from __future__ import annotations

import os
import webbrowser
from typing import Any

from .file_ops import delete_paths as delete_paths_impl
from .file_ops import open_path as open_path_impl
from .file_ops import backup_path as backup_path_impl
from .file_ops import backup_game as backup_game_impl
from .scanner import ScanEngine
from .save_scanner import SaveScanner
from .steam_api import SteamAPI
from .unified_search import UnifiedSearch
from .storage import StateStore
from .updater import UpdateManager
from .utils import normalize_name


class Backend:
    THEME_OPTIONS = [
        {"id": "neon", "label": "Neon", "description": "Classic cyan and purple look."},
        {"id": "rubellite", "label": "Rubellite", "description": "Deep rubellite red."},
        {"id": "midnight", "label": "Midnight", "description": "Cool blue and steel accents."},
        {"id": "ember", "label": "Ember", "description": "Warm orange and crimson accents."},
        {"id": "emerald", "label": "Emerald", "description": "Green highlights with a darker base."},
        {"id": "custom", "label": "Custom", "description": "Pick your own accent color with the color picker or a hex code."},
    ]

    FONT_OPTIONS = [
        {"id": "inter", "label": "Inter", "description": "Modern UI default with clean spacing."},
        {"id": "system", "label": "System UI", "description": "Uses the native Windows/system interface font."},
        {"id": "dm-mono", "label": "DM Mono", "description": "A crisp developer-style monospace font stack."},
        {"id": "trebuchet", "label": "Trebuchet MS", "description": "Rounded and friendly without needing bundled font files."},
        {"id": "georgia", "label": "Georgia", "description": "Elegant serif option with strong readability."},
        {"id": "mono", "label": "JetBrains-style Mono", "description": "A technical monospace look using local system monospace fonts."},
        {"id": "roboto-slab", "label": "Roboto Slab", "description": "A sharper slab-serif look for the whole app."},
        {"id": "roboto-condensed", "label": "Roboto Condensed", "description": "Narrower, compact interface style."},
        {"id": "fraktur", "label": "Franktur", "description": "Decorative gothic display style."},
        {"id": "atkinson-hyperlegible", "label": "Atkinson Hyperlegible", "description": "Built for readability with clearer character shapes."},
    ]

    def __init__(self) -> None:
        self.state = StateStore()
        self.steam = SteamAPI()
        self.updater = UpdateManager()
        self._installed_catalog: dict[str, dict[str, Any]] | None = None

    def _save(self) -> None:
        self.state.save()
        self.steam.save_cache()

    def _ensure_installed_catalog(self) -> dict[str, dict[str, Any]]:
        if self._installed_catalog is None:
            self._installed_catalog = ScanEngine.discover_installed_games(self.steam)
            self._save()
        return self._installed_catalog

    def preview_game_appid(self, appid: str) -> dict[str, Any]:
        value = str(appid or '').strip()
        if not value:
            return {"ok": False, "error": "Enter a Steam AppID or game name."}
        game = None
        if value.isdigit():
            game = self.steam.get_app_details(value, timeout=5)
        if not game or str(game.get("name", "")).lower().startswith("unknown game"):
            game = self.steam.search_game(value, timeout=5)
        if not game:
            alias_appid = self.steam.aliases.get(normalize_name(value))
            if alias_appid:
                game = self.steam.get_app_details(alias_appid, timeout=5)
        if not game:
            return {"ok": False, "error": "No public Steam game was found for this input."}

        gid = str(game.get("appid") or "")
        header = str(game.get("header_image") or "")
        if not header and gid.isdigit():
            header = self.steam.header_image_for_appid(gid)
        if not header:
            try:
                cover = self.steam.igdb_cover_for_name(game.get("name", ""), timeout=3)
                if cover:
                    header = cover
            except Exception:
                pass
        game = {**game, "header_image": header, "appid": gid if gid else value}
        return {"ok": True, "game": game}

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

    def backup_path(self, path: str, game: dict[str, Any] | None = None) -> dict[str, Any]:
        return backup_path_impl(path, game)

    def backup_game(self, game: dict[str, Any]) -> dict[str, Any]:
        return backup_game_impl(game)

    def set_archived(self, appid: str, archived: bool) -> dict[str, Any]:
        self.state.set_archived(str(appid), archived)
        self._save()
        return {"ok": True, "appid": str(appid), "archived": archived}

    def set_excluded(self, appid: str, excluded: bool) -> dict[str, Any]:
        game = next((item for item in self._unified_search().library_items(set()) if str(item.get("appid")) == str(appid)), {"appid": appid, "name": f"Unknown Game ({appid})"})
        self.state.set_excluded(game, excluded); self._save(); return {"ok": True}

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
        raw = (query or '')
        clean = raw.strip()
        clean_norm = normalize_name(clean)
        catalog = self._ensure_installed_catalog()
        suggestions: list[dict[str, Any]] = []
        seen: set[str] = set()

        if clean:
            def score_installed(item: dict[str, Any]) -> tuple[int, str]:
                appid = str(item.get('appid', ''))
                name = str(item.get('name', ''))
                name_norm = normalize_name(name)
                if clean == appid:
                    score = 100
                elif clean_norm and clean_norm == name_norm:
                    score = 95
                elif clean_norm and name_norm.startswith(clean_norm):
                    score = 85
                elif clean_norm and clean_norm in name_norm:
                    score = 70
                elif clean.lower() in name.lower():
                    score = 50
                else:
                    score = 0
                return (-score, name.lower())

            ranked = []
            for item in catalog.values():
                score_key = score_installed(item)
                if score_key[0] == 0:
                    continue
                ranked.append((score_key, item))
            ranked.sort(key=lambda pair: pair[0])
            ranked = [item for _, item in ranked]
            for item in ranked:
                appid = str(item.get('appid', ''))
                if not appid or appid in seen:
                    continue
                seen.add(appid)
                image = item.get('header_image', '')
                if not image and appid.isdigit():
                    image = self.steam.header_image_for_appid(appid)
                suggestions.append({
                    'id': int(appid) if appid.isdigit() else appid,
                    'name': item.get('name', f'Unknown Game ({appid})'),
                    'tiny_image': image,
                })
                if len(suggestions) >= 6:
                    return suggestions

        remote_matches = self.steam.search_suggestions(clean)
        for item in remote_matches:
            appid = str(item.get('id', ''))
            if not appid or appid in seen:
                continue
            seen.add(appid)
            suggestions.append(item)
            if len(suggestions) >= 6:
                break

        # Enrich any suggestions still missing cover images via IGDB cache.
        for s in suggestions:
            if not s.get('tiny_image'):
                try:
                    cover = self.steam.igdb_cover_for_name(s.get('name', ''), timeout=3)
                    if cover:
                        s['tiny_image'] = cover
                except Exception:
                    pass

        return suggestions[:6]

    def set_theme(self, theme_name: str) -> dict[str, Any]:
        allowed = {option["id"] for option in self.THEME_OPTIONS}
        self.state.set_theme(theme_name if theme_name in allowed else "neon")
        self._save()
        return {"ok": True, "theme": self.state.theme()}

    def set_theme_mode(self, mode: str) -> dict[str, Any]:
        self.state.set_theme_mode(mode)
        self._save()
        return {"ok": True, "theme_mode": self.state.theme_mode()}

    def set_font(self, font_name: str) -> dict[str, Any]:
        allowed = {option["id"] for option in self.FONT_OPTIONS}
        self.state.set_font(font_name if font_name in allowed else "inter")
        self._save()
        return {"ok": True, "font": self.state.font()}

    @staticmethod
    def _normalize_hex_color(color: str) -> str | None:
        value = str(color or "").strip()
        if not value.startswith("#"):
            value = "#" + value
        hex_part = value[1:]
        if len(hex_part) == 3 and all(char in "0123456789abcdefABCDEF" for char in hex_part):
            hex_part = "".join(char * 2 for char in hex_part)
        if not (len(hex_part) == 6 and all(char in "0123456789abcdefABCDEF" for char in hex_part)):
            return None
        return "#" + hex_part.lower()

    def set_custom_theme_color(self, color: str, color2: str | None = None, use_second: bool | None = None) -> dict[str, Any]:
        value = self._normalize_hex_color(color)
        if not value:
            return {"ok": False, "error": "Use a valid hex color like #d946ef."}
        self.state.set_custom_theme_color(value)
        if color2:
            value2 = self._normalize_hex_color(color2)
            if value2:
                self.state.set_custom_theme_color_2(value2)
        if use_second is not None:
            self.state.set_custom_theme_use_second_color(bool(use_second))
        self.state.set_theme("custom")
        self._save()
        return {
            "ok": True,
            "theme": self.state.theme(),
            "custom_theme_color": self.state.custom_theme_color(),
            "custom_theme_color_2": self.state.custom_theme_color_2(),
            "custom_theme_use_second_color": self.state.custom_theme_use_second_color(),
        }

    def save_custom_theme_preset(self, name: str, color: str, color2: str | None = None, use_second: bool | None = None) -> dict[str, Any]:
        value = self._normalize_hex_color(color)
        if not value:
            return {"ok": False, "error": "Use a valid hex color like #d946ef."}
        clean_name = str(name or "Custom Theme").strip()[:40] or "Custom Theme"
        value2 = self._normalize_hex_color(color2 or self.state.custom_theme_color_2()) if color2 else None
        second_enabled = bool(use_second) if use_second is not None else self.state.custom_theme_use_second_color()
        self.state.add_custom_theme_preset(clean_name, value, value2 or '#fb7185', second_enabled)
        self.state.set_custom_theme_color(value)
        if value2:
            self.state.set_custom_theme_color_2(value2)
        self.state.set_custom_theme_use_second_color(second_enabled)
        self.state.set_theme("custom")
        self._save()
        return {
            "ok": True,
            "theme": self.state.theme(),
            "custom_theme_color": self.state.custom_theme_color(),
            "custom_theme_color_2": self.state.custom_theme_color_2(),
            "custom_theme_use_second_color": self.state.custom_theme_use_second_color(),
            "custom_theme_presets": self.state.custom_theme_presets(),
        }

    def delete_custom_theme_preset(self, name: str) -> dict[str, Any]:
        self.state.delete_custom_theme_preset(name)
        self._save()
        return {"ok": True, "custom_theme_presets": self.state.custom_theme_presets()}

    def rename_custom_theme_preset(self, old_name: str, new_name: str) -> dict[str, Any]:
        presets = self.state.custom_theme_presets()
        old_lower = str(old_name or "").strip().lower()
        new_clean = str(new_name or "").strip()[:40]
        if not new_clean:
            return {"ok": False, "error": "Name cannot be empty."}
        found = False
        for item in presets:
            if item.get("name", "").lower() == old_lower:
                item["name"] = new_clean
                found = True
                break
        if not found:
            return {"ok": False, "error": "Preset not found."}
        self.state.data["custom_theme_presets"] = presets
        self.state.save()
        self._save()
        return {"ok": True, "custom_theme_presets": self.state.custom_theme_presets()}

    def update_custom_theme_preset(self, name: str, color: str, color2: str | None = None, use_second: bool | None = None) -> dict[str, Any]:
        presets = self.state.custom_theme_presets()
        target = str(name or "").strip().lower()
        found = False
        for item in presets:
            if item.get("name", "").lower() == target:
                if color:
                    c = self._normalize_hex_color(color)
                    if c:
                        item["color"] = c
                if color2:
                    c2 = self._normalize_hex_color(color2)
                    if c2:
                        item["color2"] = c2
                if use_second is not None:
                    item["use_second"] = bool(use_second)
                found = True
                break
        if not found:
            return {"ok": False, "error": "Preset not found."}
        self.state.data["custom_theme_presets"] = presets
        self.state.save()
        self._save()
        return {"ok": True, "custom_theme_presets": self.state.custom_theme_presets()}

    def reorder_custom_theme_presets(self, drag_name: str, drop_name: str) -> dict[str, Any]:
        presets = self.state.custom_theme_presets()
        drag_lower = str(drag_name or "").strip().lower()
        drop_lower = str(drop_name or "").strip().lower()
        drag_idx = -1
        drop_idx = -1
        for i, item in enumerate(presets):
            if item.get("name", "").lower() == drag_lower:
                drag_idx = i
            if item.get("name", "").lower() == drop_lower:
                drop_idx = i
        if drag_idx < 0 or drop_idx < 0 or drag_idx == drop_idx:
            return {"ok": False, "error": "Could not reorder presets."}
        dragged = presets.pop(drag_idx)
        # Recalculate drop index after removal
        drop_idx = -1
        for i, item in enumerate(presets):
            if item.get("name", "").lower() == drop_lower:
                drop_idx = i
                break
        presets.insert(drop_idx, dragged)
        self.state.data["custom_theme_presets"] = presets
        self.state.save()
        self._save()
        return {"ok": True, "custom_theme_presets": self.state.custom_theme_presets()}

    def set_font_size(self, size: int) -> dict[str, Any]:
        self.state.set_font_size(size)
        self._save()
        return {"ok": True, "font_size": self.state.font_size()}

    def get_settings_info(self) -> dict[str, Any]:
        payload = self.updater.get_settings_payload()
        payload["theme"] = self.state.theme()
        payload["theme_options"] = self.THEME_OPTIONS
        payload["font"] = self.state.font()
        payload["font_options"] = self.FONT_OPTIONS
        payload["custom_theme_color"] = self.state.custom_theme_color()
        payload["custom_theme_presets"] = self.state.custom_theme_presets()
        payload["font_size"] = self.state.font_size()
        payload["custom_theme_color_2"] = self.state.custom_theme_color_2()
        payload["custom_theme_use_second_color"] = self.state.custom_theme_use_second_color()
        payload["theme_mode"] = self.state.theme_mode()
        return payload

    def check_for_updates(self) -> dict[str, Any]:
        return self.updater.check_for_updates()

    def open_releases_page(self) -> dict[str, Any]:
        return self.updater.open_releases_page()

    def download_update_installer(self, url: str) -> dict[str, Any]:
        return self.updater.download_installer_update(url)

    def launch_update_installer(self, path: str) -> dict[str, Any]:
        return self.updater.launch_installer(path)

    def download_portable_update(self, url: str) -> dict[str, Any]:
        return self.updater.download_portable_package(url)

    def rescan_library(self) -> dict[str, Any]:
        self._installed_catalog = ScanEngine.discover_installed_games(self.steam)
        self._save()
        return self.scan_library(use_cached_installed=True)


    def _unified_search(self) -> UnifiedSearch:
        catalog = dict(self._ensure_installed_catalog())
        # A game successfully hunted on Home has a trusted identity and cached
        # confirmed paths. Include it in Library on the next refresh.
        for game in self.state.history():
            appid = str(game.get("appid") or "")
            if appid and appid not in catalog:
                catalog[appid] = dict(game)
        return UnifiedSearch(self.steam, catalog, self.state)

    def edit_game_details(self, old_appid: str, new_appid: str, name: str, header_image: str) -> dict[str, Any]:
        old_key = str(old_appid or "").strip()
        new_key = str(new_appid or old_key).strip()
        if new_key and new_key != old_key:
            taken: set[str] = set(str(a) for a in self._ensure_installed_catalog().keys())
            taken.update(str(a) for a in self.state.custom_library_games().keys())
            for source_appid, entry in self.state.game_overrides().items():
                if str(source_appid) != old_key:
                    taken.add(str((entry or {}).get("appid") or source_appid))
            for game in self.state.history():
                taken.add(str(game.get("appid") or ""))
            if new_key in taken:
                return {"ok": False, "error": f"AppID {new_key} is already used by another game in your library."}
        self.state.set_game_override(old_appid, new_appid, name, header_image)
        self._save()
        return {"ok": True}

    def add_custom_library_game(self, appid: str, name: str, header_image: str, custom_path: str) -> dict[str, Any]:
        clean_appid = str(appid or '').strip() or f"custom-{normalize_name(name)}"
        clean_name = str(name or '').strip() or f"Custom Game ({clean_appid})"
        paths = []
        if custom_path and os.path.exists(custom_path):
            paths.append({
                "path": custom_path,
                "category": "Save Files",
                "description": "Custom user path",
                "source": "custom",
                "risk": "safe",
                "size": __import__("ghosthunter_app.utils", fromlist=["path_size"]).path_size(custom_path),
                "is_dir": os.path.isdir(custom_path),
            })
        else:
            temp_game = {"appid": clean_appid if clean_appid.isdigit() else "", "name": clean_name}
            paths = SaveScanner.find_save_paths(temp_game, include_online=True, fetch_online=True)

        no_leftovers = not paths
        game_record = {
            "appid": clean_appid,
            "name": clean_name,
            "header_image": header_image or "",
            "paths": paths,
            "path_count": len(paths),
            "total_size": sum(p.get("size", 0) for p in paths),
            "sources": [],
            "installed": False,
            "has_leftovers": bool(paths),
            "is_custom": True,
        }
        self.state.add_custom_library_game(game_record)
        self._save()
        return {"ok": True, "game": game_record, "paths": paths, "no_leftovers": no_leftovers}

    def remove_custom_library_game(self, appid: str) -> dict[str, Any]:
        key = str(appid or "").strip()
        if not key:
            return {"ok": False, "error": "Missing AppID."}
        custom = self.state.custom_library_games()
        target = key if key in custom else ""
        if not target:
            # The card may display an overridden AppID (Edit Details changed
            # it). Trace the override back to the original custom record.
            for old_appid, entry in self.state.game_overrides().items():
                if str((entry or {}).get("appid") or "") == key and str(old_appid) in custom:
                    target = str(old_appid)
                    break
        if not target:
            return {"ok": False, "error": "This game was not added manually, so it cannot be removed this way."}
        self.state.remove_custom_library_game(target)
        # Also drop any Edit Details override attached to this custom card so
        # a future re-add starts clean.
        self.state.remove_game_override(target)
        self.state.remove_game_override(key)
        self._save()
        return {"ok": True}

    def add_library_search_game(self, query: str) -> dict[str, Any]:
        search = self._unified_search()
        game = search.resolve_game(query)
        if not game:
            appid = str(query or '').strip()
            if appid.isdigit():
                details = self.steam.get_app_details(appid, timeout=3)
                if details:
                    game = {"appid": appid, **details}
            if not game:
                return {"ok": False, "error": "Game not found."}

        paths = search.find_paths(game, fetch_verified=True)
        no_leftovers = not paths
        appid = str(game.get("appid") or f"custom-{normalize_name(game.get('name', 'game'))}")
        name = game.get("name", f"Game ({appid})")
        header_image = game.get("header_image", "")
        if not header_image and appid.isdigit():
            header_image = self.steam.header_image_for_appid(appid)

        game_record = {
            "appid": appid,
            "name": name,
            "header_image": header_image or "",
            "paths": paths,
            "path_count": len(paths),
            "total_size": sum(p.get("size", 0) for p in paths),
            "sources": [],
            "installed": False,
            "has_leftovers": bool(paths),
            "is_custom": True,
        }
        self.state.add_custom_library_game(game_record)
        self._save()
        return {"ok": True, "game": game_record, "no_leftovers": no_leftovers}

    def home_search(self, query: str) -> dict[str, Any]:
        search = self._unified_search()
        game = search.resolve_game(query)
        if not game:
            return {"ok": False, "error": "Game not found. Choose an exact game title or a search suggestion."}

        paths = search.find_paths(game, fetch_verified=True)
        if not paths:
            return {"ok": False, "error": "No leftovers or save/config files were found for this game."}

        # Artwork is intentionally independent from scanning: a failed image
        # lookup can never break a hunt or prevent a result from being shown.
        appid = str(game.get("appid") or "")
        # History/catalog records only carry appid+name. Re-enrich missing
        # metadata (developers, publishers, description) from cached details
        # so repeat hunts show the same full card as the first one.
        if appid.isdigit() and not (game.get("developers") or game.get("publishers")):
            try:
                details = self.steam.get_app_details(appid, timeout=3) or {}
                game = {
                    **game,
                    "developers": game.get("developers") or details.get("developers", []),
                    "publishers": game.get("publishers") or details.get("publishers", []),
                    "short_description": game.get("short_description") or details.get("short_description", ""),
                    "header_image": game.get("header_image") or details.get("header_image", ""),
                }
            except Exception:
                pass
        if not game.get("header_image") and appid.isdigit():
            game = {**game, "header_image": self.steam.header_image_for_appid(appid)}
        self.state.record_history(game)
        self._save()
        return {"ok": True, "game": game, "paths": paths, "total_size": sum(item.get("size", 0) for item in paths)}

    def scan_library(self, use_cached_installed: bool = False) -> dict[str, Any]:
        # Both screens use UnifiedSearch.find_paths(). Library is therefore a
        # different presentation of the same canonical data, not a second scan.
        if not use_cached_installed:
            self._ensure_installed_catalog()
        items = self._unified_search().library_items(set(self.state.archived_appids()))
        excluded = self.state.excluded_games()
        visible = [item for item in items if str(item.get("appid")) not in excluded]
        excluded_items = [{**meta, "excluded": True, "paths": [], "path_count": 0, "total_size": 0, "archived": False, "hidden": False, "installed": False, "installed_sources": [], "has_leftovers": False} for meta in excluded.values()]
        self._save()
        return {"ok": True, "items": visible, "excluded_items": excluded_items}

    def delete_paths(self, paths: list[str]) -> dict[str, Any]:
        return delete_paths_impl(paths)
