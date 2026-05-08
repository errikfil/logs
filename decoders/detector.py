import os


def detect_file_type(filepath):
    ext = os.path.splitext(filepath)[1].lower()

    if ext == ".csv":
        return "csv"

    if ext == ".json":
        return "json"

    if ext == ".txt":
        with open(filepath, "rb") as f:
            sample = f.read(300)

        # Αν έχει πολλά binary bytes, πιθανότατα είναι DJI encrypted/binary log
        binary_bytes = sum(1 for b in sample if b < 9 or (13 < b < 32) or b > 126)

        if binary_bytes > 30:
            return "dji_encrypted"

        return "txt_plain"

    return "unknown"