# Unified search rewrite

`ghosthunter_app/unified_search.py` is the single canonical path resolver for Home and Library.

## Trust rules

A game can enter the Library only through an installed-store record, an AppID-based leftover, or a curated game rule. Ordinary AppData folders never become games.

A displayed path must come from an AppID-specific leftover, an exact title/alias/developer path, a curated rule, or confirmed per-game data. The resolver never recursively searches arbitrary AppData folders for a game name.

## Consistency

`Backend.home_search()` and `Backend.scan_library()` both call `UnifiedSearch.find_paths()`. Home can add missing confirmed paths to the local cache; Library reads that same cache without stalling a refresh with hundreds of web requests.
