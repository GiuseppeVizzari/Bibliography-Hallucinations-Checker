import json
import logging
import os
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from flask import Blueprint, render_template, request, flash, redirect, current_app, jsonify
from werkzeug.utils import secure_filename
from .pdf_processor import extract_bibliography
from .checkers import check_reference
from .checkers.config import MAX_WORKERS

logger = logging.getLogger(__name__)

bp = Blueprint('main', __name__)

ALLOWED_EXTENSIONS = {'pdf'}

# In-memory job tracker for AJAX polling
# job_id -> {status, total, checked, results, filepath, error}
_jobs = {}
_jobs_lock = threading.Lock()


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def _check_single_ref(index, ref, total):
    """Worker function: check one reference, return result dict."""
    logger.info(f"[{index}/{total}]")
    check_result = check_reference(ref)
    return {
        "original": ref,
        "original_url": check_result.get("original_url"),
        "check": check_result,
        "number": index
    }


def _process_job(job_id, filepath, refs):
    """Background worker: process a bibliography job and update job state."""
    total = len(refs)
    results = [None] * total

    try:
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = {
                executor.submit(_check_single_ref, i, ref, total): i
                for i, ref in enumerate(refs, 1)
            }
            for future in as_completed(futures):
                try:
                    result = future.result()
                    results[result["number"] - 1] = result
                except Exception as e:
                    logger.error(f"Error in worker: {e}", exc_info=True)
                    idx = futures[future]
                    results[idx - 1] = {
                        "original": refs[idx - 1],
                        "original_url": None,
                        "check": {"status": "error", "message": str(e), "similarity": 0.0},
                        "number": idx
                    }

                # Update progress after each completed reference
                with _jobs_lock:
                    if job_id in _jobs:
                        _jobs[job_id]["checked"] = sum(1 for r in results if r is not None)

        with _jobs_lock:
            if job_id in _jobs:
                _jobs[job_id]["results"] = results
                _jobs[job_id]["status"] = "complete"

    except Exception as e:
        logger.error(f"Error processing job {job_id}: {e}", exc_info=True)
        with _jobs_lock:
            if job_id in _jobs:
                _jobs[job_id]["error"] = str(e)
                _jobs[job_id]["status"] = "error"
    finally:
        # Clean up uploaded file
        if os.path.exists(filepath):
            os.remove(filepath)


@bp.route('/status/<job_id>', methods=['GET'])
def job_status(job_id):
    """Polling endpoint: return job progress as JSON."""
    with _jobs_lock:
        job = _jobs.get(job_id)
        if job is None:
            return jsonify({"status": "not_found", "error": "Job not found"}), 404
        return jsonify({
            "status": job["status"],
            "total": job["total"],
            "checked": job["checked"],
            "error": job.get("error"),
            "results": job.get("results") if job["status"] == "complete" else None
        })


@bp.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        # Check if file is present
        if 'file' not in request.files:
            flash('No file part')
            return redirect(request.url)

        file = request.files['file']

        if file.filename == '':
            flash('No selected file')
            return redirect(request.url)

        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            # Save temporarily
            upload_folder = os.path.join(current_app.root_path, 'uploads')
            os.makedirs(upload_folder, exist_ok=True)
            filepath = os.path.join(upload_folder, filename)
            file.save(filepath)

            # Process PDF
            try:
                refs = extract_bibliography(filepath)
                if not refs:
                    flash('No references found or bibliography section not detected.')
                    return redirect(request.url)

                total_refs = len(refs)

                logger.info(f"\n{'='*60}")
                logger.info(f"Processing {total_refs} references")
                logger.info(f"{'='*60}\n")

                # Create async job for AJAX clients
                job_id = str(uuid.uuid4())
                with _jobs_lock:
                    _jobs[job_id] = {
                        "status": "processing",
                        "total": total_refs,
                        "checked": 0,
                        "results": None,
                        "filepath": filepath,
                        "error": None
                    }

                # Launch background worker
                threading.Thread(
                    target=_process_job,
                    args=(job_id, filepath, refs),
                    daemon=True
                ).start()

                # Detect AJAX request via X-Requested-With header
                if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                    return jsonify({"job_id": job_id, "status": "processing"})

                # Fallback: synchronous processing for non-AJAX clients
                results = [None] * total_refs
                with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
                    futures = {
                        executor.submit(_check_single_ref, i, ref, total_refs): i
                        for i, ref in enumerate(refs, 1)
                    }
                    for future in as_completed(futures):
                        try:
                            result = future.result()
                            results[result["number"] - 1] = result
                        except Exception as e:
                            logger.error(f"Error in worker: {e}", exc_info=True)
                            idx = futures[future]
                            results[idx - 1] = {
                                "original": refs[idx - 1],
                                "original_url": None,
                                "check": {"status": "error", "message": str(e), "similarity": 0.0},
                                "number": idx
                            }

                logger.info(f"\n{'='*60}")
                logger.info(f"Processing complete!")
                logger.info(f"{'='*60}\n")

                return render_template('results.html', results=results, total_count=total_refs)

            except Exception as e:
                logger.error(f"Error processing file: {e}", exc_info=True)
                flash(f'Error processing file: {str(e)}')
                return redirect(request.url)
            finally:
                # Cleanup
                if os.path.exists(filepath):
                    os.remove(filepath)

    return render_template('index.html')
