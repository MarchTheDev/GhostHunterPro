from __future__ import annotations

import sys
from pathlib import Path

from .backend import Backend
from .config import APP_TITLE, UI_PATH


def main() -> None:
    try:
        import webview  # type: ignore
    except Exception:
        print("pywebview is required to run Ghost Hunter Pro.")
        print("Install it with: pip install pywebview")
        input("\nPress Enter to close...")
        return

    if not UI_PATH.exists():
        print(f"UI file not found: {UI_PATH}")
        input("\nPress Enter to close...")
        return

    backend = Backend()
    webview.create_window(
        APP_TITLE,
        url=UI_PATH.resolve().as_uri(),
        js_api=backend,
        width=1280,
        height=900,
        min_size=(980, 720),
        text_select=False,
    )
    webview.start(debug=False)
