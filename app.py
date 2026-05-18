from flask import Flask, render_template, request, send_file
from werkzeug.utils import secure_filename
from decoders.main_decoder import decode_log_file
from decoders.dji_log_parser import DJILogParser
import os

app = Flask(__name__)

UPLOAD_FOLDER = "uploads"
CONVERTED_FOLDER = "converted"

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(CONVERTED_FOLDER, exist_ok=True)


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/upload", methods=["POST"])
def upload_file():
    file = request.files.get("logfile")

    if file is None or file.filename == "":
        return "Δεν επέλεξες αρχείο."

    filename = secure_filename(file.filename)
    filepath = os.path.join(UPLOAD_FOLDER, filename)

    file.save(filepath)

    try:
        extension = os.path.splitext(filename)[1].lower()

        # =========================
        # DJI ENCRYPTED TXT
        # =========================
        if extension == ".txt":

            parser = DJILogParser()

            success = parser.parse_file(filepath)

            if not success:
                return """
                <h1>Αποτυχία αποκωδικοποίησης</h1>
                <a href="/">Πίσω</a>
                """

            decoded_filename = filename.replace(".txt", "_decoded.csv")

            decoded_path = os.path.join(
                CONVERTED_FOLDER,
                decoded_filename
            )

            parser.export_csv(decoded_path)

            return render_template(
                "txt_detected.html",
                original_filename=filename,
                decoded_filename=decoded_filename
            )

        # =========================
        # NORMAL FILES
        # =========================
        result = decode_log_file(filepath)

        if result["status"] != "success":
            return result.get("message", "Σφάλμα.")

        return render_template(
            "success.html",
            filename=filename,
            flight_data=result["data"]
        )

    except Exception as error:
        return f"Σφάλμα: {error}"


@app.route("/download/<filename>")
def download_decoded_file(filename):
    path = os.path.join(CONVERTED_FOLDER, filename)

    return send_file(
        path,
        as_attachment=True
    )


@app.route("/view/<filename>")
def view_decoded_file(filename):
    path = os.path.join(CONVERTED_FOLDER, filename)

    result = decode_log_file(path)

    if result["status"] != "success":
        return "Αποτυχία ανάγνωσης decoded αρχείου."

    return render_template(
        "success.html",
        filename=filename,
        flight_data=result["data"]
    )


if __name__ == "__main__":
    app.run(debug=True, use_reloader=False)