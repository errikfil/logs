import json


def decode_json(filepath):
    flight_data = []

    with open(filepath, "r", encoding="utf-8", errors="ignore") as file:
        data = json.load(file)

    if isinstance(data, dict):
        if "flight_data" in data:
            data = data["flight_data"]
        elif "points" in data:
            data = data["points"]
        elif "records" in data:
            data = data["records"]

    if not isinstance(data, list):
        return []

    for row in data:
        try:
            lat = row.get("latitude") or row.get("lat")
            lon = row.get("longitude") or row.get("lon") or row.get("lng")

            if lat is None or lon is None:
                continue

            flight_data.append({
                "time": row.get("time") or row.get("timestamp") or "",
                "latitude": float(lat),
                "longitude": float(lon),
                "altitude": float(row.get("altitude") or row.get("height") or 0),
                "speed": float(row.get("speed") or row.get("velocity") or 0),
                "battery": float(row.get("battery") or row.get("battery_percent") or 0)
            })

        except Exception:
            continue

    return flight_data