from flask import Flask, render_template, request
from dotenv import load_dotenv
from werkzeug.utils import secure_filename
from decoders.dji_encrypted_decoder import decode_dji_encrypted_txt
import os
import csv
import subprocess
import re
import json
import requests

app = Flask(__name__)

load_dotenv()

UPLOAD_FOLDER = "uploads"
CONVERTED_FOLDER = "converted"

DECODER_API_URL = os.getenv("DECODER_API_URL")
DECODER_API_KEY = os.getenv("DECODER_API_KEY")

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(CONVERTED_FOLDER, exist_ok=True)


@app.route("/")
def home():
    return render_template("index.html")


def get_value(row, possible_names, default=None):
    for name in possible_names:
        if name in row and row[name] not in [None, ""]:
            return row[name]
    return default


def safe_float(value, default=0):
    try:
        if value in [None, "", "NULL", "null"]:
            return default
        return float(value)
    except:
        return default


def normalize_points(data):
    flight_data = []

    if isinstance(data, dict):
        if "data" in data:
            data = data["data"]
        elif "flight_data" in data:
            data = data["flight_data"]
        elif "points" in data:
            data = data["points"]
        elif "records" in data:
            data = data["records"]

    if not isinstance(data, list):
        return []

    for point in data:
        if not isinstance(point, dict):
            continue

        lat = get_value(point, ["latitude", "lat", "Latitude", "LAT"])
        lon = get_value(point, ["longitude", "lon", "lng", "Longitude", "LON", "LNG"])

        if lat in [None, ""] or lon in [None, ""]:
            continue

        flight_data.append({
            "time": get_value(point, ["time", "timestamp", "Time", "Timestamp"], ""),
            "latitude": safe_float(lat),
            "longitude": safe_float(lon),
            "altitude": safe_float(get_value(point, ["altitude", "height", "Altitude", "Height"], 0)),
            "speed": safe_float(get_value(point, ["speed", "velocity", "Speed", "Velocity"], 0)),
            "battery": safe_float(get_value(point, ["battery", "battery_percent", "Battery", "BATTERY"], 0))
        })

    return flight_data


def parse_json(filepath):
    with open(filepath, "r", encoding="utf-8", errors="ignore") as jsonfile:
        data = json.load(jsonfile)

    return normalize_points(data)


def parse_csv(filepath):
    flight_data = []

    with open(filepath, newline="", encoding="utf-8-sig", errors="ignore") as csvfile:
        reader = csv.DictReader(csvfile)

        for row in reader:
            lat = get_value(row, ["latitude", "lat", "Latitude", "LAT"])
            lon = get_value(row, ["longitude", "lon", "lng", "Longitude", "LON", "LNG"])

            if lat in [None, ""] or lon in [None, ""]:
                continue

            flight_data.append({
                "time": get_value(row, ["time", "timestamp", "Time", "Timestamp"], ""),
                "latitude": safe_float(lat),
                "longitude": safe_float(lon),
                "altitude": safe_float(get_value(row, ["altitude", "height", "Altitude", "Height"], 0)),
                "speed": safe_float(get_value(row, ["speed", "velocity", "Speed", "Velocity"], 0)),
                "battery": safe_float(get_value(row, ["battery", "battery_percent", "Battery", "BATTERY"], 0))
            })

    return flight_data


def detect_file_type(filepath):
    ext = os.path.splitext(filepath)[1].lower()

    if ext == ".csv":
        return "csv"

    if ext == ".json":
        return "json"

    if ext == ".txt":
        with open(filepath, "rb") as f:
            header = f.read(300)

        binary_bytes = sum(
            1 for b in header
            if b < 9 or (13 < b < 32) or b > 126
        )

        if b"\x00" in header or binary_bytes > 30:
            return "dji_encrypted"

        try:
            header.decode("utf-8")
            return "txt_plain"
        except:
            return "dji_encrypted"

    return "unknown"


def parse_app_log(filepath):
    flight_data = []

    pattern = re.compile(
        r"(?P<time>\d{2}:\d{2}:\d{2}\.\d{3}).*?"
        r"VehicleModel - "
        r"(?P<lat>-?\d+\.\d+)/(?P<lon>-?\d+\.\d+)"
        r"\((?P<sat>\d+)\)\s+"
        r"(?P<alt>-?\d+\.\d+)m.*?"
        r"battery\((?P<battery>\d+|NULL)%?\)"
    )

    with open(filepath, "r", encoding="utf-8", errors="ignore") as logfile:
        for line in logfile:
            match = pattern.search(line)

            if match:
                battery_value = match.group("battery")

                flight_data.append({
                    "time": match.group("time"),
                    "latitude": safe_float(match.group("lat")),
                    "longitude": safe_float(match.group("lon")),
                    "altitude": safe_float(match.group("alt")),
                    "speed": 0,
                    "battery": safe_float(battery_value)
                })

    return flight_data


def convert_dji_txt_to_csv(filepath, filename):
    output_name = os.path.splitext(filename)[0] + ".csv"
    csv_output = os.path.join(CONVERTED_FOLDER, output_name)

    subprocess.run(
        [
            "./dji-log",
            filepath,
            "-c",
            csv_output
        ],
        check=True
    )

    return csv_output


def decode_encrypted_dji_log(filepath):
    if not DECODER_API_URL:
        raise Exception("Δεν έχει οριστεί DECODER_API_URL στο .env")

    headers = {}

    if DECODER_API_KEY:
        headers["Authorization"] = f"Bearer {DECODER_API_KEY}"

    with open(filepath, "rb") as log_file:
        response = requests.post(
            DECODER_API_URL,
            headers=headers,
            files={"file": log_file},
            timeout=120
        )

    if response.status_code != 200:
        raise Exception(f"Decoder API error: {response.status_code} - {response.text}")

    decoded_json = response.json()

    return normalize_points(decoded_json)


@app.route("/upload", methods=["POST"])
def upload_file():
    file = request.files.get("logfile")

    if file is None or file.filename == "":
        return "Δεν επέλεξες αρχείο."

    filename = secure_filename(file.filename)
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    file.save(filepath)

    try:
        file_type = detect_file_type(filepath)

        if file_type == "csv":
            flight_data = parse_csv(filepath)

        elif file_type == "json":
            flight_data = parse_json(filepath)

        elif file_type == "txt_plain":
            flight_data = parse_app_log(filepath)

            if len(flight_data) == 0:
                try:
                    csv_path = convert_dji_txt_to_csv(filepath, filename)
                    flight_data = parse_csv(csv_path)
                except Exception:
                    flight_data = []

        elif file_type == "dji_encrypted":
            try:
                csv_path = decode_dji_encrypted_txt(filepath, filename)
                flight_data = parse_csv(csv_path)

            except Exception as decoder_error:
                return render_template(
                    "txt_detected.html",
                    filename=filename,
                    message=str(decoder_error)
                )

        else:
            return "Υποστηρίζονται μόνο .csv, .json και .txt αρχεία."

    except Exception as error:
        return f"Σφάλμα επεξεργασίας αρχείου: {error}"

    if len(flight_data) == 0:
        return """
        <h1>Δεν βρέθηκαν δεδομένα πτήσης</h1>
        <p>Το αρχείο δεν περιέχει αναγνωρίσιμα coordinates.</p>
        <a href="/">Πίσω</a>
        """

    return render_template(
        "success.html",
        filename=filename,
        flight_data=flight_data
    )

if __name__ == "__main__":
    app.run(debug=True, use_reloader=False)