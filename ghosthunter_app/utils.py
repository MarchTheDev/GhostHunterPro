from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any


def safe_read_json(path: Path, default: Any) -> Any:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def safe_write_json(path: Path, data: Any) -> None:
    try:
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def path_size(path: str) -> int:
    total = 0
    try:
        if os.path.isfile(path):
            return os.path.getsize(path)
        for root, _, files in os.walk(path):
            for file_name in files:
                try:
                    total += os.path.getsize(os.path.join(root, file_name))
                except Exception:
                    pass
    except Exception:
        pass
    return total


def get_name_variations(text: str) -> list[str]:
    if not text:
        return []
    s = text.lower().strip()
    clean = re.sub(r"[^a-zA-Z0-9\s]", "", s)
    values = {
        text,
        s,
        clean,
        clean.replace(" ", "_"),
        clean.replace(" ", "-"),
        clean.replace(" ", ""),
        s.replace(" ", "_"),
        s.replace(" ", "-"),
    }
    return [value for value in values if value]


def normalize_name(text: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]", "", (text or "").lower())
