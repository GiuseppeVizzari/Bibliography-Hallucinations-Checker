import os
from flask import Blueprint, render_template, request, flash, redirect, current_app
from werkzeug.utils import secure_filename
from .pdf_processor import extract_bibliography
from .reference_checker import check_reference

bp = Blueprint('main', __name__)

ALLOWED_EXTENSIONS = {'pdf'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

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
                
                # Process all references (no batching needed with Semantic Scholar)
                import time
                results = []
                total_refs = len(refs)
                
                print(f"\n{'='*60}")
                print(f"Processing {total_refs} references")
                print(f"{'='*60}\n")
                
                for i, ref in enumerate(refs, 1):
                    print(f"[{i}/{total_refs}]")
                    check_result = check_reference(ref)
                    results.append({
                        "original": ref,
                        "check": check_result,
                        "number": i
                    })
                
                print(f"\n{'='*60}")
                print(f"Processing complete!")
                print(f"{'='*60}\n")
                
                return render_template('results.html', results=results, total_count=total_refs)
                
            except Exception as e:
                flash(f'Error processing file: {str(e)}')
                return redirect(request.url)
            finally:
                # Cleanup
                if os.path.exists(filepath):
                    os.remove(filepath)

    return render_template('index.html')
