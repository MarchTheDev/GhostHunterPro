from __future__ import annotations

import json
import urllib.parse
import urllib.request
from typing import Any

from .config import APP_DETAILS_URL, STEAM_CACHE_FILE, STORE_SEARCH_URL
from .storage import migrate_legacy_files
from .utils import normalize_name, safe_read_json, safe_write_json


class SteamAPI:
    def __init__(self) -> None:
        migrate_legacy_files()
        raw_cache: dict[str, dict[str, Any]] = safe_read_json(STEAM_CACHE_FILE, {})
        self.cache: dict[str, dict[str, Any]] = {
            str(app_id): self._normalize_game_payload(str(app_id), payload)
            for app_id, payload in raw_cache.items()
            if isinstance(payload, dict)
        }
        # Persist normalized cache so old camelCase entries get upgraded once.
        self.save_cache()

    def save_cache(self) -> None:
        safe_write_json(STEAM_CACHE_FILE, self.cache)

    @staticmethod
    def _normalize_game_payload(app_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "name": payload.get("name") or f"Unknown Game ({app_id})",
            "appid": str(payload.get("appid") or app_id),
            "developers": payload.get("developers") or [],
            "publishers": payload.get("publishers") or [],
            "header_image": payload.get("header_image") or payload.get("headerImage") or "",
            "short_description": payload.get("short_description") or payload.get("shortDescription") or "",
        }

    def search_suggestions(self, query: str, limit: int = 6) -> list[dict[str, Any]]:
        query = query.strip()
        if not query:
            return []
        if query.isdigit():
            game = self.get_app_details(query, timeout=8)
            if not game:
                return []
            return [{
                "id": int(game["appid"]),
                "name": game["name"],
                "tiny_image": game.get("header_image", ""),
            }]
        try:
            url = f"{STORE_SEARCH_URL}?term={urllib.parse.quote(query)}&l=english&cc=US"
            with urllib.request.urlopen(url, timeout=8) as response:
                data = json.loads(response.read().decode("utf-8", errors="replace"))
            return (data.get("items") or [])[:limit]
        except Exception:
            return []

    def search_game(self, query: str, timeout: int = 8) -> dict[str, Any] | None:
        query = query.strip()
        if not query:
            return None
        try:
            if query.isdigit():
                return self.get_app_details(query, timeout=timeout)
            url = f"{STORE_SEARCH_URL}?term={urllib.parse.quote(query)}&l=english&cc=US"
            with urllib.request.urlopen(url, timeout=timeout) as response:
                data = json.loads(response.read().decode("utf-8", errors="replace"))
            items = data.get("items") or []
            if not items:
                return None
            return self.get_app_details(str(items[0].get("id")), timeout=timeout)
        except Exception:
            return None

    def get_app_details(self, app_id: str, timeout: int = 8) -> dict[str, Any] | None:
        app_id = str(app_id)
        if app_id in self.cache:
            return self.cache[app_id]
        try:
            url = f"{APP_DETAILS_URL}?appids={app_id}"
            with urllib.request.urlopen(url, timeout=timeout) as response:
                data = json.loads(response.read().decode("utf-8", errors="replace"))
            if not data.get(app_id, {}).get("success"):
                return None
            info = data[app_id]["data"]
            result = self._normalize_game_payload(app_id, info)
            self.cache[app_id] = result
            return result
        except Exception:
            return None

    def resolve_candidate_name(self, name: str) -> dict[str, Any] | None:
        result = self.search_game(name, timeout=2)
        if not result:
            return None
        candidate_norm = normalize_name(name)
        result_norm = normalize_name(result.get("name", ""))
        if not candidate_norm or not result_norm:
            return None
        if candidate_norm == result_norm or candidate_norm in result_norm or result_norm in candidate_norm:
            return result
        return None
