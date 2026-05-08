import re


def decode_txt_plain(filepath):
    flight_data = []

    with open(filepath, "r", encoding="utf-8", errors="ignore") as file:
        lines = file.readlines()

    for line in lines:
        lat = extract_value(line, ["latitude", "lat"])
        lon = extract_value(line, ["longitude", "lon", "lng"])

        if lat is None or lon is None:
            continue

        try:
            flight_data.append({
                "time": extract_text_value(line, ["time", "timestamp"]) or "",
                "latitude": float(lat),
                "longitude": float(lon),
                "altitude": float(extract_value(line, ["altitude", "height"]) or 0),
                "speed": float(extract_value(line, ["speed", "velocity"]) or 0),
                "battery": float(extract_value(line, ["battery"]) or 0)
            })
        except ValueError:
            continue

    return flight_data


def extract_value(text, keys):
    for key in keys:
        pattern = rf"{key}\s*[:=]\s*(-?\d+\.?\d*)"
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1)

    return None


def extract_text_value(text, keys):
    for key in keys:
        pattern = rf"{key}\s*[:=]\s*([^\s,;]+)"
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1)

    return None