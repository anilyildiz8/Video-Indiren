import os
import sys
import re


def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


def time_to_seconds(t_str):
    if not t_str:
        return None
    try:
        parts = str(t_str).split(':')
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
        elif len(parts) == 2:
            return int(parts[0]) * 60 + float(parts[1])
        else:
            return float(t_str)
    except Exception:
        return None


def format_bytes(b):
    if b is None or b == 0:
        return "0.0B"
    for unit in ['B', 'KB', 'MB', 'GB']:
        if abs(b) < 1024.0:
            return f"{b:3.1f}{unit}"
        b /= 1024.0
    return f"{b:.1f}TB"


def strip_ansi(text):
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    return ansi_escape.sub('', text)
