from __future__ import annotations

import os
import webbrowser
from typing import Any

from .file_ops import delete_paths as delete_paths_impl
from .file_ops import open_path as open_path_impl
from .scanner import ScanEngine
from .steam_api import SteamAPI
from .storage import StateStore


class Backend:
    def __init__(self) -> None:
        self.state = StateStore()
        self.steam = SteamAPI()

    def _save(self) -> None:
        self.state.save()
        self.steam.save_cache()

    def ping(self) -> dict[str, Any]:
        return {"ok": True, "desktop": True}

    def open_url(self, url: str) -> dict[str, Any]:
        try:
            webbrowser.open_new_tab(url)
            return {"ok": True}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def open_path(self, path: str) -> dict[str, Any]:
        return open_path_impl(path)

    def set_archived(self, appid: str, archived: bool) -> dict[str, Any]:
        self.state.set_archived(str(appid), archived)
        self._save()
        return {"ok": True, "appid": str(appid), "archived": archived}

    def get_history(self) -> list[dict[str, Any]]:
        return self.state.history()

    def remove_history_item(self, appid: str) -> dict[str, Any]:
        self.state.remove_history_item(str(appid))
        self._save()
        return {"ok": True}

    def clear_history(self) -> dict[str, Any]:
        self.state.clear_history()
        self._save()
        return {"ok": True}

    def search_suggestions(self, query: str) -> list[dict[str, Any]]:
        return self.steam.search_suggestions(query)

    def home_search(self, query: str) -> dict[str, Any]:
        game = self.steam.search_game(query)
        if not game:
            return {"ok": False, "error": "Game not found. Try a different name or Steam AppID."}

        candidates = ScanEngine.generate_home_candidates(game)
        resolved: list[dict[str, Any]] = []
        seen: set[str] = set()

        for candidate in candidates:
            for match in ScanEngine.resolve_candidate(candidate):
                norm = os.path.normcase(os.path.normpath(match["path"]))
                if norm in seen:
                    continue
                seen.add(norm)
                resolved.append(match)

        # Also merge the full library-style AppID scan for this game so Home and
        # Library stay consistent even when leftovers are found in non-template
        # locations like Public Documents crack folders or Steam userdata.
        library_index = ScanEngine.build_library_index()
        for match in library_index.get(str(game.get("appid", "")), []):
            norm = os.path.normcase(os.path.normpath(match["path"]))
            if norm in seen:
                continue
            seen.add(norm)
            resolved.append(match)

        resolved.sort(key=lambda item: (item["category"], item["path"].lower()))
        self.state.record_history(game)
        self._save()
        return {
            "ok": True,
            "game": game,
            "paths": resolved,
            "total_size": sum(item.get("size", 0) for item in resolved),
        }

    def scan_library(self) -> dict[str, Any]:
        archived_set = set(self.state.archived_appids())
        index = ScanEngine.build_library_index()
        items: list[dict[str, Any]] = []

        for appid, paths in index.items():
            meta = self.steam.get_app_details(appid) or {
                "name": f"Unknown Game ({appid})",
                "appid": appid,
                "developers": [],
                "publishers": [],
                "header_image": "",
                "short_description": "Not found on Steam Store.",
            }
            paths.sort(key=lambda item: (item["category"], item["path"].lower()))
            legit_owned = any(str(path.get("category", "")).startswith("Steam ") for path in paths)
            items.append({
                "appid": appid,
                "name": meta["name"],
                "developers": meta.get("developers", []),
                "publishers": meta.get("publishers", []),
                "header_image": meta.get("header_image", ""),
                "short_description": meta.get("short_description", ""),
                "paths": paths,
                "path_count": len(paths),
                "total_size": sum(path.get("size", 0) for path in paths),
                "archived": appid in archived_set,
                "legit_owned": legit_owned,
            })

        items.sort(key=lambda item: (item["archived"], item["name"].lower()))
        self._save()
        return {"ok": True, "items": items}

    def delete_paths(self, paths: list[str]) -> dict[str, Any]:
        return delete_paths_impl(paths)
