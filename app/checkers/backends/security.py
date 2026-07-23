"""
app/checkers/backends/security.py

Shared security utilities for HTTP backends.
"""

import ipaddress
import logging
import socket
from functools import lru_cache
from typing import List
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# Private / reserved / special IP ranges that must never be fetched
_BLOCKED_RANGES: List[ipaddress.IPv4Network] = [
    ipaddress.IPv4Network("0.0.0.0/8"),       # current network (RFC 1122)
    ipaddress.IPv4Network("10.0.0.0/8"),      # private (RFC 1918)
    ipaddress.IPv4Network("100.64.0.0/10"),   # shared address space (RFC 6598)
    ipaddress.IPv4Network("127.0.0.0/8"),     # loopback (RFC 1122)
    ipaddress.IPv4Network("168.254.0.0/16"),  # link-local (RFC 3927)
    ipaddress.IPv4Network("169.254.0.0/16"),  # link-local (RFC 3927)
    ipaddress.IPv4Network("172.16.0.0/12"),   # private (RFC 1918)
    ipaddress.IPv4Network("192.0.0.0/24"),    # IETF protocol registry (RFC 5736)
    ipaddress.IPv4Network("192.0.2.0/24"),    # TEST-NET-1 (RFC 5737)
    ipaddress.IPv4Network("192.88.99.0/24"),  # 6to4 relay (RFC 7526)
    ipaddress.IPv4Network("192.168.0.0/16"),  # private (RFC 1918)
    ipaddress.IPv4Network("198.18.0.0/15"),   # benchmarking (RFC 2544)
    ipaddress.IPv4Network("198.51.100.0/24"), # TEST-NET-2 (RFC 5737)
    ipaddress.IPv4Network("203.0.113.0/24"),  # TEST-NET-3 (RFC 5737)
    ipaddress.IPv4Network("224.0.0.0/4"),     # multicast (RFC 3171)
    ipaddress.IPv4Network("240.0.0.0/4"),     # reserved (RFC 1112)
    ipaddress.IPv4Network("255.255.255.255/32"),  # broadcast
]

_BLOCKED_V6: List[ipaddress.IPv6Network] = [
    ipaddress.IPv6Network("::/128"),            # unspecified
    ipaddress.IPv6Network("::1/128"),           # loopback
    ipaddress.IPv6Network("::/96"),             # IPv4-mapped (deprecated)
    ipaddress.IPv6Network("::ffff:0:0/96"),    # IPv4-mapped
    ipaddress.IPv6Network("64:ff9b::/48"),     # IPv4-IPv6 translation
    ipaddress.IPv6Network("100::/64"),          # discard-only (RFC 6666)
    ipaddress.IPv6Network("2001::/32"),         # Teredo (RFC 4380)
    ipaddress.IPv6Network("2001:2::/48"),       # BCP 38 deprecation
    ipaddress.IPv6Network("2001:db8::/32"),     # documentation (RFC 3849)
    ipaddress.IPv6Network("2002::/16"),         # 6to4 (RFC 7526)
    ipaddress.IPv6Network("fc00::/7"),          # unique local (RFC 4193)
    ipaddress.IPv6Network("fe80::/10"),         # link-local (RFC 4291)
    ipaddress.IPv6Network("ff00::/8"),          # multicast
]

_ALLOWED_SCHEMES = {"http", "https"}
_MAX_REDIRECTS = 2  # prevent redirect loops / excessive hops


def _ip_is_blocked(addr: str) -> bool:
    """Check if an IP address string falls within any blocked range."""
    try:
        ip = ipaddress.ip_address(addr)
    except ValueError:
        return True  # treat unparseable as blocked

    if isinstance(ip, ipaddress.IPv4Address):
        return any(ip in net for net in _BLOCKED_RANGES)
    else:
        return any(ip in net for net in _BLOCKED_V6)


@lru_cache(maxsize=512)
def _resolve_and_check(hostname: str) -> None:
    """
    Resolve *hostname* and verify every returned IP address.
    Raises ``ValueError`` if any address is blocked.
    Cached because repeated lookups of the same host are common
    (e.g. during meta-refresh follow).
    """
    try:
        infos = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
    except socket.gaierror:
        return  # DNS failure will be caught by the HTTP layer

    for family, socktype, proto, canonname, sockaddr in infos:
        addr = sockaddr[0]
        if _ip_is_blocked(addr):
            raise ValueError(
                f"SSRF protection: hostname {hostname!r} resolved to blocked "
                f"address {addr} (family {family})"
            )


def validate_url_for_fetch(url: str) -> None:
    """
    Validate *url* is safe to fetch from the server side.

    Checks:
    - Scheme is ``http`` or ``https``
    - Host is present and not an IP literal pointing to a blocked range
    - DNS resolution does not return blocked addresses

    Raises ``ValueError`` on violation.
    """
    parsed = urlparse(url)

    # Scheme check
    if parsed.scheme not in _ALLOWED_SCHEMES:
        raise ValueError(
            f"SSRF protection: scheme {parsed.scheme!r} not allowed "
            f"(allowed: {_ALLOWED_SCHEMES})"
        )

    hostname = parsed.hostname
    if not hostname:
        raise ValueError("SSRF protection: no hostname in URL")

    # Block bare IP literals (both IPv4 and IPv6) to avoid bypassing via
    # numeric addresses that bypass DNS-based checks.
    try:
        ipaddress.ip_address(hostname)
        # If we get here, it IS a valid IP — block it entirely.
        # We only want to allow hostnames that resolve via DNS.
        raise ValueError(
            f"SSRF protection: bare IP addresses are not allowed ({hostname})"
        )
    except ValueError:
        pass  # Not an IP literal — good, it's a hostname

    # DNS resolution check (cached)
    _resolve_and_check(hostname)


def _follow_redirect_safe(url: str) -> str:
    """
    Follow at most one meta-refresh redirect in *url*, returning the final URL.

    Returns the original *url* if no redirect is found or if the redirect
    target fails validation.
    """
    try:
        from urllib.parse import urljoin

        import requests

        validate_url_for_fetch(url)

        resp = requests.get(url, allow_redirects=False, timeout=10)
        if resp.status_code not in (301, 302, 303, 307, 308):
            return url

        # Check redirect count via headers
        redirect_count = int(resp.headers.get("X-Redirect-Count", "0"))
        if redirect_count >= _MAX_REDIRECTS:
            return url

        location = resp.headers.get("Location")
        if not location:
            return url

        final_url = urljoin(url, location)

        # Validate the redirect target
        validate_url_for_fetch(final_url)

        return final_url

    except (ValueError, requests.RequestException):
        return url
