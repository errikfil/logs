import csv
import math


def get_value(row, possible_keys, default=""):
    for key in possible_keys:
        if key in row and row[key] not in ["", None]:
            return row[key]
    return default


def safe_float(value, default=0):
    try:
        return float(str(value).replace(",", "."))
    except:
        return default


def parse_time_to_seconds(value):
    if value in ["", None, "N/A"]:
        return None

    text = str(value).strip().lower()

    try:
        return float(text.replace(",", "."))
    except:
        pass

    # π.χ. 0m 2.5s
    if "m" in text and "s" in text:
        try:
            minutes = float(text.split("m")[0].strip())
            seconds = float(text.split("m")[1].replace("s", "").strip())
            return minutes * 60 + seconds
        except:
            return None

    return None


def format_time_from_seconds(seconds):
    if seconds is None:
        return "0m 0.0s"

    minutes = int(seconds // 60)
    sec = round(seconds % 60, 1)

    return f"{minutes}m {sec}s"


def format_time(index):
    return format_time_from_seconds(index * 0.2)


def format_ft(value):
    if value in ["", None, "N/A"]:
        return "N/A"
    return f"{round(safe_float(value), 1)} ft"


def format_mph(value):
    return f"{round(safe_float(value), 1)} mph"


def format_voltage(value):
    if value in ["", None, "N/A"]:
        return "N/A"

    v = safe_float(value)

    if v > 100:
        v = v / 1000

    return f"{round(v, 3)} V"


def format_percent(value):
    if value in ["", None, "N/A"]:
        return "N/A"

    return f"{round(safe_float(value))}%"


def calculate_cell_deviation(cells, existing_value=""):
    if existing_value not in ["", None, "N/A"]:
        return f"{existing_value} V"

    values = []

    for cell in cells:
        v = safe_float(cell, 0)

        if v > 100:
            v = v / 1000

        if v > 0:
            values.append(v)

    if len(values) < 2:
        return "N/A"

    deviation = max(values) - min(values)
    return f"{round(deviation, 3)} V"


def read_csv_with_optional_sep(filepath):
    file = open(filepath, "r", encoding="utf-8-sig", errors="ignore")
    first_line = file.readline()

    if not first_line.strip().startswith("sep="):
        file.seek(0)

    return file, csv.DictReader(file)


def decode_csv(filepath):
    flight_data = []
    previous_mode = None

    mode_names = {
        "0": "Manual",
        "1": "Atti",
        "2": "P-GPS",
        "3": "P-GPS (Brake)",
        "6": "Tripod",
        "10": "Sport",
        "11": "GPS",
        "26": "Starting Motors",
    }

    file, reader = read_csv_with_optional_sep(filepath)

    try:
        for row in reader:
            lat = get_value(row, ["OSD.latitude", "latitude", "lat", "Latitude"])
            lon = get_value(row, ["OSD.longitude", "longitude", "lon", "lng", "Longitude"])

            if not lat or not lon:
                continue

            latitude = safe_float(lat)
            longitude = safe_float(lon)

            if latitude == 0 or longitude == 0:
                continue

            if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
                continue

            if flight_data:
                prev = flight_data[-1]
                if abs(latitude - prev["latitude"]) > 0.01 or abs(longitude - prev["longitude"]) > 0.01:
                    continue

           # Time από το αρχείο
            raw_time = get_value(row, [
                "OSD.flyTime",
                "flyTime",
                "time_seconds",
                "time",
                "Time",
                "CUSTOM.updateTime [local]",
                "DETAILS.timestamp"
            ], "")

            time_seconds_value = parse_time_to_seconds(raw_time)

            if time_seconds_value is None:
                time_seconds_value = len(flight_data) * 0.2

            time_text = format_time_from_seconds(time_seconds_value)
            # Altitude
            if get_value(row, ["height"], "") != "":
                height_m = safe_float(get_value(row, ["height"], 0))
                height_ft = height_m * 3.28084
            else:
                height_ft = safe_float(get_value(row, ["OSD.height [ft]"], 0))
                height_m = height_ft * 0.3048

            # VPS altitude
            vps_ft = get_value(row, ["OSD.vpsHeight [ft]", "vps_altitude"], "")

            # Home distance
            home_distance_ft = get_value(row, ["HOME.distance [ft]", "home_distance"], "")

            # Speed
            if get_value(row, ["speed_x"], "") != "":
                speed_x = safe_float(get_value(row, ["speed_x"], 0))
                speed_y = safe_float(get_value(row, ["speed_y"], 0))

                speed_ms = math.sqrt(speed_x ** 2 + speed_y ** 2)
                speed_mph = speed_ms * 2.23694
                speed_kmh = speed_ms * 3.6
            else:
                speed_mph = safe_float(get_value(row, ["OSD.hSpeed [MPH]"], 0))
                speed_kmh = speed_mph * 1.60934

            # GPS
            satellites = int(safe_float(get_value(row, ["OSD.gpsNum", "satellite_count"], 0)))

            # Flight mode
            raw_mode = get_value(row, ["OSD.flycState", "flight_mode"], "N/A")
            flight_mode = mode_names.get(str(raw_mode), str(raw_mode))

            # Battery
            battery = get_value(row, ["BATTERY.chargeLevel", "battery_percent"], "")
            battery_voltage = get_value(row, ["BATTERY.voltage [V]", "BATTERY.currentPV [V]", "battery_voltage"], "")

            cell_1 = get_value(row, ["BATTERY.cellVoltage1 [V]", "cell_1"], "")
            cell_2 = get_value(row, ["BATTERY.cellVoltage2 [V]", "cell_2"], "")
            cell_3 = get_value(row, ["BATTERY.cellVoltage3 [V]", "cell_3"], "")
            cell_4 = get_value(row, ["BATTERY.cellVoltage4 [V]", "cell_4"], "")

            existing_deviation = get_value(row, ["BATTERY.maxCellVoltageDeviation", "cell_deviation"], "")

            # Messages
            app_tip = get_value(row, ["APP.tip"], "")
            app_warning = get_value(row, ["APP.warning"], "")
            parser_message = get_value(row, ["message"], "")

            message = ""

            if parser_message:
                message = parser_message
            else:
                if app_tip:
                    message += app_tip

                if app_warning:
                    if message:
                        message += " "
                    message += app_warning

            if not message:
                if len(flight_data) == 0:
                    message = "Flight mode changed to Starting Motors."
                elif previous_mode and flight_mode != previous_mode:
                    message = f"Flight mode changed to {flight_mode}."

            point = {
                "time": time_text,
                "time_seconds": time_seconds_value,
                "latitude": latitude,
                "longitude": longitude,
                "flight_mode": flight_mode,
                "gps": f"{satellites} satellites" if satellites > 0 else "N/A",
                "altitude": height_m,
                "imu_altitude": format_ft(height_ft),
                "vps_altitude": format_ft(vps_ft),
                "speed": format_mph(speed_mph),
                "speed_display": f"{round(speed_kmh, 1)} km/h",
                "home_distance": format_ft(home_distance_ft),
                "battery": format_percent(battery),
                "battery_display": format_percent(battery),
                "battery_voltage": format_voltage(battery_voltage),
                "cell_1": format_voltage(cell_1),
                "cell_2": format_voltage(cell_2),
                "cell_3": format_voltage(cell_3),
                "cell_4": format_voltage(cell_4),
                "cell_deviation": calculate_cell_deviation(
                    [cell_1, cell_2, cell_3, cell_4],
                    existing_deviation
                ),
                "message": message
            }

            flight_data.append(point)
            previous_mode = flight_mode

    finally:
        file.close()

    return flight_data