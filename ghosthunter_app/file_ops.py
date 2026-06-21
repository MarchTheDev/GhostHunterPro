from __future__ import annotations

import os
import shutil
import subprocess
import webbrowser
from pathlib import Path
from typing import Any

from .scanner import ScanEngine


BLOCKED_NAMES = {
    "documents",
    "appdata",
    "local",
    "locallow",
    "windows",
    "system32",
    "program files",
    "program files (x86)",
    "programdata",
    "users",
    "steam",
}


def delete_paths(paths: list[str]) -> dict[str, Any]:
    collapsed = ScanEngine.collapse_selected_paths([str(path) for path in paths])
    deleted = 0
    failed: list[dict[str, str]] = []

    for path in sorted(collapsed, key=lambda value: len(os.path.normpath(value)), reverse=True):
        try:
            normalized = os.path.normpath(path)
            base = os.path.basename(normalized).lower()
            if base in BLOCKED_NAMES:
                failed.append({"path": path, "message": "Protected system folder"})
                continue
            if not os.path.exists(normalized):
                failed.append({"path": path, "message": "Path not found"})
                continue
            if os.path.isfile(normalized):
                os.remove(normalized)
            else:
                shutil.rmtree(normalized)
            deleted += 1
        except PermissionError:
            failed.append({"path": path, "message": "Permission denied. Try running as Administrator."})
        except Exception as exc:
            failed.append({"path": path, "message": str(exc)})

    return {"ok": True, "deleted": deleted, "failed": failed}


def open_path(path: str) -> dict[str, Any]:
    try:
        target = os.path.normpath(path)
        if not os.path.exists(target):
            return {"ok": False, "error": "Path not found"}
        if os.name == "nt":
            if os.path.isfile(target):
                subprocess.Popen(["explorer", f"/select,{target}"])
            else:
                os.startfile(target)  # type: ignore[attr-defined]
        else:
            folder = target if os.path.isdir(target) else os.path.dirname(target)
            webbrowser.open_new_tab(Path(folder).resolve().as_uri())
        return {"ok": True}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}
