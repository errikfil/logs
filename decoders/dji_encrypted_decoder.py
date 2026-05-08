import os
import subprocess


CONVERTED_FOLDER = "converted"


def decode_dji_encrypted_txt(filepath, filename):
    os.makedirs(CONVERTED_FOLDER, exist_ok=True)

    output_csv = os.path.join(
        CONVERTED_FOLDER,
        os.path.splitext(filename)[0] + ".csv"
    )

    command = [
        "./dji-log",
        filepath,
        "-c",
        output_csv
    ]

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=120
        )

        if result.returncode != 0:
            raise Exception(result.stderr or result.stdout)

        if not os.path.exists(output_csv):
            raise Exception("Ο decoder δεν δημιούργησε CSV αρχείο.")

        return output_csv

    except Exception as error:
        raise Exception(
            "Το DJI αρχείο είναι encrypted και δεν μπορεί να διαβαστεί χωρίς "
            f"κανονικό DJI decoder/API key. Λεπτομέρειες: {error}"
        )