from flask import Flask, render_template, request, send_from_directory, url_for
from werkzeug.utils import secure_filename
from pathlib import Path
from datetime import datetime
import json
import uuid

from huffman import compress_file, compress_pdf, decompress_file, read_header

app = Flask(__name__)
BASE_DIR = Path(__file__).resolve().parent
UPLOAD_FOLDER = BASE_DIR / "uploads"
COMPRESSED_FOLDER = BASE_DIR / "compressed"
DECOMPRESSED_FOLDER = BASE_DIR / "decompressed"
HISTORY_FILE = BASE_DIR / "history.json"

for folder in (UPLOAD_FOLDER, COMPRESSED_FOLDER, DECOMPRESSED_FOLDER):
    folder.mkdir(exist_ok=True)

# 50 MB per uploaded file. Increase only if your hosting plan supports it.
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024
ALLOWED_EXTENSIONS = {".txt", ".pdf", ".doc", ".docx"}


def allowed_file(filename):
    return Path(filename).suffix.lower() in ALLOWED_EXTENSIONS


def read_history():
    try:
        return json.loads(HISTORY_FILE.read_text(encoding="utf-8")) if HISTORY_FILE.exists() else []
    except (json.JSONDecodeError, OSError):
        return []


def save_history(entry):
    history = read_history()
    history.insert(0, entry)
    HISTORY_FILE.write_text(json.dumps(history[:100], indent=2), encoding="utf-8")


@app.route("/")
def index():
    return render_template("index.html", history=read_history()[:10])


@app.route("/compress", methods=["POST"])
def compress():
    uploaded_files = [f for f in request.files.getlist("files") if f and f.filename]
    if not uploaded_files:
        single = request.files.get("file")
        uploaded_files = [single] if single and single.filename else []
    if not uploaded_files:
        return render_template("index.html", error="Please select at least one file.", history=read_history()[:10])

    target_mode = request.form.get("target_mode", "percentage")
    compression_level = request.form.get("compression_level", "medium")
    target_value_raw = request.form.get("target_value", "30")
    if compression_level not in {"low", "medium", "high"}:
        compression_level = "medium"
    try:
        target_value = float(target_value_raw)
        if target_mode == "percentage" and not 1 <= target_value <= 95:
            raise ValueError("Percentage must be between 1 and 95.")
        if target_mode == "size" and not 0.01 <= target_value <= 50:
            raise ValueError("Target size must be between 0.01 and 50 MB.")
        if target_mode not in {"percentage", "size"}:
            raise ValueError("Invalid target mode.")
    except ValueError as error:
        return render_template("index.html", error=str(error), history=read_history()[:10])

    results = []
    errors = []
    for uploaded_file in uploaded_files:
        original_name = secure_filename(uploaded_file.filename)
        if not original_name or not allowed_file(original_name):
            errors.append(f"{uploaded_file.filename}: unsupported file type.")
            continue

        unique_id = uuid.uuid4().hex[:10]
        input_path = UPLOAD_FOLDER / f"{unique_id}_{original_name}"
        uploaded_file.save(input_path)
        suffix = Path(original_name).suffix.lower()
        is_pdf = suffix == ".pdf"
        output_name = f"{Path(original_name).stem}_compressed.pdf" if is_pdf else f"{Path(original_name).stem}.huff"
        output_name = f"{unique_id}_{output_name}"
        output_folder = COMPRESSED_FOLDER
        output_path = output_folder / output_name

        try:
            if is_pdf:
                original_size, output_size, target_bytes = compress_pdf(
                    str(input_path), str(output_path), target_mode, target_value
                )
                method = "PDF optimization (lossless)"
                download_folder = "compressed"
            else:
                original_size, output_size, target_bytes = compress_file(
                    str(input_path), str(output_path), original_name,
                    target_mode, target_value, compression_level
                )
                method = f"Lossless {compression_level} compression"
                download_folder = "compressed"

            saved_bytes = original_size - output_size
            reduction = round((saved_bytes / original_size) * 100, 2) if original_size else 0
            target_met = output_size <= target_bytes
            item = {
                "operation": "Compression",
                "original_name": original_name,
                "output_name": output_name,
                "original_size": original_size,
                "compressed_size": output_size,
                "saved_bytes": saved_bytes,
                "saving_percentage": reduction,
                "target_size": target_bytes,
                "target_met": target_met,
                "compression_level": compression_level.title(),
                "method": method,
                "download_url": url_for("download_file", folder=download_folder, filename=output_name)
            }
            results.append(item)
            save_history({
                "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "input_name": original_name,
                "output_name": output_name,
                "original_size": original_size,
                "output_size": output_size,
                "reduction": reduction,
                "operation": "Compression",
                "folder": "compressed"
            })
        except Exception as error:
            output_path.unlink(missing_ok=True)
            errors.append(f"{original_name}: {error}")
        finally:
            input_path.unlink(missing_ok=True)

    if not results:
        message = " ".join(errors) or "No files could be processed."
        return render_template("index.html", error=message, history=read_history()[:10])
    return render_template("result.html", results=results, errors=errors)


@app.route("/decompress", methods=["POST"])
def decompress():
    uploaded_file = request.files.get("compressed_file")
    if uploaded_file is None or uploaded_file.filename == "":
        return render_template("index.html", error="Please select a .huff file.", history=read_history()[:10])
    compressed_name = secure_filename(uploaded_file.filename)
    if Path(compressed_name).suffix.lower() != ".huff":
        return render_template("index.html", error="Only .huff files can be decompressed here. Optimized PDFs are already readable PDFs.", history=read_history()[:10])

    unique_id = uuid.uuid4().hex[:10]
    input_path = UPLOAD_FOLDER / f"{unique_id}_{compressed_name}"
    uploaded_file.save(input_path)
    try:
        header = read_header(str(input_path))
        original_name = secure_filename(header.get("original_name", "restored_file.txt")) or "restored_file.txt"
        restored_name = f"{unique_id}_{original_name}"
        restored_path = DECOMPRESSED_FOLDER / restored_name
        decompress_file(str(input_path), str(restored_path))
        save_history({
            "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "input_name": compressed_name,
            "output_name": original_name,
            "original_size": restored_path.stat().st_size,
            "output_size": restored_path.stat().st_size,
            "reduction": 0,
            "operation": "Decompression",
            "folder": "decompressed"
        })
        result = {
            "operation": "Decompression",
            "original_name": compressed_name,
            "output_name": original_name,
            "download_url": url_for("download_file", folder="decompressed", filename=restored_name)
        }
        return render_template("result.html", results=[result], errors=[])
    except Exception as error:
        return render_template("index.html", error=f"Decompression failed: {error}", history=read_history()[:10])
    finally:
        input_path.unlink(missing_ok=True)


@app.route("/history")
def history():
    return render_template("history.html", history=read_history())


@app.route("/download/<folder>/<path:filename>")
def download_file(folder, filename):
    folders = {"compressed": COMPRESSED_FOLDER, "decompressed": DECOMPRESSED_FOLDER}
    if folder not in folders:
        return "Invalid download location", 404
    return send_from_directory(folders[folder], filename, as_attachment=True)


@app.errorhandler(413)
def file_too_large(error):
    return render_template("index.html", error="Each uploaded file must be 50 MB or smaller.", history=read_history()[:10]), 413


if __name__ == "__main__":
    app.run(debug=True)
