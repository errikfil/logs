#!/usr/bin/env python3
"""
DJI Flight Log Parser/Decryptor
===============================

Parses DJI flight record .txt files and extracts flight data.
Supports AES-encrypted logs (version 13+) with DJI API key.

Usage:
    python dji_log_parser.py <input_file> --api-key YOUR_KEY [--all]
"""

import struct
import os
import sys
import json
import csv
import argparse
import base64
from pathlib import Path
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass, asdict
from enum import IntEnum
import math

# CRC64 implementation matching the Rust crc64 crate
# Polynomial: 0x95AC9329AC4BC9B5 (reflected ECMA-XZ variant)
CRC64_TABLE = None

def _init_crc64_table():
    global CRC64_TABLE
    if CRC64_TABLE is not None:
        return

    POLY = 0x95AC9329AC4BC9B5
    CRC64_TABLE = []
    for i in range(256):
        crc = i
        for _ in range(8):
            if crc & 1:
                crc = (crc >> 1) ^ POLY
            else:
                crc >>= 1
        CRC64_TABLE.append(crc)

def crc64_jones(init: int, data: bytes) -> int:
    """CRC64-Jones as used by the crc64 Rust crate

    The Rust crate uses the init value directly as starting CRC,
    NOT XOR'd with 0xFFFFFFFFFFFFFFFF.
    """
    _init_crc64_table()
    crc = init & 0xFFFFFFFFFFFFFFFF
    for byte in data:
        crc = CRC64_TABLE[(crc ^ byte) & 0xFF] ^ (crc >> 8)
    return crc

# Try to import optional dependencies
try:
    from Crypto.Cipher import AES
    HAS_CRYPTO = True
except ImportError:
    HAS_CRYPTO = False

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False


DJI_API_ENDPOINT = "https://dev.dji.com/openapi/v1/flight-records/keychains"
DJI_API_KEY = "3037b76a7c8efbdaf916dbf0937d813"


FEATURE_POINT_NAMES = {
    1: "FR_Standardization_Feature_Base_1",
    2: "FR_Standardization_Feature_Vision_2",
    3: "FR_Standardization_Feature_Waypoint_3",
    4: "FR_Standardization_Feature_Agriculture_4",
    5: "FR_Standardization_Feature_AirLink_5",
    6: "FR_Standardization_Feature_AfterSales_6",
    7: "FR_Standardization_Feature_DJIFlyCustom_7",
    8: "FR_Standardization_Feature_Plaintext_8",
    9: "FR_Standardization_Feature_FlightHub_9",
    10: "FR_Standardization_Feature_Gimbal_10",
    11: "FR_Standardization_Feature_RC_11",
    12: "FR_Standardization_Feature_Camera_12",
    13: "FR_Standardization_Feature_Battery_13",
    14: "FR_Standardization_Feature_FlySafe_14",
    15: "FR_Standardization_Feature_Security_15",
}


class RecordType(IntEnum):
    OSD = 1
    HOME = 2
    GIMBAL = 3
    RC = 4
    CUSTOM = 5
    DEFORM = 6
    CENTER_BATTERY = 7
    SMART_BATTERY = 8
    APP_TIP = 9
    APP_WARN = 10
    RC_GPS = 11
    RC_DEBUG = 12
    RECOVER = 13
    APP_GPS = 14
    FIRMWARE = 15
    KEY_STORAGE = 56
    KEY_STORAGE_RECOVER = 50


@dataclass
class FileInfo:
    file_size: int = 0
    version: int = 0
    api_version: int = 0
    department: int = 0
    encryption_type: str = ""
    records_offset: int = 0
    records_end: int = 0


@dataclass
class FlightFrame:
    index: int = 0
    latitude: float = 0.0
    longitude: float = 0.0
    height: float = 0.0
    home_distance: float = 0.0
    vps_altitude: float = 0.0
    time_seconds: float = 0.0

    rc_throttle: float = 0.0
    rc_yaw: float = 0.0
    rc_pitch: float = 0.0
    rc_roll: float = 0.0

    speed_x: float = 0.0
    speed_y: float = 0.0
    speed_z: float = 0.0

    pitch: float = 0.0
    roll: float = 0.0
    yaw: float = 0.0

    satellite_count: int = 0
    flight_mode: int = 0

    is_motor_on: bool = False
    is_flying: bool = False

    battery_percent: float = 0.0
    battery_voltage: float = 0.0

    cell_1: float = 0.0
    cell_2: float = 0.0
    cell_3: float = 0.0
    cell_4: float = 0.0

    message: str = ""


