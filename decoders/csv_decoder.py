import csv


def get_value(row, possible_keys, default=0):
    for key in possible_keys:
        if key in row and row[key] not in ["", None]:
            return row[key]
    return default


def decode_csv(filepath):
    flight_data = []

    with open(filepath, "r", encoding="utf-8-sig", errors="ignore") as file:
        reader = csv.DictReader(file)

        for row in reader:
            lat = get_value(row, ["latitude", "lat", "Latitude", "LAT"])
            lon = get_value(row, ["longitude", "lon", "lng", "Longitude", "LON", "LNG"])

            if not lat or not lon:
                continue

            try:
                flight_data.append({
                    "time": get_value(row, ["time", "timestamp", "Time", "Timestamp"], ""),
                    "latitude": float(lat),
                    "longitude": float(lon),
                    "altitude": float(get_value(row, ["altitude", "height", "Altitude", "Height"], 0)),
                    "speed": float(get_value(row, ["speed", "velocity", "Speed", "Velocity"], 0)),
                    "battery": float(get_value(row, ["battery", "battery_percent", "Battery", "BatteryPercent"], 0))
                })
            except ValueError:
                continue

    return flight_data