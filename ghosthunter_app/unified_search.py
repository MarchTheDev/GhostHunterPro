from __future__ import annotations

"""One conservative resolver shared by Home search and Library."""

import glob
import concurrent.futures
import os
from typing import Any

from .save_scanner import SaveScanner
from .ludusavi_manifest import find_paths as ludusavi_paths, discover_existing_locallow_games, discover_existing_manifest_games
from .scanner import ScanEngine
from .utils import normalize_name, placeholder_header_image


class UnifiedSearch:
    # Steam's newer assets use a content-hash URL, so their old predictable
    # /apps/<id>/header.jpg URL can 404. These are resolved, known headers for
    # titles that need the newer form before their metadata cache is refreshed.
    CURATED_HEADERS = {
        "3844970": "https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/3844970/d6127e4eabda23e1d1c727a1875e6b6cb0e634ae/header.jpg?t=1781100001",
        "3606890": "https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/3606890/93b3fb78b1c6efc64089b7f2ef493a53aaaabecd/header.jpg?t=1775915574",
    }

    # Exact paths only. No general AppData walk or partial folder-name matching.
    DIRECT_TEMPLATES = (
        (r"{APPDATA}\{GAME}", "Save Files", "Save folder"),
        (r"{LOCAL}\{GAME}", "Save Files", "Local game data"),
        (r"{LOCALLOW}\{GAME}", "Save Files", "LocalLow game data"),
        (r"{SAVEDGAMES}\{GAME}", "Save Files", "Save folder"),
        (r"{DOCS}\{GAME}", "Save Files", "Save folder"),
        (r"{DOCS}\My Games\{GAME}", "Save Files", "Save folder"),
        (r"{PUBLICDOCS}\{GAME}", "Save Files", "Shared save folder"),
        (r"{PUBLICDOCS}\My Games\{GAME}", "Save Files", "Shared save folder"),
        (r"{LOCAL}\NVIDIA Corporation\NVIDIA App\NvBackend\ApplicationOntology\data\wrappers\{GAME}", "NVIDIA data", "NVIDIA game data"),
        (r"{LOCAL}\NVIDIA Corporation\NVIDIA App\NvBackend\ApplicationOntology\data\translations\{GAME}", "NVIDIA data", "NVIDIA game data"),
        (r"{LOCAL}\{GAME}\Saved", "Save Files", "Save folder"),
        (r"{LOCAL}\{GAME}\Saved\SaveGames", "Save Files", "Save folder"),
        (r"{LOCAL}\{GAME}\Saved\Config", "Config Files", "Configuration folder"),
        (r"{APPDATA}\Godot\app_userdata\{GAME}", "Save Files", "Save folder"),
    )

    def __init__(self, steam_api: Any, installed_catalog: dict[str, dict[str, Any]], state_store: Any = None) -> None:
        self.steam, self.catalog, self.state = steam_api, installed_catalog, state_store
        # This scan used to run once per game card, which made Library loading
        # progressively slower. Build the AppID index once per Library/Home run.
        self.leftover_index = ScanEngine.build_library_index()
        self.locallow_index = self._build_locallow_index()
        self.nvidia_index = self._build_nvidia_index()
        self.component_index = self._build_component_index()
        self.validated_candidates = self._discover_validated_candidates()

    def _discover_validated_candidates(self) -> dict[str, dict[str, Any]]:
        """Discover unknown save folders only after an exact Steam title match."""
        env = SaveScanner.env_map()
        # Root-specific game boundaries. Only outer containers are candidates.
        roots = [("locallow", env.get("{LOCALLOW}", ""), 2, 2), ("saved", env.get("{SAVEDGAMES}", ""), 1, 2), ("documents", env.get("{DOCS}", ""), 1, 2), ("local", env.get("{LOCAL}", ""), 1, 2)]
        candidates: list[tuple[str, str]] = []
        seen: set[str] = set()
        for root_kind, root, min_depth, max_depth in roots:
            if not root or not os.path.isdir(root): continue
            base_depth = len(os.path.normpath(root).split(os.sep))
            root_candidates = 0
            for current, dirs, _files in os.walk(root):
                depth = len(os.path.normpath(current).split(os.sep)) - base_depth
                # Candidate discovery needs outer game containers, not inner
                # Profiles/Unity/Config folders. Known-path scanning still goes deeper.
                if depth > max_depth: dirs[:] = []; continue
                name = os.path.basename(current)
                token = normalize_name(name)
                # Very short tokens (for example Lua) are commonly engine/config
                # directories, not dependable public game identities.
                if len(token) < 4 or token in seen or SaveScanner._is_blocked_folder(name): continue
                if depth < min_depth:
                    continue
                # LocalLow depth 1 is an author; deeper values are child data.
                # Save/Config/Profile/Unity folders are never game identities.
                generic = {"profiles", "profile", "save", "saved", "saves", "savedata", "savegames", "config", "configs", "unity", "cache", "modules", "logs", "settings", "data", "runtime"}
                if token in generic:
                    continue
                seen.add(token); candidates.append((name, current)); root_candidates += 1
                if root_candidates >= 60: break
        def resolve(item: tuple[str, str]):
            name, path = item
            token = normalize_name(name)
            # Store manifests and curated aliases beat a remote title search.
            game = next((dict(entry) for entry in self.catalog.values() if token and normalize_name(str(entry.get("name") or "")) == token), None)
            rule = SaveScanner.known_rule_for_name(name)
            if not game and rule:
                game = {"appid": str(rule.get("appid") or ""), "name": str(rule.get("name") or name), "sources": []}
            if game:
                return str(game.get("appid") or ""), {**game, "sources": game.get("sources", []), "paths": [{"path": path, "category": "Save Files", "description": "Detected game data folder", "source": "validated_local", "risk": "caution", "size": 0, "is_dir": True}]}
            try: game = self.steam.search_game(name, timeout=2)
            except Exception: game = None
            if not game or normalize_name(str(game.get("name") or "")) != normalize_name(name): return None
            # Store search/cache summaries omit the type. Fetch canonical app
            # metadata before rejecting a genuine title as an unknown app.
            try:
                details = self.steam.get_app_details(str(game.get("appid") or ""), timeout=3)
                if details:
                    game = {**game, **details}
            except Exception:
                pass
            # Store searches also return software/tools/DLC. New Library cards
            # must be actual games; installed catalog entries remain trusted.
            app_type = str(game.get("app_type") or "").lower()
            # Unknown/empty type is not enough for a new card: it may be an
            # old cached software search result. Catalog/curated games return
            # before this point and remain unaffected.
            if app_type != "game": return None
            appid = str(game.get("appid") or "")
            return appid, {**game, "appid": appid, "sources": [], "paths": [{"path": path, "category": "Save Files", "description": "Detected game data folder", "source": "validated_local", "risk": "caution", "size": 0, "is_dir": True}]}
        resolved = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            for result in pool.map(resolve, candidates):
                if result and result[0]: resolved.append(result)
        # If both a game folder and a child folder resolve as titles, the
        # outermost candidate wins. This prevents "The Great Circle" inside
        # "Indiana Jones and the Great Circle" becoming a second game card.
        resolved.sort(key=lambda pair: len(os.path.normpath(pair[1]["paths"][0]["path"])))
        found: dict[str, dict[str, Any]] = {}
        kept_paths: list[str] = []
        for appid, game in resolved:
            path = os.path.normcase(os.path.normpath(game["paths"][0]["path"]))
            if any(path.startswith(parent + os.sep) for parent in kept_paths):
                continue
            kept_paths.append(path)
            found[appid] = game
        return found

    def _aliases_by_appid(self) -> dict[str, set[str]]:
        aliases: dict[str, set[str]] = {}
        def add(appid: str, value: str) -> None:
            token = normalize_name(value)
            if not token:
                return
            aliases.setdefault(appid, set()).add(token)
            if token.startswith("the") and len(token) > 3:
                aliases[appid].add(token[3:])
        for appid, game in self.catalog.items():
            for value in SaveScanner.folder_names_for_game(game): add(str(appid), value)
        for rule in SaveScanner.KNOWN_GAMES.values():
            appid = str(rule.get("appid") or "")
            if appid:
                for value in [rule.get("name", ""), *(rule.get("aliases") or [])]: add(appid, str(value))
        return aliases

    def _build_component_index(self) -> dict[str, list[str]]:
        """Bounded scan of approved roots, matching exact known game-name components.

        No Steam searching occurs here and it never invents a game card from an
        unknown directory. A component must exactly match a known title/alias.
        """
        aliases = self._aliases_by_appid()
        reverse: dict[str, set[str]] = {}
        for appid, names in aliases.items():
            for name in names: reverse.setdefault(name, set()).add(appid)
        env = SaveScanner.env_map()
        roots = [(env.get("{LOCALLOW}", ""), "LocalLow game data"), (env.get("{LOCAL}", ""), "Local game data"), (env.get("{APPDATA}", ""), "Roaming game data"), (env.get("{DOCS}", ""), "Document game data"), (env.get("{SAVEDGAMES}", ""), "Save folder")]
        found: dict[str, list[str]] = {}; checked = 0; max_dirs = 12000
        for root, _label in roots:
            if not root or not os.path.isdir(root): continue
            root_depth = len(os.path.normpath(root).split(os.sep))
            for current, dirs, _files in os.walk(root):
                checked += 1
                if checked > max_dirs: return found
                depth = len(os.path.normpath(current).split(os.sep)) - root_depth
                if depth > 4:
                    dirs[:] = []; continue
                token = normalize_name(os.path.basename(current))
                for appid in reverse.get(token, set()):
                    found.setdefault(appid, []).append(current)
        return found

    def _build_nvidia_index(self) -> dict[str, list[str]]:
        """Index NVIDIA wrapper/translation folders by exact game alias."""
        aliases: dict[str, set[str]] = {}
        for appid, game in self.catalog.items():
            aliases[str(appid)] = {normalize_name(value) for value in SaveScanner.folder_names_for_game(game) if normalize_name(value)}
        for rule in SaveScanner.KNOWN_GAMES.values():
            appid = str(rule.get("appid") or "")
            if appid:
                aliases.setdefault(appid, set()).update(normalize_name(value) for value in [rule.get("name", ""), *(rule.get("aliases") or [])] if normalize_name(value))
        local = SaveScanner.env_map().get("{LOCAL}", "")
        root = os.path.join(local, "NVIDIA Corporation", "NVIDIA App", "NvBackend", "ApplicationOntology", "data")
        found: dict[str, list[str]] = {}
        for kind in ("wrappers", "translations"):
            folder = os.path.join(root, kind)
            try:
                children = [os.path.join(folder, item) for item in os.listdir(folder)]
            except OSError:
                continue
            for child in children:
                if not os.path.exists(child):
                    continue
                token = normalize_name(os.path.basename(child))
                for appid, names in aliases.items():
                    if token and token in names:
                        found.setdefault(appid, []).append(child)
        return found

    def _build_locallow_index(self) -> dict[str, list[str]]:
        """Match LocalLow folders to known installed/curated titles, two levels deep.

        LocalLow commonly uses ``Company/Product`` rather than the Steam title.
        We enumerate only that bounded structure and accept a folder only when
        its name exactly matches an installed game variation or curated alias.
        """
        aliases: dict[str, set[str]] = {}
        for appid, game in self.catalog.items():
            aliases[str(appid)] = {normalize_name(value) for value in SaveScanner.folder_names_for_game(game) if normalize_name(value)}
        for rule in SaveScanner.KNOWN_GAMES.values():
            appid = str(rule.get("appid") or "")
            if not appid:
                continue
            values = [rule.get("name", ""), *(rule.get("aliases") or [])]
            aliases.setdefault(appid, set()).update(normalize_name(value) for value in values if normalize_name(value))
        root = SaveScanner.env_map().get("{LOCALLOW}", "")
        found: dict[str, list[str]] = {}
        if not os.path.isdir(root):
            return found
        try:
            companies = [os.path.join(root, name) for name in os.listdir(root)]
        except OSError:
            return found
        for company in companies:
            if not os.path.isdir(company):
                continue
            candidates = [company]
            try:
                children = [os.path.join(company, name) for name in os.listdir(company)]
            except OSError:
                children = []
            candidates.extend(children)
            # A few launchers insert an extra vendor layer. Three levels is
            # still bounded and avoids a recursive LocalLow crawl.
            grandchildren: list[str] = []
            for child in children:
                if not os.path.isdir(child):
                    continue
                try:
                    grandchildren.extend(os.path.join(child, name) for name in os.listdir(child))
                except OSError:
                    continue
            candidates.extend(grandchildren)
            # Some Unity publishers use Author/Group/Publisher/Game. This is
            # the final bounded level; it is not a recursive filesystem walk.
            for grandchild in grandchildren:
                if not os.path.isdir(grandchild):
                    continue
                try:
                    candidates.extend(os.path.join(grandchild, name) for name in os.listdir(grandchild))
                except OSError:
                    continue
            for candidate in candidates:
                if not os.path.isdir(candidate):
                    continue
                token = normalize_name(os.path.basename(candidate))
                for appid, names in aliases.items():
                    if token and token in names:
                        found.setdefault(appid, []).append(candidate)
        return found

    @staticmethod
    def _same_name(a: str, b: str) -> bool:
        return bool(normalize_name(a) and normalize_name(a) == normalize_name(b))

    @staticmethod
    def _key(path: dict[str, Any]) -> str:
        return os.path.normcase(os.path.normpath(str(path.get("path") or "")))

    def resolve_game(self, query: str) -> dict[str, Any] | None:
        query = str(query or "").strip()
        if not query:
            return None
        if query in self.catalog:
            return dict(self.catalog[query])
        for item in self.catalog.values():
            if self._same_name(query, str(item.get("name") or "")):
                return dict(item)
        rule = SaveScanner.known_rule_for_name(query)
        if rule:
            appid = str(rule.get("appid") or "")
            details = self.steam.get_app_details(appid, timeout=3) if appid.isdigit() else {}
            return {"appid": appid, "name": rule.get("name") or query,
                    "developers": (details or {}).get("developers", []), "publishers": (details or {}).get("publishers", []),
                    "header_image": (details or {}).get("header_image", ""), "short_description": (details or {}).get("short_description", ""), "sources": []}
        # A remote result is permitted only when its title exactly equals what was requested.
        try:
            result = self.steam.search_game(query)
        except Exception:
            result = None
        return dict(result) if result and self._same_name(query, str(result.get("name") or "")) else None

    def _add(self, output: list[dict[str, Any]], seen: set[str], path: str, category: str, description: str, source: str) -> None:
        # Templates use Windows separators; normalize before exposing a path.
        entry = SaveScanner._path_entry(os.path.normpath(path), category, description, source)
        if entry and self._key(entry) not in seen:
            seen.add(self._key(entry)); output.append(entry)

    def _exact_paths(self, game: dict[str, Any]) -> list[dict[str, Any]]:
        output: list[dict[str, Any]] = []; seen: set[str] = set()
        rule = SaveScanner.known_rule_for_name(str(game.get("name") or ""))
        if rule:
            for pattern in rule.get("patterns") or []:
                for match in glob.glob(SaveScanner.expand_vars(str(pattern))):
                    category = "Save & Config Files" if rule.get("save_and_config") else ("Config Files" if "config" in match.lower() else "Save Files")
                    description = "Save and configuration folder" if category == "Save & Config Files" else ("Configuration folder" if category == "Config Files" else "Save folder")
                    self._add(output, seen, match, category, description, "curated")
            if rule.get("patterns_only"):
                return output
        for name in SaveScanner.folder_names_for_game(game):
            for template, category, description in self.DIRECT_TEMPLATES:
                self._add(output, seen, SaveScanner.expand_vars(template.replace("{GAME}", name)), category, description, "exact")
            for person in SaveScanner.people_for_game(game):
                for template, category, description in ((r"{APPDATA}\{PERSON}\{GAME}", "Save Files", "Save folder"), (r"{LOCAL}\{PERSON}\{GAME}", "Save Files", "Local game data"), (r"{LOCALLOW}\{PERSON}\{GAME}", "Save Files", "LocalLow game data")):
                    self._add(output, seen, SaveScanner.expand_vars(template.replace("{PERSON}", person).replace("{GAME}", name)), category, description, "exact")
        return output

    def find_paths(self, game: dict[str, Any], fetch_verified: bool) -> list[dict[str, Any]]:
        """The only path-finding method called by either UI screen."""
        paths = self._exact_paths(game); seen = {self._key(item) for item in paths}
        for item in game.get("paths", []) or []:
            if self._key(item) not in seen:
                seen.add(self._key(item)); paths.append(dict(item))
        appid = str(game.get("appid") or "")
        for path in self.locallow_index.get(appid, []):
            self._add(paths, seen, path, "Save Files", "LocalLow game data", "exact")
        for path in self.nvidia_index.get(appid, []):
            self._add(paths, seen, path, "NVIDIA data", "NVIDIA game data", "exact")
        for path in self.component_index.get(appid, []):
            self._add(paths, seen, path, "Save Files", "Detected game data folder", "exact")
        if appid.isdigit():
            for item in self.leftover_index.get(appid, []):
                if self._key(item) not in seen:
                    seen.add(self._key(item)); paths.append(dict(item))
        if appid.isdigit():
            nvidia = SaveScanner.expand_vars(r"{LOCAL}\\NVIDIA Corporation\\NVIDIA App\\NvBackend\\Recommendations\\" + appid)
            self._add(paths, seen, nvidia, "NVIDIA data", "NVIDIA game recommendation data", "appid")
        # Maintained offline manifest covers unusual LocalLow/AppData paths.
        for item in ludusavi_paths(game):
            entry = dict(item)
            leaf = normalize_name(os.path.basename(str(entry.get("path") or "")))
            # Manifest entries often name the inner Profiles/Saves directory.
            # Present the game container instead when it is clearly a generic
            # child folder, avoiding deletion of a tiny child only.
            if leaf in {"profile", "profiles", "save", "saves", "savedata", "savegames", "config", "configs"}:
                parent = os.path.dirname(str(entry["path"]))
                if parent and os.path.isdir(parent):
                    entry["path"] = parent
                    entry["size"] = __import__("ghosthunter_app.utils", fromlist=["path_size"]).path_size(parent)
            if self._key(entry) not in seen:
                seen.add(self._key(entry)); paths.append(entry)
        for item in SaveScanner.pcgw_save_paths(game, fetch_missing=fetch_verified):
            if self._key(item) not in seen:
                seen.add(self._key(item)); paths.append(item)
        return SaveScanner.collapse_nested_paths(paths)

    def library_games(self) -> dict[str, dict[str, Any]]:
        # No arbitrary save-folder discovery: only store manifests, AppID traces, and curated games.
        games = {str(appid): dict(item) for appid, item in self.catalog.items()}
        if getattr(self, "state", None):
            for appid, custom_game in self.state.custom_library_games().items():
                key = str(appid)
                # Never clobber a real detected/installed game with a custom
                # record: the scanner's entry has trusted paths and sources.
                if key in games:
                    continue
                record = dict(custom_game)
                record["is_custom"] = True
                games[key] = record
        # Candidate folders are accepted only after an exact Steam-title match.
        for appid, candidate in self.validated_candidates.items():
            games.setdefault(appid, candidate)
        # Component matches only enrich already trusted cards. New save-only
        # cards come from an exact Ludusavi path, never a generic app folder.
        # Reverse manifest discovery adds save-only games whose store install
        # is gone or was not discovered by a launcher manifest.
        for appid, manifest_game in discover_existing_manifest_games().items():
            if appid not in games:
                games[appid] = manifest_game
        for appid in self.nvidia_index:
            if appid not in games:
                rule = next((item for item in SaveScanner.KNOWN_GAMES.values() if str(item.get("appid") or "") == str(appid)), None)
                if rule:
                    games[appid] = {"appid": appid, "name": rule.get("name", f"Unknown Game (AppID: {appid})"), "sources": []}
        for appid in self.leftover_index:
            if appid not in games:
                games[appid] = {**self.steam.cached_library_details(appid, fallback_name=f"Unknown Game ({appid})"), "appid": appid, "sources": []}
        for rule in SaveScanner.KNOWN_GAMES.values():
            appid = str(rule.get("appid") or "") or f"local-save:{normalize_name(str(rule.get('name') or ''))}"
            game = {"appid": appid, "name": str(rule.get("name") or ""), "developers": [], "publishers": [], "sources": []}
            if appid not in games and game["name"] and self.find_paths(game, False):
                games[appid] = game
        return games

    def library_items(self, hidden: set[str]) -> list[dict[str, Any]]:
        games = self.library_games()
        # Resolve only AppID leftovers that still have no title. The API helper
        # performs these requests concurrently and caches successful results.
        unknown_ids = [appid for appid, game in games.items() if str(appid).isdigit() and str(game.get("name") or "").lower().startswith("unknown game")]
        try:
            details = self.steam.get_many_app_details(unknown_ids, timeout=3)
        except Exception:
            details = {}
        overrides = self.state.game_overrides() if getattr(self, "state", None) else {}
        items = []
        for appid, game in games.items():
            game = {**game, **(details.get(str(appid)) or {}), "appid": str(appid)}
            # Do not block Library on one online lookup per card. Home searches
            # populate the same confirmed-path cache; Library reads it here.
            paths = self.find_paths(game, fetch_verified=False)
            meta = self.steam.cached_library_details(str(appid), fallback_name=str(game.get("name") or f"Unknown Game (AppID: {appid})"))
            name = str(meta.get("name") or game.get("name") or f"Unknown Game (AppID: {appid})")
            if name.lower().startswith("unknown game"):
                name = f"Unknown Game (AppID: {appid})"
            # Prefer an already-cached IGDB cover. This is cache-only, so it
            # never makes Library loading slower or causes a network failure.
            is_unresolved = (name.lower().startswith("unknown game") or str(meta.get("details_state") or game.get("details_state") or "").lower() == "missing")
            cached_cover = "" if is_unresolved else self.steam.igdb_cover_for_name(name, timeout=0)
            # Prefer an IGDB cover for local/Epic entries and cards whose
            # Steam header is absent. This keeps artwork independent of scans.
            fresh_cover = ""
            if not cached_cover and not str(appid).isdigit():
                try: fresh_cover = self.steam.igdb_cover_for_name(name, timeout=3)
                except Exception: fresh_cover = ""
            header = str(fresh_cover or cached_cover or self.CURATED_HEADERS.get(str(appid), "") or game.get("header_image") or meta.get("header_image") or "")
            if not header and str(appid).isdigit() and not is_unresolved:
                try:
                    details = self.steam.get_app_details(str(appid), timeout=3) or {}
                    header = str(details.get("header_image") or "")
                except Exception: pass
            if not header and str(appid).isdigit() and not is_unresolved: header = self.steam.header_image_for_appid(str(appid))
            if not header and not is_unresolved: header = placeholder_header_image(name, "Game data")
            if is_unresolved: header = ""

            override = overrides.get(str(appid)) or overrides.get(str(game.get('appid')))
            if override:
                name = override.get('name') or name
                appid = override.get('appid') or appid
                if override.get('header_image'):
                    header = override.get('header_image')

            # Installed manifests already carry their source. Re-probing Steam,
            # Epic and GOG for every Library card was another avoidable slowdown.
            sources = game.get("sources") or []
            is_custom = bool(game.get("is_custom"))
            if is_custom:
                # Custom records keep their stored paths (e.g. a user-supplied
                # custom folder) merged with anything the scanner finds live.
                stored_paths = list(game.get("paths") or [])
                seen_keys = {self._key(path) for path in paths}
                for path in stored_paths:
                    if self._key(path) not in seen_keys:
                        paths.append(path)
                        seen_keys.add(self._key(path))
                # A custom card is never proof of a store install.
                sources = []
                if not header:
                    header = str(game.get("header_image") or "")
            items.append({"is_unknown": is_unresolved, "is_custom": is_custom, "appid": str(appid), "name": name, "developers": meta.get("developers", game.get("developers", [])), "publishers": meta.get("publishers", game.get("publishers", [])), "header_image": header, "short_description": meta.get("short_description", game.get("short_description", f"Detected game data for AppID {appid}.")), "paths": paths, "path_count": len(paths), "total_size": sum(path.get("size", 0) for path in paths), "archived": str(appid) in hidden, "hidden": str(appid) in hidden, "installed_sources": sources, "installed": bool(sources), "has_leftovers": bool(paths)})
        # A GSE folder may be indexed under its raw shortened ID and its
        # corrected trailing-zero AppID. If the corrected ID resolved to a
        # real game, hide the duplicate unknown card for the exact same path.
        known_paths = {self._key(path) for item in items if not item.get("is_unknown") for path in item.get("paths", [])}
        items = [item for item in items if not item.get("is_unknown") or any(self._key(path) not in known_paths for path in item.get("paths", []))]
        # If both a genuine GSE AppID and its accidental trailing-zero variant
        # resolve, prefer the original shorter AppID for the shared path.
        path_to_ids = {}
        for item in items:
            for path in item.get("paths", []):
                path_to_ids.setdefault(self._key(path), set()).add(str(item.get("appid")))
        remove_ids = set()
        for ids in path_to_ids.values():
            for appid in ids:
                if appid.endswith("0") and appid[:-1] in ids:
                    remove_ids.add(appid)
        items = [item for item in items if str(item.get("appid")) not in remove_ids]
        return sorted(items, key=lambda item: (bool(item["archived"]), bool(item.get("is_unknown")), item["name"].lower()))

