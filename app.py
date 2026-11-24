
from flask import (
    Flask, render_template, request,
    send_from_directory, url_for
)

from werkzeug.utils import secure_filename
from pathlib import Path
import uuid

from huffman import (
    compress_file,
    decompress_file,
    read_header
)

app = Flask(__name__)

BASE_DIR = Path(__file__).resolve().parent

UPLOAD_FOLDER = BASE_DIR / "uploads"
COMPRESSED_FOLDER = BASE_DIR / "compressed"
DECOMPRESSED_FOLDER = BASE_DIR / "decompressed"

for folder in [
    UPLOAD_FOLDER,
    COMPRESSED_FOLDER,
    DECOMPRESSED_FOLDER
]:
    folder.mkdir(exist_ok=True)

app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024

ALLOWED_EXTENSIONS = {
    ".txt", ".pdf", ".doc", ".docx"
}


def allowed_file(filename):
    return Path(filename).suffix.lower() in ALLOWED_EXTENSIONS


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/compress", methods=["POST"])
def compress():

    uploaded_file = request.files.get("file")

    if uploaded_file is None or uploaded_file.filename == "":
        return render_template(
            "index.html",
            error="Please select a file."
        )

    if not allowed_file(uploaded_file.filename):
        return render_template(
            "index.html",
            error="Only TXT, PDF, DOC and DOCX files are supported."
        )

    original_name = secure_filename(uploaded_file.filename)

    if not original_name:
        return render_template(
            "index.html",
            error="Invalid filename."
        )

    unique_id = uuid.uuid4().hex[:8]

    input_path = UPLOAD_FOLDER / f"{unique_id}_{original_name}"

   
    compressed_name = f"{unique_id}_{original_name}.huff"

    compressed_path = COMPRESSED_FOLDER / compressed_name

    uploaded_file.save(input_path)

    try:

        original_size, compressed_size = compress_file(
            str(input_path),
            str(compressed_path),
            original_name
        )

        saved_bytes = original_size - compressed_size

        if original_size > 0:
            saving_percentage = (
                saved_bytes / original_size
            ) * 100
        else:
            saving_percentage = 0

        result = {
            "operation": "Compression",
            "original_name": original_name,
            "output_name": compressed_name,
            "original_size": original_size,
            "compressed_size": compressed_size,
            "saved_bytes": saved_bytes,
            "saving_percentage": round(saving_percentage, 2),
            "download_url": url_for(
                "download_file",
                folder="compressed",
                filename=compressed_name
            )
        }

        return render_template("result.html", result=result)

    except Exception as error:

        return render_template(
            "index.html",
            error=f"Compression failed: {error}"
        )


@app.route("/decompress", methods=["POST"])
def decompress():

    uploaded_file = request.files.get("compressed_file")

    if uploaded_file is None or uploaded_file.filename == "":
        return render_template(
            "index.html",
            error="Please select a compressed .huff file."
        )

    if Path(uploaded_file.filename).suffix.lower() != ".huff":
        return render_template(
            "index.html",
            error="Please upload a .huff file."
        )

    unique_id = uuid.uuid4().hex[:8]

    compressed_name = secure_filename(uploaded_file.filename)

    input_path = UPLOAD_FOLDER / f"{unique_id}_{compressed_name}"

    uploaded_file.save(input_path)

    try:

        header = read_header(str(input_path))

        original_name = secure_filename(
            header.get("original_name", "restored_file.txt")
        )

        if not original_name:
            original_name = "restored_file.txt"

        restored_name = f"{unique_id}_{original_name}"

        restored_path = DECOMPRESSED_FOLDER / restored_name

        decompress_file(
            str(input_path),
            str(restored_path)
        )

        result = {
            "operation": "Decompression",
            "original_name": compressed_name,
            "output_name": original_name,
            "download_url": url_for(
                "download_file",
                folder="decompressed",
                filename=restored_name
            )
        }

        return render_template("result.html", result=result)

    except Exception as error:

        return render_template(
            "index.html",
            error=f"Decompression failed: {error}"
        )


@app.route("/download/<folder>/<filename>")
def download_file(folder, filename):
    folders = {
        "compressed": COMPRESSED_FOLDER,
        "decompressed": DECOMPRESSED_FOLDER
    }

    if folder not in folders:
        return "Invalid download location", 404

    return send_from_directory(
        folders[folder],
        filename,
        as_attachment=True
    )


@app.errorhandler(413)
def file_too_large(error):

    return render_template(
        "index.html",
        error="Maximum file size is 10 MB."
    ), 413


if __name__ == "__main__":
    app.run(debug=True)
