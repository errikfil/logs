from decoders.detector import detect_file_type
from decoders.csv_decoder import decode_csv
from decoders.json_decoder import decode_json
from decoders.txt_decoder import decode_txt_plain


def decode_log_file(filepath):
    file_type = detect_file_type(filepath)

    if file_type == "csv":
        return {
            "status": "success",
            "type": "csv",
            "data": decode_csv(filepath)
        }

    if file_type == "json":
        return {
            "status": "success",
            "type": "json",
            "data": decode_json(filepath)
        }

    if file_type == "txt_plain":
        return {
            "status": "success",
            "type": "txt_plain",
            "data": decode_txt_plain(filepath)
        }

    if file_type == "dji_encrypted":
        return {
            "status": "encrypted",
            "type": "dji_encrypted",
            "data": [],
            "message": "Το αρχείο είναι DJI encrypted/binary TXT και χρειάζεται εξωτερικό DJI decoder."
        }

    return {
        "status": "error",
        "type": "unknown",
        "data": [],
        "message": "Άγνωστος τύπος αρχείου."
    }