class XorDecoder:
    """XOR decoder using CRC64-Jones"""

    def __init__(self, data: bytes, record_type: int):
        if len(data) < 1:
            self.decoded = bytes()
            return

        first_byte = data[0]
        content = data[1:]

        # Generate XOR key using CRC64-Jones
        magic = 0x123456789ABCDEF0
        combined = (first_byte + record_type) & 0xFF
        magic_mult = (magic * first_byte) & 0xFFFFFFFFFFFFFFFF
        key_int = crc64_jones(combined, magic_mult.to_bytes(8, 'little'))
        key = key_int.to_bytes(8, 'little')

        self.decoded = bytes(b ^ key[i % 8] for i, b in enumerate(content))


class DJILogParser:
    PREFIX_SIZE = 100


    def _parse_rc(self, data: bytes):
        try:
            print("RC DATA LEN:", len(data))
            print("RC RAW:", data[:40].hex())

            if len(data) < 8:
                return None

            rc = {
                "rc_roll": struct.unpack('<h', data[0:2])[0],
                "rc_pitch": struct.unpack('<h', data[2:4])[0],
                "rc_throttle": struct.unpack('<h', data[4:6])[0],
                "rc_yaw": struct.unpack('<h', data[6:8])[0],
            }

            print("RC PARSED:", rc)
            return rc

        except Exception as e:
            print("RC ERROR:", e)
            return None

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or DJI_API_KEY
        self.file_info = FileInfo()
        self.frames: List[FlightFrame] = []
        self._data: bytes = b''
        self._keychains: Dict[int, Tuple[bytes, bytes]] = {}
        self._keychain_entries: List[Dict] = []
        self.last_battery = {
            "battery_percent": 0.0,
            "battery_voltage": 0.0,
            "cell_1": 0.0,
            "cell_2": 0.0,
            "cell_3": 0.0,
            "cell_4": 0.0,
        }
        self.last_rc = {
            "rc_roll": 0,
            "rc_pitch": 0,
            "rc_throttle": 0,
            "rc_yaw": 0,
        }

        self.last_message = ""
        self.home_latitude = None
        self.home_longitude = None

    def parse_file(self, filepath: str) -> bool:
        path = Path(filepath)
        if not path.exists():
            print(f"Error: File not found: {filepath}")
            return False

        print(f"Parsing: {path.name}")
        self.file_info.file_size = path.stat().st_size
        print(f"File size: {self.file_info.file_size:,} bytes")

        with open(filepath, 'rb') as f:
            self._data = f.read()

        return self._parse()

    def _parse(self) -> bool:
        self._read_prefix()

        print(f"Version: {self.file_info.version}, API: {self.file_info.api_version}")
        print(f"Department: {self.file_info.department}")
        print(f"Encryption: {self.file_info.encryption_type}")

        if self.file_info.encryption_type == "aes":
            if self.api_key:
                if self._fetch_keychains():
                    return self._parse_aes_records()
                return False
            else:
                print("\nAPI key required. Use --api-key YOUR_KEY")
                return False
        else:
            return self._parse_xor_records()

    def _read_prefix(self):
        if len(self._data) < self.PREFIX_SIZE:
            return

        detail_offset = struct.unpack('<Q', self._data[0:8])[0]
        self.file_info.version = self._data[10]

        if self.file_info.version < 7:
            self.file_info.encryption_type = "none"
            self.file_info.records_offset = 12 if self.file_info.version < 6 else self.PREFIX_SIZE
            self.file_info.records_end = detail_offset
        elif self.file_info.version <= 12:
            self.file_info.encryption_type = "xor"
            self.file_info.records_offset = self.PREFIX_SIZE + (436 if self.file_info.version == 12 else 0)
            self.file_info.records_end = self.file_info.file_size if self.file_info.version == 12 else detail_offset
        else:
            self.file_info.encryption_type = "aes"
            self._read_auxiliary_blocks()
            self.file_info.records_offset = detail_offset
            self.file_info.records_end = self.file_info.file_size

    def _read_auxiliary_blocks(self):
        cursor = self.PREFIX_SIZE
        detail_offset = struct.unpack('<Q', self._data[0:8])[0]

        while cursor < min(detail_offset, len(self._data) - 3):
            magic = self._data[cursor]
            length = struct.unpack('<H', self._data[cursor+1:cursor+3])[0]

            if magic == 1:  # Version block
                block_data = self._data[cursor+3:cursor+3+length]
                if len(block_data) >= 3:
                    self.file_info.api_version = struct.unpack('<H', block_data[0:2])[0]
                    self.file_info.department = block_data[2]
            elif magic not in [0, 1]:
                break

            cursor += 3 + length

    def _extract_keychains(self):
        cursor = self.file_info.records_offset

        while cursor < self.file_info.records_end - 5:
            rec_type = self._data[cursor]
            rec_len = struct.unpack('<H', self._data[cursor+1:cursor+3])[0]

            if rec_len == 0 or rec_len > 1000 or cursor + 3 + rec_len + 1 > len(self._data):
                cursor += 1
                continue

            end_pos = cursor + 3 + rec_len
            if end_pos >= len(self._data) or self._data[end_pos] != 0xFF:
                cursor += 1
                continue

            if rec_type == RecordType.KEY_STORAGE:
                rec_data = self._data[cursor+3:cursor+3+rec_len]
                decoder = XorDecoder(rec_data, rec_type)
                decoded = decoder.decoded

                if len(decoded) >= 4:
                    feature_point = struct.unpack('<H', decoded[0:2])[0]
                    data_length = struct.unpack('<H', decoded[2:4])[0]

                    if 1 <= feature_point <= 15 and data_length <= len(decoded) - 4:
                        key_data = decoded[4:4+data_length]
                        self._keychain_entries.append({
                            'feature_point': feature_point,
                            'ciphertext': key_data
                        })

            cursor += 3 + rec_len + 1

    def _fetch_keychains(self) -> bool:
        if not HAS_REQUESTS or not HAS_CRYPTO:
            print("Error: Install requests and pycryptodome")
            return False

        print("\nExtracting keychains...")
        self._extract_keychains()

        if not self._keychain_entries:
            print("No keychain entries found")
            return False

        print(f"Found {len(self._keychain_entries)} entries")

        keychains_array = [[{
            "featurePoint": FEATURE_POINT_NAMES.get(e['feature_point'], f"Unknown_{e['feature_point']}"),
            "aesCiphertext": base64.b64encode(e['ciphertext']).decode()
        } for e in self._keychain_entries]]

        api_version = self.file_info.api_version or 4
        department = self.file_info.department or 3

        print(f"Calling DJI API (v{api_version}, dept {department})...")

        try:
            response = requests.post(
                DJI_API_ENDPOINT,
                headers={"Content-Type": "application/json", "Api-Key": self.api_key},
                json={"version": api_version, "department": department, "keychainsArray": keychains_array},
                timeout=30
            )

            if response.status_code != 200:
                print(f"API error: {response.status_code}")
                return False

            result = response.json()
            if result.get("result", {}).get("code") != 0:
                print(f"API error: {result.get('result', {}).get('msg')}")
                return False

            for group in result.get("data", []):
                for entry in group:
                    try:
                        fp = int(entry["featurePoint"].split("_")[-1])
                        iv = base64.b64decode(entry["aesIv"])
                        key = base64.b64decode(entry["aesKey"])
                        self._keychains[fp] = (iv, key)
                    except Exception as e:
                        pass

            print(f"Got {len(self._keychains)} keys")
            return len(self._keychains) > 0

        except Exception as e:
            print(f"Error: {e}")
            return False

    def _get_feature_point(self, rec_type: int) -> int:
        v = self.file_info.version
        mapping = {
            1: 1, 2: 1, 3: 10 if v > 13 else 1, 4: 11 if v > 13 else 1,
            5: 7, 6: 1, 7: 13 if v > 13 else 1, 8: 13 if v > 13 else 1,
            9: 7, 10: 7, 11: 11 if v > 13 else 1, 13: 1, 14: 1, 15: 1,
        }
        return mapping.get(rec_type, 8)

    def _decrypt_aes(self, data: bytes, fp: int) -> Optional[bytes]:
        if fp not in self._keychains:
            fp = 1 if 1 in self._keychains else (8 if 8 in self._keychains else None)
            if fp is None:
                return None

        iv, key = self._keychains[fp]
        try:
            # Capture next IV BEFORE decryption (last 16 bytes of ciphertext)
            next_iv = data[-16:] if len(data) >= 16 else iv

            # Pad to block size if needed
            padded_data = data
            if len(data) % 16:
                padded_data = data + bytes(16 - len(data) % 16)

            cipher = AES.new(key, AES.MODE_CBC, iv)
            dec = cipher.decrypt(padded_data)

            # Update IV for next decryption with this feature point
            self._keychains[fp] = (next_iv, key)

            # Remove PKCS7 padding
            pad = dec[-1]
            if 0 < pad <= 16 and all(b == pad for b in dec[-pad:]):
                return dec[:-pad]
            return dec
        except:
            return None

    def _parse_aes_records(self) -> bool:
        print("\nParsing records...")
        cursor = self.file_info.records_offset
        idx = 0
        record_counts = {}
    
        while cursor < self.file_info.records_end - 5:
            rec_type = self._data[cursor]
            rec_len = struct.unpack('<H', self._data[cursor+1:cursor+3])[0]
            record_counts[rec_type] = record_counts.get(rec_type, 0) + 1


            if rec_len == 0 or rec_len > 1000 or cursor + 3 + rec_len + 1 > len(self._data):
                cursor += 1
                continue

            if self._data[cursor + 3 + rec_len] != 0xFF:
                cursor += 1
                continue

            dec = None

            if rec_type not in [RecordType.KEY_STORAGE, RecordType.KEY_STORAGE_RECOVER]:
                rec_data = self._data[cursor+3:cursor+3+rec_len]
                decoder = XorDecoder(rec_data, rec_type)

                xor_dec = decoder.decoded[:-1] if len(decoder.decoded) > 1 else decoder.decoded

                fp = self._get_feature_point(rec_type)

                if fp != 8:
                    dec = self._decrypt_aes(xor_dec, fp)
                else:
                    dec = xor_dec

            if dec:
                if rec_type in [RecordType.SMART_BATTERY, RecordType.CENTER_BATTERY]:
                    self._parse_battery(dec)

                elif rec_type in [RecordType.APP_TIP, RecordType.APP_WARN]:
                    self._parse_message(dec)

                elif rec_type == RecordType.RC:
                    rc = self._parse_rc(dec)

                    if rc:
                        self.last_rc.update(rc)

                elif rec_type == RecordType.OSD and len(dec) >= 30:
                    frame = self._parse_osd(dec, idx)

                    if frame:
                        if frame and self._valid_gps(frame):
                            if self.home_latitude is None or self.home_longitude is None:
                                self.home_latitude = frame.latitude
                                self.home_longitude = frame.longitude

                            frame.time_seconds = round((frame.index - 0.5) * 0.2, 1)
                            frame.home_distance = self._calculate_distance_m(
                                self.home_latitude,
                                self.home_longitude,
                                frame.latitude,
                                frame.longitude
                            )

                        frame.battery_percent = self.last_battery["battery_percent"]
                        frame.battery_percent = self.last_battery["battery_percent"]
                        frame.battery_voltage = self.last_battery["battery_voltage"]

                        frame.cell_1 = self.last_battery["cell_1"]
                        frame.cell_2 = self.last_battery["cell_2"]
                        frame.cell_3 = self.last_battery["cell_3"]
                        frame.cell_4 = self.last_battery["cell_4"]

                        frame.message = self.last_message

                        frame.rc_roll = self.last_rc["rc_roll"]

                        frame.rc_pitch = self.last_rc["rc_pitch"]
                        frame.rc_throttle = self.last_rc["rc_throttle"]
                        frame.rc_yaw = self.last_rc["rc_yaw"]

                        self.frames.append(frame)
                        idx += 1

                        self.last_message = ""

            cursor += 3 + rec_len + 1
        
        print(f"Found {len(self.frames)} frames")
        return len(self.frames) > 0

    def _parse_xor_records(self) -> bool:
        print("\nParsing records...")
        cursor = self.file_info.records_offset
        idx = 0
        version = self.file_info.version
        record_counts = {}

        while cursor < self.file_info.records_end - 3:
            rec_type = self._data[cursor]
            rec_len = (
                self._data[cursor + 1]
                if version <= 12
                else struct.unpack('<H', self._data[cursor + 1:cursor + 3])[0]
            )
            hdr = 2 if version <= 12 else 3

            record_counts[rec_type] = record_counts.get(rec_type, 0) + 1

            if rec_len == 0 or rec_len > 200 or cursor + hdr + rec_len > len(self._data):
                cursor += 1
                continue

            rec_data = self._data[cursor + hdr:cursor + hdr + rec_len]
            dec = XorDecoder(rec_data, rec_type).decoded if version >= 7 else rec_data

            if rec_type in [RecordType.SMART_BATTERY, RecordType.CENTER_BATTERY]:
                self._parse_battery(dec)

            elif rec_type in [RecordType.APP_TIP, RecordType.APP_WARN]:
                self._parse_message(dec)

            elif rec_type == RecordType.RC:
                rc = self._parse_rc(dec)
                if rc:
                    self.last_rc.update(rc)

            elif rec_type == RecordType.OSD and len(dec) >= 30:
                frame = self._parse_osd(dec, idx)

                if frame and self._valid_gps(frame):
                    if self.home_latitude is None or self.home_longitude is None:
                        self.home_latitude = frame.latitude
                        self.home_longitude = frame.longitude

                    frame.home_distance = self._calculate_distance_m(
                        self.home_latitude,
                        self.home_longitude,
                        frame.latitude,
                        frame.longitude
                    )

                    frame.battery_percent = self.last_battery["battery_percent"]
                    frame.battery_voltage = self.last_battery["battery_voltage"]

                    frame.time_seconds = round((frame.index - 0.5) * 0.2, 1)
                    frame.cell_1 = self.last_battery["cell_1"]
                    frame.cell_2 = self.last_battery["cell_2"]
                    frame.cell_3 = self.last_battery["cell_3"]
                    frame.cell_4 = self.last_battery["cell_4"]

                    frame.rc_roll = self.last_rc["rc_roll"]
                    frame.rc_pitch = self.last_rc["rc_pitch"]
                    frame.rc_throttle = self.last_rc["rc_throttle"]
                    frame.rc_yaw = self.last_rc["rc_yaw"]

                    frame.message = self.last_message

                    self.frames.append(frame)
                    idx += 1
                    self.last_message = ""

            cursor += hdr + rec_len + (1 if version >= 13 else 0)

        print("RECORD TYPES FOUND:")
        for k, count in sorted(record_counts.items()):
            print("TYPE:", k, "COUNT:", count)

        print(f"Found {len(self.frames)} frames")
        return len(self.frames) > 0
    
    def _calculate_distance_m(self, lat1, lon1, lat2, lon2):
        r = 6371000  # Earth radius in meters

        phi1 = math.radians(lat1)
        phi2 = math.radians(lat2)

        delta_phi = math.radians(lat2 - lat1)
        delta_lambda = math.radians(lon2 - lon1)

        a = (
            math.sin(delta_phi / 2) ** 2
            + math.cos(phi1) * math.cos(phi2)
            * math.sin(delta_lambda / 2) ** 2
        )

        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

        return r * c

    def _valid_gps(self, f: FlightFrame) -> bool:
        return -90 <= f.latitude <= 90 and -180 <= f.longitude <= 180 and (f.latitude != 0 or f.longitude != 0)

    def _parse_osd(self, data: bytes, idx: int) -> Optional[FlightFrame]:
        try:
            lon = math.degrees(struct.unpack('<d', data[0:8])[0])
            lat = math.degrees(struct.unpack('<d', data[8:16])[0])
            
            if idx % 500 == 0:
                print("IDX:", idx, "LEN:", len(data))
                print("OSD HEX 30-100:", data[30:100].hex())

            
            return FlightFrame(
                index=idx + 1,
                longitude=lon, latitude=lat,
                height=struct.unpack('<h', data[16:18])[0] * 0.1,
                speed_x=struct.unpack('<h', data[18:20])[0] * 0.01,
                speed_y=struct.unpack('<h', data[20:22])[0] * 0.01,
                speed_z=struct.unpack('<h', data[22:24])[0] * 0.01,
                pitch=struct.unpack('<h', data[24:26])[0] * 0.1,
                roll=struct.unpack('<h', data[26:28])[0] * 0.1,
                yaw=struct.unpack('<h', data[28:30])[0] * 0.1,
                is_flying=bool(data[30] & 0x01) if len(data) > 30 else False,
                is_motor_on=bool(data[30] & 0x10) if len(data) > 30 else False,
                flight_mode=data[32] if len(data) > 32 else 0,
                satellite_count=data[33] if len(data) > 33 else 0,
            )
        except:
            return None

    def _parse_battery(self, data: bytes):
        try:
            battery = {}

            if len(data) >= 12:
                voltage_mv = struct.unpack('<H', data[0:2])[0]
                percent = data[11] if len(data) > 11 else 0

                battery["battery_voltage"] = round(voltage_mv / 1000, 3)
                battery["battery_percent"] = float(percent)

            if len(data) >= 20:
                battery["cell_1"] = round(struct.unpack('<H', data[12:14])[0] / 1000, 3)
                battery["cell_2"] = round(struct.unpack('<H', data[14:16])[0] / 1000, 3)
                battery["cell_3"] = round(struct.unpack('<H', data[16:18])[0] / 1000, 3)
                battery["cell_4"] = round(struct.unpack('<H', data[18:20])[0] / 1000, 3)

            for key, value in battery.items():
                if value:
                    self.last_battery[key] = value

        except Exception:
            pass

    def _parse_message(self, data: bytes):
        try:
            text = data.decode("utf-8", errors="ignore")
            text = text.replace("\x00", " ").strip()

            if text:
                clean = " ".join(text.split())

                if len(clean) > 5:
                    self.last_message = clean[:250]

        except Exception:
            pass

    def export_csv(self, path: str):
        valid = [f for f in self.frames if self._valid_gps(f)]
        if not valid:
            print("No valid GPS frames to export")
            return
        with open(path, 'w', newline='') as f:
            w = csv.DictWriter(f, asdict(valid[0]).keys())
            w.writeheader()
            for fr in valid:
                w.writerow(asdict(fr))
        print(f"Exported {len(valid)} frames to {path}")

    def export_json(self, path: str):
        valid = [f for f in self.frames if self._valid_gps(f)]
        with open(path, 'w') as f:
            json.dump({'info': asdict(self.file_info), 'frames': [asdict(fr) for fr in valid]}, f, indent=2)
        print(f"Exported {len(valid)} frames to {path}")

    def export_kml(self, path: str):
        valid = [f for f in self.frames if self._valid_gps(f)]
        if not valid:
            print("No valid GPS frames to export")
            return
        coords = '\n'.join(f"{f.longitude},{f.latitude},{f.height}" for f in valid)
        with open(path, 'w') as f:
            f.write(f'<?xml version="1.0"?>\n<kml xmlns="http://www.opengis.net/kml/2.2"><Document><Placemark><LineString><coordinates>\n{coords}\n</coordinates></LineString></Placemark></Document></kml>')
        print(f"Exported {len(valid)} frames to {path}")

    def print_summary(self):
        print(f"\n{'='*50}\nSUMMARY\n{'='*50}")
        print(f"Total frames: {len(self.frames)}")
        # Filter to valid GPS frames
        valid = [f for f in self.frames if self._valid_gps(f)]
        print(f"Valid GPS frames: {len(valid)}")
        if valid:
            print(f"Max height: {max(f.height for f in valid):.1f}m")
            print(f"Max speed: {max((f.speed_x**2 + f.speed_y**2)**0.5 for f in valid):.1f}m/s")
            print(f"Start: {valid[0].latitude:.6f}, {valid[0].longitude:.6f}")
            print(f"End: {valid[-1].latitude:.6f}, {valid[-1].longitude:.6f}")
        print('='*50)

