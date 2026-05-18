from decoders.detector import detect_file_type
from decoders.csv_decoder import decode_csv
from decoders.json_decoder import decode_json
from decoders.txt_decoder import decode_txt_plain
from decoders.dji_encrypted_decoder import decode_dji_encrypted


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
        data = decode_dji_encrypted(filepath)

        if len(data) == 0:
            return {
                "status": "error",
                "type": "dji_encrypted",
                "data": [],
                "message": "Δεν μπόρεσε να γίνει αποκωδικοποίηση του DJI encrypted αρχείου."
            }

        return {
            "status": "success",
            "type": "dji_encrypted",
            "data": data
        }

    return {
        "status": "error",
        "type": "unknown",
        "data": [],
        "message": "Άγνωστος τύπος αρχείου."
    }