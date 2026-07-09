import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from flask import Blueprint, render_template, request, flash, redirect, current_app
from werkzeug.utils import secure_filename
from .pdf_processor import extract_bibliography
from .checkers import check_reference
from .checkers.config import MAX_WORKERS

logger = logging.getLogger(__name__)

bp = Blueprint('main', __name__)

ALLOWED_EXTENSIONS = {'pdf'}


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

                # Parallel verification: check references concurrently
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