def frames_to_flight_data(frames):
    flight_data = []
    previous_mode = None

    mode_names = {
        0: "Manual",
        1: "Atti",
        2: "P-GPS",
        3: "P-GPS (Brake)",
        6: "Tripod",
        10: "Sport",
        11: "GPS",
        26: "Starting Motors",
    }

    for i, f in enumerate(frames):
        speed_ms = math.sqrt(f.speed_x ** 2 + f.speed_y ** 2)
        speed_kmh = speed_ms * 3.6
        speed_mph = speed_ms * 2.23694

        first_time = getattr(frames[0], "time_seconds", 0) if frames else 0
        time_seconds_total = getattr(f, "time_seconds", i * 0.2)
        time_seconds_total = max(0, time_seconds_total - first_time)

        minutes = int(time_seconds_total // 60)
        seconds = round(time_seconds_total % 60, 1)

        flight_mode = mode_names.get(f.flight_mode, str(f.flight_mode))

        message = f.message

        if not message:
            if i == 0:
                message = "Flight mode changed to Starting Motors."
            elif previous_mode and flight_mode != previous_mode:
                message = f"Flight mode changed to {flight_mode}."

        cells = [f.cell_1, f.cell_2, f.cell_3, f.cell_4]
        valid_cells = [c for c in cells if c and c > 0]

        if len(valid_cells) >= 2:
            cell_deviation = f"{round(max(valid_cells) - min(valid_cells), 3)} V"
        else:
            cell_deviation = "N/A"

        point = {
            "time": f"{minutes}m {seconds}s",
            "latitude": f.latitude,
            "longitude": f.longitude,
            "rc_roll": f.rc_roll,
            "rc_pitch": f.rc_pitch,
            "rc_throttle": f.rc_throttle,
            "rc_yaw": f.rc_yaw,
            "pitch": f.pitch,
            "roll": f.roll,
            "yaw": f.yaw,
            "speed_x": f.speed_x,
            "speed_y": f.speed_y,
            "speed_z": f.speed_z,
            "flight_mode": flight_mode,
            "gps": f"{f.satellite_count} satellites" if f.satellite_count else "N/A",
            "altitude": f.height,
            "imu_altitude": f"{round(f.height * 3.28084, 1)} ft",
            "vps_altitude": f"{round(f.vps_altitude * 3.28084, 1)} ft" if f.vps_altitude else "N/A",            "speed": f"{round(speed_mph, 1)} mph",
            "speed_display": f"{round(speed_kmh, 1)} km/h",
            "home_distance": f"{round(f.home_distance * 3.28084, 1)} ft" if f.home_distance else "0 ft",            "battery": f"{int(f.battery_percent)}%" if f.battery_percent else "N/A",
            "battery_display": f"{int(f.battery_percent)}%" if f.battery_percent else "N/A",
            "battery_voltage": f"{round(f.battery_voltage, 3)} V" if f.battery_voltage else "N/A",
            "cell_1": f"{round(f.cell_1, 3)} V" if f.cell_1 else "N/A",
            "cell_2": f"{round(f.cell_2, 3)} V" if f.cell_2 else "N/A",
            "cell_3": f"{round(f.cell_3, 3)} V" if f.cell_3 else "N/A",
            "cell_4": f"{round(f.cell_4, 3)} V" if f.cell_4 else "N/A",
            "cell_deviation": cell_deviation,
            "message": message
        }

        flight_data.append(point)
        previous_mode = flight_mode

    return flight_data

def main():
    p = argparse.ArgumentParser(description='DJI Log Parser')
    p.add_argument('input')
    p.add_argument('--api-key', default=DJI_API_KEY, help='DJI API key (optional, built-in key used by default)')
    p.add_argument('--output', '-o', default='.')
    p.add_argument('--csv', action='store_true')
    p.add_argument('--json', action='store_true')
    p.add_argument('--kml', action='store_true')
    p.add_argument('--all', action='store_true')
    args = p.parse_args()

    parser = DJILogParser(args.api_key)
    if parser.parse_file(args.input):
        parser.print_summary()
        if args.all or args.csv or args.json or args.kml:
            os.makedirs(args.output, exist_ok=True)
            base = Path(args.input).stem
            if args.all or args.json:
                parser.export_json(f"{args.output}/{base}.json")
            if args.all or args.csv:
                parser.export_csv(f"{args.output}/{base}.csv")
            if args.all or args.kml:
                parser.export_kml(f"{args.output}/{base}.kml")


if __name__ == '__main__':
    main()
