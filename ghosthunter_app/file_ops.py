from __future__ import annotations

import os
import shutil
import tempfile
from datetime import datetime
import subprocess
import webbrowser
from pathlib import Path
from typing import Any

from .scanner import ScanEngine
from .utils import path_size


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


def backup_path(path: str, game: dict[str, Any] | None = None) -> dict[str, Any]:
    """Copy one file/folder after the user chooses a backup destination."""
    source = Path(path)
    if not source.exists(): return {"ok": False, "error": "Path no longer exists."}
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk(); root.withdraw(); root.attributes("-topmost", True)
        destination = filedialog.askdirectory(title="Choose backup destination", initialdir=str(Path.home() / "Downloads"), parent=root)
        root.destroy()
    except Exception as exc:
        return {"ok": False, "error": f"Could not open backup folder picker: {exc}"}
    if not destination: return {"ok": False, "cancelled": True}
    game = game or {}
    safe_name = "".join(c if c not in '<>:"/\\|?*' else '_' for c in str(game.get("name") or "Game"))
    stamp = datetime.now().strftime("%d-%m-%Y %H-%M-%S")
    category = str(game.get("backup_type") or "Game data")
    safe_category = "".join(c if c not in '<>:"/\\|?*' else "_" for c in category)
    folder = Path(destination) / f"{safe_name} - {game.get('appid','Unknown')} - {safe_category} - {stamp}"
    target = folder / source.name
    if folder.exists(): return {"ok": False, "error": f"A backup folder named '{folder.name}' already exists."}
    try:
        # Use a system-created temporary directory to avoid Windows rename/
        # hidden-folder issues, then move it into the final visible location.
        temp_folder = Path(tempfile.mkdtemp(prefix="GhostHunterBackup_", dir=destination))
        temp_target = temp_folder / source.name
        if source.is_dir(): shutil.copytree(source, temp_target)
        else: shutil.copy2(source, temp_target)
        size = path_size(str(source)); units=["B","KB","MB","GB","TB"]; value=float(size); index=0
        while value >= 1024 and index < len(units)-1: value/=1024; index+=1
        info="\n".join(["Ghost Hunter Pro Backup","",f"Game Name: {game.get('name','')}",f"AppID: {game.get('appid','')}",f"Backup Type: {game.get('backup_type','Game data')}",f"Original Location: {source}",f"Backup Size: {value:.1f} {units[index]}"])
        (temp_folder/"Backup Info.txt").write_text(info,encoding="utf-8")
        shutil.move(str(temp_folder), str(folder))
        return {"ok":True,"destination":str(folder)}
    except Exception as exc:
        try:
            if 'temp_folder' in locals() and temp_folder.exists(): shutil.rmtree(temp_folder,ignore_errors=True)
        except Exception: pass
        return {"ok":False,"error":f"Backup copy failed: {exc}"}

def _backup_size_label(size: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]; value=float(size); index=0
    while value >= 1024 and index < len(units)-1: value/=1024; index+=1
    return f"{value:.1f} {units[index]}"


def backup_game(game: dict[str, Any]) -> dict[str, Any]:
    paths = [item for item in (game.get("paths") or []) if Path(str(item.get("path") or "")).exists()]
    if not paths: return {"ok": False, "error": "No existing paths are available to back up."}
    try:
        import tkinter as tk
        from tkinter import filedialog
        root=tk.Tk(); root.withdraw(); root.attributes("-topmost", True)
        destination=filedialog.askdirectory(title="Choose game backup destination", initialdir=str(Path.home()/"Downloads"), parent=root); root.destroy()
    except Exception as exc: return {"ok":False,"error":str(exc)}
    if not destination: return {"ok":False,"cancelled":True}
    safe_name="".join(c if c not in '<>:"/\\|?*' else '_' for c in str(game.get("name") or "Game"))
    stamp=datetime.now().strftime("%d-%m-%Y %H-%M-%S")
    folder=Path(destination)/f"{safe_name} - {game.get('appid','Unknown')} - Full Backup - {stamp}"
    if folder.exists(): return {"ok":False,"error":"That game backup folder already exists."}
    try:
        folder.mkdir(parents=True); lines=["Ghost Hunter Pro Backup","",f"Game Name: {game.get('name','')}",f"AppID: {game.get('appid','')}","", "Backed Up Items:",""]
        total=0
        for i,item in enumerate(paths,1):
            source=Path(str(item['path'])); target=folder/f"{i:02d} - {source.name}"; size=int(item.get('size') or path_size(str(source))); total+=size
            if source.is_dir(): shutil.copytree(source,target)
            else: shutil.copy2(source,target)
            lines += [f"{i}. {item.get('description') or item.get('category') or 'Game data'}",f"   Original Location: {source}",f"   Backup Folder/File: {target.name}",f"   Size: {_backup_size_label(size)}",""]
        lines += [f"Total Size: {_backup_size_label(total)}"]
        (folder/"Backup Info.txt").write_text("\n".join(lines),encoding="utf-8")
        return {"ok":True,"destination":str(folder)}
    except Exception as exc: return {"ok":False,"error":str(exc)}
