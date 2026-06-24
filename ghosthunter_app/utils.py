from __future__ import annotations

import html
import json
import os
import re
import urllib.parse
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


def placeholder_header_image(title: str, subtitle: str = "Ghost Hunter Pro") -> str:
    safe_title = html.escape((title or "Unknown Game")[:48])
    safe_subtitle = html.escape((subtitle or "")[:48])
    words = [part for part in re.split(r"\s+", title or "") if part]
    initials = "".join(word[0] for word in words[:3]).upper() or "GH"
    safe_initials = html.escape(initials[:3])
    svg = f"""
    <svg xmlns='http://www.w3.org/2000/svg' width='460' height='215' viewBox='0 0 460 215'>
      <defs>
        <linearGradient id='bg' x1='0' y1='0' x2='1' y2='1'>
          <stop offset='0%' stop-color='#10243c'/>
          <stop offset='55%' stop-color='#182e4e'/>
          <stop offset='100%' stop-color='#2b2450'/>
        </linearGradient>
        <radialGradient id='glow' cx='28%' cy='30%' r='60%'>
          <stop offset='0%' stop-color='rgba(51,221,255,0.28)'/>
          <stop offset='100%' stop-color='rgba(51,221,255,0)'/>
        </radialGradient>
      </defs>
      <rect width='460' height='215' rx='18' fill='url(#bg)'/>
      <rect width='460' height='215' rx='18' fill='url(#glow)'/>
      <rect x='18' y='18' width='104' height='104' rx='22' fill='rgba(255,255,255,0.08)' stroke='rgba(255,255,255,0.14)'/>
      <text x='70' y='84' text-anchor='middle' font-family='Segoe UI, Arial, sans-serif' font-size='38' font-weight='700' fill='#f1fbff'>{safe_initials}</text>
      <text x='18' y='156' font-family='Segoe UI, Arial, sans-serif' font-size='28' font-weight='700' fill='#eef7ff'>{safe_title}</text>
      <text x='18' y='184' font-family='Segoe UI, Arial, sans-serif' font-size='14' fill='#96a8c4'>{safe_subtitle}</text>
    </svg>
    """.strip()
    return "data:image/svg+xml;charset=UTF-8," + urllib.parse.quote(svg)
