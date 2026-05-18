import os
from pathlib import Path
from decoders.dji_log_parser import DJILogParser
from decoders.csv_decoder import decode_csv

CONVERTED_FOLDER = "converted"


def decode_dji_encrypted(filepath):
    os.makedirs(CONVERTED_FOLDER, exist_ok=True)

    output_name = Path(filepath).stem + ".csv"
    output_path = os.path.join(CONVERTED_FOLDER, output_name)

    parser = DJILogParser()
    success = parser.parse_file(filepath)

    if not success:
        return []

    parser.export_csv(output_path)

    if not os.path.exists(output_path):
        return []

    print("Decoded CSV saved at:", output_path)

    return decode_csv(output_path)