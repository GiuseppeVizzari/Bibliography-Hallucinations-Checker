import requests

def test_query(title):
    url = "https://api.openalex.org/works"
    params = {"search": title}
    r = requests.get(url, params=params)
    data = r.json()
    print(f"Items found for '{title}':", len(data.get("results", [])))
    for res in data.get("results", [])[:3]:
        print(" ->", res.get("title"))

test_query("You'll never walk alone: Modeling social behavior for multi-target tracking")
test_query("Modeling social behavior for multi-target tracking")
