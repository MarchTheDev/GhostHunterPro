from __future__ import annotations

import concurrent.futures
import json
import re
import urllib.parse
import urllib.request
from typing import Any

from .aliases import DELISTED_GAME_ALIASES, DELISTED_GAME_METADATA
from .config import APP_DETAILS_URL, STEAM_CACHE_FILE, STORE_SEARCH_URL
BONKER_API_URL = "https://api.bonker.dev/api/appdetails"
IGDB_PROXY_URL = "https://ambidex-igdb.netlify.app/api/igdb"
from .config import IGDB_CACHE_FILE
from .storage import migrate_legacy_files
from .utils import get_name_variations, normalize_name, safe_read_json, safe_write_json


class SteamAPI:
    def __init__(self) -> None:
        migrate_legacy_files()
        raw_cache: dict[str, dict[str, Any]] = safe_read_json(STEAM_CACHE_FILE, {})
        self.cache: dict[str, dict[str, Any]] = {
            str(app_id): self._normalize_game_payload(str(app_id), payload)
            for app_id, payload in raw_cache.items()
            if isinstance(payload, dict)
        }
        self.aliases = {normalize_name(name): str(appid) for name, appid in DELISTED_GAME_ALIASES.items()}
        self._cover_query_cache: dict[str, str] = {}
        # Persistent IGDB cache: name_norm → {cover_image_url, short_description, ...}
        self._igdb_cache: dict[str, dict[str, Any]] = safe_read_json(IGDB_CACHE_FILE, {})
        self.save_cache()

    def save_cache(self) -> None:
        safe_write_json(STEAM_CACHE_FILE, self.cache)
        safe_write_json(IGDB_CACHE_FILE, self._igdb_cache)

    @staticmethod
    def header_image_for_appid(app_id: str) -> str:
        return f"https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/{app_id}/header.jpg"

    @classmethod
    def _normalize_game_payload(cls, app_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        details_state = payload.get("details_state") or ""
        header_image = payload.get("header_image") or payload.get("headerImage") or ""
        name = payload.get("name") or f"Unknown Game ({app_id})"
        app_id_str = str(app_id or "").strip()

        is_unknown = (
            not name
            or name.lower().startswith("unknown game")
            or details_state == "missing"
            or app_id_str.startswith("local-save:")
            or app_id_str.startswith("local:")
        )

        if is_unknown:
            header_image = ""
        elif not header_image and details_state != "missing":
            header_image = cls.header_image_for_appid(app_id)
        return {
            "name": name,
            "appid": str(payload.get("appid") or app_id),
            "developers": payload.get("developers") or [],
            "publishers": payload.get("publishers") or [],
            "header_image": header_image,
            "short_description": payload.get("short_description") or payload.get("shortDescription") or "",
            "details_state": details_state,
            "app_type": payload.get("type") or payload.get("app_type") or "",
        }

    def seed_cache_entry(self, app_id: str, name: str, **extra: Any) -> dict[str, Any]:
        payload = {
            "name": name,
            "appid": str(app_id),
            "developers": extra.get("developers") or [],
            "publishers": extra.get("publishers") or [],
            "header_image": extra.get("header_image") or extra.get("headerImage") or "",
            "short_description": extra.get("short_description") or extra.get("shortDescription") or "",
            "details_state": extra.get("details_state") or "",
        }
        normalized = self._normalize_game_payload(str(app_id), payload)
        self.cache[str(app_id)] = normalized
        return normalized

    def _alias_fallback_game(self, app_id: str) -> dict[str, Any] | None:
        meta = DELISTED_GAME_METADATA.get(str(app_id))
        if not meta:
            return None
        return self.seed_cache_entry(
            str(app_id),
            meta.get("name", f"Unknown Game ({app_id})"),
            short_description="Delisted or hard-to-search title resolved from local alias data.",
        )

    @staticmethod
    def _score_name(query: str, name: str) -> int:
        q = normalize_name(query)
        n = normalize_name(name)
        if not q or not n:
            return 0
        if q == n:
            return 100
        if n.startswith(q):
            return 85
        if q in n:
            return 70
        q_words = set(get_name_variations(query))
        name_words = set(get_name_variations(name))
        if q_words & name_words:
            return 45
        return 0

    @staticmethod
    def _trusted_candidate_match(candidate: str, result_name: str, top_score: int, second_score: int = 0) -> bool:
        candidate_norm = normalize_name(candidate)
        result_norm = normalize_name(result_name)
        if not candidate_norm or not result_norm:
            return False
        if candidate_norm == result_norm:
            return True
        if top_score < 85:
            return False
        candidate_words = [part for part in re.split(r"\s+", (candidate or '').strip()) if part]
        has_digits = any(char.isdigit() for char in candidate)
        if result_norm.startswith(candidate_norm):
            if has_digits or len(candidate_words) >= 2 or len(candidate_norm) >= 10:
                return second_score < top_score
        return False

    def _cached_name_matches(self, query: str, limit: int = 6) -> list[dict[str, Any]]:
        ranked: list[tuple[int, dict[str, Any]]] = []
        for payload in self.cache.values():
            score = self._score_name(query, str(payload.get("name", "")))
            if score > 0:
                ranked.append((score, payload))
        ranked.sort(key=lambda item: (-item[0], item[1].get("name", "").lower()))
        return [payload for _, payload in ranked[:limit]]

    def cached_library_details(self, app_id: str, fallback_name: str = "") -> dict[str, Any]:
        app_id = str(app_id)
        cached = self.cache.get(app_id)
        if cached:
            if str(cached.get("details_state", "")) == "missing":
                return {
                    "name": fallback_name or cached.get("name") or f"Unknown Game ({app_id})",
                    "appid": app_id,
                    "developers": [],
                    "publishers": [],
                    "header_image": "",
                    "short_description": "",
                    "details_state": "missing",
                }
            return cached
        alias = self._alias_fallback_game(app_id) if app_id.isdigit() else None
        if alias:
            return alias
        return {
            "name": fallback_name or f"Unknown Game ({app_id})",
            "appid": app_id,
            "developers": [],
            "publishers": [],
            "header_image": self.header_image_for_appid(app_id) if app_id.isdigit() else "",
            "short_description": "",
            "details_state": "",
        }

    def _is_seeded_stub(self, app_id: str, payload: dict[str, Any] | None) -> bool:
        if not payload:
            return False
        if str(payload.get("details_state", "")) == "missing":
            return False
        name = str(payload.get("name", "") or "")
        header_image = str(payload.get("header_image", "") or payload.get("headerImage", "") or "")
        developers = payload.get("developers") or []
        publishers = payload.get("publishers") or []
        short_description = str(payload.get("short_description", "") or payload.get("shortDescription", "") or "")
        if name.startswith("Unknown Game"):
            return True
        return (
            header_image == self.header_image_for_appid(app_id)
            and not developers
            and not publishers
            and not short_description
        )

    def _store_search_items(self, query: str, timeout: int = 8) -> list[dict[str, Any]]:
        url = f"{STORE_SEARCH_URL}?term={urllib.parse.quote(query)}&l=english&cc=US"
        with urllib.request.urlopen(url, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8", errors="replace"))
        return [item for item in (data.get("items") or []) if item.get("id")]

    def _artwork_query_variants(self, name: str) -> list[str]:
        raw = str(name or '').strip()
        if not raw:
            return []
        variants = [raw]
        stripped = raw
        for suffix in [
            r"\s*[-+:|]?\s*demo$",
            r"\s*[-+:|]?\s*playtest$",
            r"\s*[-+:|]?\s*soundtrack$",
            r"\s*[-+:|]?\s*dedicated server$",
        ]:
            candidate = re.sub(suffix, '', stripped, flags=re.IGNORECASE).strip()
            if candidate and candidate != stripped:
                variants.append(candidate)
                stripped = candidate
        return list(dict.fromkeys(variant for variant in variants if variant))

    def cover_image_for_name(self, name: str, timeout: int = 3) -> str:
        cache_key = normalize_name(name)
        if not cache_key:
            return ''
        if cache_key in self._cover_query_cache:
            return self._cover_query_cache[cache_key]

        for query in self._artwork_query_variants(name):
            try:
                ranked = sorted(
                    self._store_search_items(query, timeout=timeout),
                    key=lambda item: (-self._score_name(query, str(item.get('name', ''))), str(item.get('name', '')).lower()),
                )
            except Exception:
                ranked = []
            if not ranked:
                continue
            top = ranked[0]
            top_name = str(top.get('name', '') or query)
            top_score = self._score_name(query, top_name)
            second_score = self._score_name(query, str(ranked[1].get('name', ''))) if len(ranked) > 1 else 0
            if not self._trusted_candidate_match(query, top_name, top_score, second_score):
                continue
            image = str(top.get('tiny_image') or '')
            if image:
                self._cover_query_cache[cache_key] = image
                return image
        self._cover_query_cache[cache_key] = ''
        return ''

    def search_suggestions(self, query: str, limit: int = 6) -> list[dict[str, Any]]:
        raw_query = query or ""
        clean_query = raw_query.strip()
        if not clean_query:
            return []
        if clean_query.isdigit():
            game = self.get_app_details(clean_query, timeout=8) or self._alias_fallback_game(clean_query)
            if not game:
                return []
            return [{
                "id": int(game["appid"]),
                "name": game["name"],
                "tiny_image": game.get("header_image", ""),
            }]

        alias_query = normalize_name(clean_query)
        alias_hits = []
        for alias, appid in self.aliases.items():
            if alias_query and (alias_query == alias or alias_query in alias or alias in alias_query):
                game = self.get_app_details(appid, timeout=8) or self._alias_fallback_game(appid)
                if game:
                    alias_hits.append({
                        "id": int(game["appid"]),
                        "name": game["name"],
                        "tiny_image": game.get("header_image", ""),
                    })
        if alias_hits:
            dedup = []
            seen_ids = set()
            for item in alias_hits:
                sid = str(item["id"])
                if sid in seen_ids:
                    continue
                seen_ids.add(sid)
                dedup.append(item)
            return dedup[:limit]

        suggestions: list[dict[str, Any]] = []
        seen: set[str] = set()

        for payload in self._cached_name_matches(clean_query, limit=limit):
            appid = str(payload.get("appid", ""))
            if appid in seen:
                continue
            seen.add(appid)
            suggestions.append({
                "id": int(appid) if appid.isdigit() else appid,
                "name": payload.get("name", f"Unknown Game ({appid})"),
                "tiny_image": payload.get("header_image", ""),
            })
            if len(suggestions) >= limit:
                return suggestions

        try:
            for item in self._store_search_items(clean_query, timeout=8):
                appid = str(item.get("id", ""))
                if not appid or appid in seen:
                    continue
                seen.add(appid)
                suggestions.append(item)
                if len(suggestions) >= limit:
                    break
        except Exception:
            pass

        return suggestions[:limit]

    def search_game(self, query: str, timeout: int = 8) -> dict[str, Any] | None:
        query = query.strip()
        if not query:
            return None
        try:
            if query.isdigit():
                return self.get_app_details(query, timeout=timeout) or self._alias_fallback_game(query)

            alias_appid = self.aliases.get(normalize_name(query))
            if alias_appid:
                alias_game = self.get_app_details(alias_appid, timeout=timeout) or self._alias_fallback_game(alias_appid)
                if alias_game:
                    return alias_game

            cached = self._cached_name_matches(query, limit=1)
            best_cached = cached[0] if cached else None
            best_score = self._score_name(query, best_cached.get("name", "")) if best_cached else 0
            if best_score >= 85:
                return best_cached

            items = self._store_search_items(query, timeout=timeout)
            if items:
                ranked = sorted(
                    [item for item in items if item.get("id")],
                    key=lambda item: (-self._score_name(query, str(item.get("name", ""))), str(item.get("name", "")).lower()),
                )
                if ranked and self._score_name(query, str(ranked[0].get("name", ""))) > 0:
                    resolved = self.get_app_details(str(ranked[0].get("id")), timeout=timeout)
                    if resolved:
                        return resolved

            if best_cached:
                return best_cached
            return None
        except Exception:
            alias_appid = self.aliases.get(normalize_name(query))
            if alias_appid:
                alias_game = self.get_app_details(alias_appid, timeout=timeout) or self._alias_fallback_game(alias_appid)
                if alias_game:
                    return alias_game
            return self._cached_name_matches(query, limit=1)[0] if self._cached_name_matches(query, limit=1) else None

    def _fetch_bonker_details(self, app_id: str, timeout: int = 8) -> dict[str, Any] | None:
        """Fetch game details from bonker.dev API as a fallback."""
        try:
            url = f"{BONKER_API_URL}?appids={app_id}&detail=basic"
            with urllib.request.urlopen(url, timeout=timeout) as response:
                data = json.loads(response.read().decode("utf-8", errors="replace"))
            if data.get("success") and data.get("data"):
                info = data["data"]
                return self._normalize_game_payload(app_id, {
                    "name": info.get("name", ""),
                    "appid": app_id,
                    "header_image": info.get("header_image", ""),
                    "short_description": info.get("short_description", ""),
                    "developers": [g.get("description", "") for g in (info.get("developers") or info.get("genres") or [])[:2]],
                    "publishers": [],
                    "details_state": "fetched",
                })
        except Exception:
            pass
        return None

    def get_app_details(self, app_id: str, timeout: int = 8) -> dict[str, Any] | None:
        app_id = str(app_id)
        cached = self.cache.get(app_id)
        # A previous offline failure must not permanently leave a real AppID as
        # Unknown Game. Revalidate missing entries on later rescans.
        if cached and not self._is_seeded_stub(app_id, cached) and cached.get("details_state") != "missing" and cached.get("app_type"):
            return cached
        try:
            url = f"{APP_DETAILS_URL}?appids={app_id}"
            with urllib.request.urlopen(url, timeout=timeout) as response:
                data = json.loads(response.read().decode("utf-8", errors="replace"))
            if not data.get(app_id, {}).get("success"):
                # Try bonker.dev as fallback
                bonker_result = self._fetch_bonker_details(app_id, timeout=timeout)
                if bonker_result:
                    self.cache[app_id] = bonker_result
                    return bonker_result
                fallback_name = (cached or {}).get("name") or f"Unknown Game ({app_id})"
                missing_payload = self._normalize_game_payload(app_id, {
                    "name": fallback_name,
                    "appid": app_id,
                    "header_image": "",
                    "short_description": "",
                    "details_state": "missing",
                })
                self.cache[app_id] = missing_payload
                return missing_payload
            info = data[app_id]["data"]
            info["details_state"] = "fetched"
            result = self._normalize_game_payload(app_id, info)
            self.cache[app_id] = result
            return result
        except Exception:
            # Try bonker.dev as fallback when Steam API fails
            bonker_result = self._fetch_bonker_details(app_id, timeout=timeout)
            if bonker_result:
                self.cache[app_id] = bonker_result
                return bonker_result
            return cached if cached else None

    def get_many_app_details(self, app_ids: list[str], timeout: int = 8, chunk_size: int = 25) -> dict[str, dict[str, Any]]:
        normalized_ids = [str(app_id) for app_id in app_ids if str(app_id).isdigit()]
        results: dict[str, dict[str, Any]] = {}
        missing: list[str] = []

        for app_id in normalized_ids:
            cached = self.cache.get(app_id)
            if cached and not self._is_seeded_stub(app_id, cached) and cached.get("details_state") != "missing":
                results[app_id] = cached
            else:
                missing.append(app_id)

        if not missing:
            return results

        worker_count = max(1, min(8, len(missing)))
        with concurrent.futures.ThreadPoolExecutor(max_workers=worker_count) as executor:
            future_map = {
                executor.submit(self.get_app_details, app_id, timeout): app_id
                for app_id in missing
            }
            for future in concurrent.futures.as_completed(future_map):
                app_id = future_map[future]
                try:
                    payload = future.result()
                except Exception:
                    payload = None
                if payload:
                    results[app_id] = payload

        return results

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

    # ── IGDB integration via ambidex proxy ──────────────────────────────

    def igdb_search(self, query: str, timeout: int = 10) -> list[dict[str, Any]]:
        """Search IGDB via the ambidex proxy. Returns list of game dicts."""
        query = (query or "").strip()
        if not query:
            return []
        url = f"{IGDB_PROXY_URL}?search={urllib.parse.quote(query)}"
        try:
            with urllib.request.urlopen(url, timeout=timeout) as response:
                data = json.loads(response.read().decode("utf-8", errors="replace"))
            if isinstance(data, dict) and "error" in data:
                return []
            if isinstance(data, list):
                return data
        except Exception:
            pass
        return []

    def igdb_cover_url(self, image_id: str, size: str = "t_cover_big") -> str:
        """Build an IGDB cover image URL from an image id."""
        if not image_id:
            return ""
        return f"https://images.igdb.com/igdb/image/upload/{size}/{image_id}.jpg"

    def igdb_cover_for_name(self, name: str, timeout: int = 6) -> str:
        """Fast cached cover URL lookup. Returns cover URL string or ''.

        Checks the persistent IGDB cache first, then falls back to a network
        search only if the name has never been looked up before.

        Pass timeout=0 for cache-only mode (no network calls).
        """
        cache_key = normalize_name(name)
        if not cache_key:
            return ""

        cached = self._igdb_cache.get(cache_key)
        if cached is not None:
            return cached.get("cover_image_url", "")

        # Cache-only mode: don't make network calls.
        if timeout <= 0:
            return ""

        # Cache miss — do a full IGDB lookup and store the result.
        result = self.igdb_best_match(name, timeout=timeout)
        if result:
            return result.get("cover_image_url", "")
        # Store empty result so we don't retry this name every scan.
        self._igdb_cache[cache_key] = {"cover_image_url": "", "short_description": ""}
        return ""

    def igdb_best_match(self, query: str, timeout: int = 10) -> dict[str, Any] | None:
        """Find the best IGDB match for a game name and return enriched data.

        Returns a dict with keys: name, cover_image_url, short_description, igdb_id
        or None if no good match found.  Results are cached persistently.
        """
        import difflib

        cache_key = normalize_name(query)
        if not cache_key:
            return None

        # Check persistent cache first.
        cached = self._igdb_cache.get(cache_key)
        if cached is not None:
            if cached.get("cover_image_url"):
                return cached
            return None

        results = self.igdb_search(query, timeout=timeout)
        if not results:
            self._igdb_cache[cache_key] = {"cover_image_url": "", "short_description": ""}
            self.save_cache()
            return None

        query_lower = query.lower().strip()

        best: dict[str, Any] | None = None

        # Try exact match first
        for game in results:
            if game.get("name", "").lower() == query_lower:
                best = self._extract_igdb_data(game)
                break

        # Fuzzy match with scoring (same algorithm as ambidex)
        if not best:
            search_words = query_lower.split()
            scored: list[tuple[float, dict[str, Any]]] = []
            for game in results:
                game_name_lower = game.get("name", "").lower()
                game_words = game_name_lower.split()
                similarity = difflib.SequenceMatcher(None, query_lower, game_name_lower).ratio()
                exact_start = 1.5 if game_name_lower.startswith(query_lower) else 1.0
                all_words = 1.3 if all(w in game_words for w in search_words) else 1.0
                extra_penalty = max(1.0 - abs(len(game_words) - len(search_words)) * 0.15, 0.5)
                pop_bonus = 1.0 + (game.get("total_rating", 0) / 2000)
                score = similarity * exact_start * all_words * extra_penalty * pop_bonus
                scored.append((score, game))

            scored.sort(key=lambda x: x[0], reverse=True)
            if scored and scored[0][0] > 0.6:
                best = self._extract_igdb_data(scored[0][1])

        # Cache the result (even empty) so we don't re-query.
        if best:
            self._igdb_cache[cache_key] = best
        else:
            self._igdb_cache[cache_key] = {"cover_image_url": "", "short_description": ""}
        self.save_cache()
        return best

    @staticmethod
    def _extract_igdb_data(game: dict[str, Any]) -> dict[str, Any]:
        """Pull useful fields from an IGDB game result."""
        cover = game.get("cover") or {}
        image_id = cover.get("image_id", "") if isinstance(cover, dict) else ""
        summary = game.get("summary", "")
        return {
            "igdb_id": game.get("id"),
            "name": game.get("name", ""),
            "cover_image_id": image_id,
            "cover_image_url": f"https://images.igdb.com/igdb/image/upload/t_cover_big/{image_id}.jpg" if image_id else "",
            "short_description": summary[:200] if summary else "",
            "total_rating": game.get("total_rating", 0),
        }
