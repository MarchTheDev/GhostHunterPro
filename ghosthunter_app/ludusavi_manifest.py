from __future__ import annotations

"""Fast, bundled Windows save-location index derived from Ludusavi's manifest.

Source manifest: https://github.com/mtkennerly/ludusavi-manifest (MIT License).
The source YAML is precompiled at build time because parsing its full 17 MB YAML
on every user machine would make Library loading unacceptably slow.
"""

import json
import glob
import os
from pathlib import Path
from typing import Any

from .utils import normalize_name, path_size

_INDEX_PATH = Path(__file__).resolve().parent / "data" / "ludusavi_windows_index.json"
_ENTRIES: list[dict[str, Any]] | None = None
_BY_APPID: dict[str, list[dict[str, Any]]] | None = None
_BY_NAME: dict[str, list[dict[str, Any]]] | None = None


def _load() -> None:
    global _ENTRIES, _BY_APPID, _BY_NAME
    if _ENTRIES is not None:
        return
    try:
        data = json.loads(_INDEX_PATH.read_text(encoding="utf-8"))
        _ENTRIES = data if isinstance(data, list) else []
    except Exception:
        _ENTRIES = []
    _BY_APPID, _BY_NAME = {}, {}
    for entry in _ENTRIES:
        appid = str(entry.get("appid") or "")
        name = normalize_name(str(entry.get("name") or ""))
        # steamExtra IDs are DLC/demo/edition IDs that belong to the primary
        # game. Index them under the same entry so they never become unknown.
        for steam_id in entry.get("appids") or ([appid] if appid else []):
            if str(steam_id):
                _BY_APPID.setdefault(str(steam_id), []).append(entry)
        for alias in entry.get("aliases") or [entry.get("name", "")]:
            token = normalize_name(str(alias))
            if token:
                _BY_NAME.setdefault(token, []).append(entry)


def _expand(value: str) -> str:
    home = os.environ.get("USERPROFILE") or str(Path.home())
    repl = {
        "<home>": home,
        "<winAppData>": os.environ.get("APPDATA", os.path.join(home, "AppData", "Roaming")),
        "<winLocalAppData>": os.environ.get("LOCALAPPDATA", os.path.join(home, "AppData", "Local")),
        "<winDocuments>": os.path.join(home, "Documents"),
        "<winPublic>": os.environ.get("PUBLIC", r"C:\Users\Public"),
        "<winSavedGames>": os.path.join(home, "Saved Games"),
        "<winProgramData>": os.environ.get("PROGRAMDATA", r"C:\ProgramData"),
    }
    for key, replacement in repl.items():
        value = value.replace(key, replacement)
    return os.path.normpath(os.path.expandvars(value.replace("/", os.sep)))


def discover_existing_locallow_games() -> dict[str, dict[str, Any]]:
    """Find manifest-backed games from existing LocalLow paths.

    Unlike a title-folder guess, this works in reverse: a LocalLow folder is
    accepted only when it exactly matches a maintained Ludusavi manifest path.
    This lets Library discover save-only/uninstalled games safely.
    """
    _load()
    found: dict[str, dict[str, Any]] = {}
    for entry in _ENTRIES or []:
        appid = str(entry.get("appid") or "")
        if not appid:
            continue
        matches: list[dict[str, Any]] = []
        for item in entry.get("paths") or []:
            raw = str(item.get("path") or "")
            if "locallow" not in raw.lower():
                continue
            path = _expand(raw)
            if not os.path.exists(path):
                continue
            matches.append({"path": path, "category": item.get("category", "Save Files"), "description": "Save folder", "source": "ludusavi_manifest", "risk": "caution", "size": path_size(path), "is_dir": os.path.isdir(path)})
        if matches:
            found[appid] = {"appid": appid, "name": str(entry.get("name") or f"Game files (AppID: {appid})"), "paths": matches, "sources": [], "manifest_backed": True}
    return found


def discover_existing_manifest_games() -> dict[str, dict[str, Any]]:
    """Reverse-match exact existing manifest paths across all Windows roots."""
    _load()
    found: dict[str, dict[str, Any]] = {}
    for entry in _ENTRIES or []:
        appid = str(entry.get("appid") or "")
        if not appid:
            continue
        matches = []
        for item in entry.get("paths") or []:
            pattern = _expand(str(item.get("path") or ""))
            existing = glob.glob(pattern) if any(ch in pattern for ch in "*?") else ([pattern] if os.path.exists(pattern) else [])
            for path in existing:
                matches.append({"path": path, "category": item.get("category", "Save Files"), "description": "Save folder", "source": "ludusavi_manifest", "risk": "caution", "size": path_size(path), "is_dir": os.path.isdir(path)})
        if matches:
            found[appid] = {"appid": appid, "name": str(entry.get("name") or f"Game files (AppID: {appid})"), "paths": matches, "sources": [], "manifest_backed": True}
    return found


def resolve_alias(name: str) -> dict[str, str] | None:
    _load()
    matches = (_BY_NAME or {}).get(normalize_name(name), [])
    if not matches:
        return None
    entry = matches[0]
    appid = str(entry.get("appid") or "")
    return {"appid": appid, "name": str(entry.get("name") or name)} if appid else None


def _container_for_wildcard(pattern: str, matched: str) -> str:
    """Prefer the game container over a deep matched save file."""
    parts = Path(pattern).parts
    generic = {"saved", "savegames", "saves", "profiles", "profile", "config", "configs", "characters"}
    for index, part in enumerate(parts):
        if part.lower() in generic and index > 0:
            candidate = Path(*parts[:index])
            if candidate.is_dir():
                return str(candidate)
    return matched


def find_paths(game: dict[str, Any]) -> list[dict[str, Any]]:
    _load()
    appid = str(game.get("appid") or "")
    name = normalize_name(str(game.get("name") or ""))
    entries = list((_BY_APPID or {}).get(appid, [])) or list((_BY_NAME or {}).get(name, []))
    output: list[dict[str, Any]] = []
    seen: set[str] = set()
    for entry in entries:
        for item in entry.get("paths") or []:
            pattern = _expand(str(item.get("path") or ""))
            existing = glob.glob(pattern) if any(ch in pattern for ch in "*?") else ([pattern] if os.path.exists(pattern) else [])
            for path in existing:
                if any(ch in pattern for ch in "*?"):
                    path = _container_for_wildcard(pattern, path)
                key = os.path.normcase(path)
                if key in seen:
                    continue
                seen.add(key)
                output.append({"path": path, "category": item.get("category", "Save Files"), "description": "Save folder" if item.get("category") == "Save Files" else "Configuration folder", "source": "ludusavi_manifest", "risk": "caution", "size": path_size(path), "is_dir": os.path.isdir(path)})
    return output

def component_game_index() -> dict[str, dict[str, str]]:
    """Exact folder-name aliases from the manifest, for safe reverse discovery."""
    _load()
    out: dict[str, dict[str, str]] = {}
    for entry in _ENTRIES or []:
        appid = str(entry.get("appid") or "")
        name = str(entry.get("name") or "")
        token = normalize_name(name)
        if not appid or not token:
            continue
        out.setdefault(token, {"appid": appid, "name": name})
        if token.startswith("the") and len(token) > 3:
            out.setdefault(token[3:], {"appid": appid, "name": name})
    return out
