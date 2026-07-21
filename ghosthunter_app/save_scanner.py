from __future__ import annotations

import glob
import json
import os
import re
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from .config import PCGW_CACHE_FILE
from .utils import get_name_variations, normalize_name, path_size, placeholder_header_image, safe_read_json, safe_write_json


class SaveScanner:
    """Focused save/config discovery layer.

    The scanner is intentionally conservative:
    - Home search checks exact/common locations for one chosen game.
    - Library only adds save-only entries when the folder can be resolved as a game
      or is in our curated rules.
    - It does not walk all of AppData looking for partial name matches, because
      that causes false positives such as launchers/mod managers containing a
      folder with a game name inside them.
    """

    # Folder aliases whose on-disk names are not the nice public title.
    # appid is optional but gives the Library proper Steam art/details.
    KNOWN_GAMES: dict[str, dict[str, Any]] = {
        "balatro": {
            "name": "Balatro",
            "appid": "2379780",
            "aliases": ["Balatro"],
            "save_and_config": True,
            "patterns": [r"{APPDATA}\Balatro"],
        },
        "hitman3": {
            "name": "HITMAN World of Assassination",
            "appid": "1659040",
            "aliases": ["HITMAN3", "HITMAN 3", "HITMAN III", "Hitman 3"],
            "patterns": [
                r"{APPDATA}\IO Interactive\Epic\*\HITMAN3",
                r"{LOCAL}\IO Interactive\Epic\*\HITMAN3",
                r"{APPDATA}\IO Interactive\HITMAN3",
            ],
        },
        "hitmanworldofassassination": {
            "name": "HITMAN World of Assassination",
            "appid": "1659040",
            "aliases": ["HITMAN3", "HITMAN 3", "HITMAN III", "Hitman 3"],
            "patterns": [
                r"{APPDATA}\IO Interactive\Epic\*\HITMAN3",
                r"{LOCAL}\IO Interactive\Epic\*\HITMAN3",
                r"{APPDATA}\IO Interactive\HITMAN3",
            ],
        },
        "hitmaniii": {
            "name": "HITMAN World of Assassination",
            "appid": "1659040",
            "aliases": ["HITMAN3", "HITMAN 3", "HITMAN III", "Hitman 3"],
            "patterns": [
                r"{APPDATA}\IO Interactive\Epic\*\HITMAN3",
                r"{LOCAL}\IO Interactive\Epic\*\HITMAN3",
                r"{APPDATA}\IO Interactive\HITMAN3",
            ],
        },
        "assettocorsaevo": {
            "name": "Assetto Corsa EVO",
            "appid": "3058630",
            "aliases": ["ACE", "Assetto Corsa EVO", "AssettoCorsaEVO"],
            "patterns": [
                r"{LOCAL}\ACE\Saved",
                r"{LOCAL}\ACE\Saved\SaveGames",
                r"{LOCAL}\ACE\Saved\Config",
            ],
        },
        "ace": {
            "name": "Assetto Corsa EVO",
            "appid": "3058630",
            "aliases": ["ACE", "Assetto Corsa EVO", "AssettoCorsaEVO"],
            "patterns": [
                r"{LOCAL}\ACE\Saved",
                r"{LOCAL}\ACE\Saved\SaveGames",
                r"{LOCAL}\ACE\Saved\Config",
            ],
        },
        "legobatmanlegacyofthedarkknight": {
            "name": "LEGO Batman: Legacy of the Dark Knight",
            "appid": "2215200",
            "aliases": [
                "LEGO Batman Legacy of the Dark Knight",
                "LEGO Batman - Legacy of the Dark Knight",
                "LEGO\u00ae Batman\u2122: Legacy of the Dark Knight",
                "Dinner",
            ],
            "patterns_only": True,
            "patterns": [
                r"{LOCAL}\Warner Bros. Interactive Entertainment\LEGO Batman - Legacy of the Dark Knight\SaveGames",
                r"{LOCAL}\Dinner\Saved\Config\Windows",
            ],
        },
        "legobatmanlegacyofthedarkknightdinner": {
            "name": "LEGO Batman: Legacy of the Dark Knight",
            "appid": "2215200",
            "aliases": ["Dinner", "LEGO Batman - Legacy of the Dark Knight"],
            "patterns_only": True,
            "patterns": [
                r"{LOCAL}\Warner Bros. Interactive Entertainment\LEGO Batman - Legacy of the Dark Knight\SaveGames",
                r"{LOCAL}\Dinner\Saved\Config\Windows",
            ],
        },
        "dispatch": {
            "name": "Dispatch",
            "aliases": ["Dispatch"],
            "patterns": [
                r"{APPDATA}\Dispatch",
                r"{LOCAL}\Dispatch",
                r"{LOCAL}\Dispatch\Saved",
                r"{LOCAL}\Dispatch\Saved\SaveGames",
                r"{SAVEDGAMES}\Dispatch",
                r"{DOCS}\My Games\Dispatch",
            ],
        },
        # ── Assetto Corsa ──────────────────────────────────────────────
        "assettocorsa": {
            "name": "Assetto Corsa",
            "appid": "244210",
            "aliases": ["Assetto Corsa"],
            "save_and_config": True,
            "patterns": [
                r"{DOCS}\Assetto Corsa",
                r"{DOCS}\Assetto Corsa\cfg",
                r"{DOCS}\Assetto Corsa\setups",
                r"{DOCS}\Assetto Corsa\replay",
            ],
        },
        "assettocorsacompetizione": {
            "name": "Assetto Corsa Competizione",
            "appid": "805550",
            "aliases": ["Assetto Corsa Competizione", "ACC"],
            "save_and_config": True,
            "patterns": [
                r"{DOCS}\Assetto Corsa Competizione",
                r"{DOCS}\Assetto Corsa Competizione\Config",
                r"{DOCS}\Assetto Corsa Competizione\Savegames",
                r"{DOCS}\Assetto Corsa Competizione\Customs",
            ],
        },
        # ── The Last of Us ─────────────────────────────────────────────
        "thelastofusparti": {
            "name": "The Last of Us Part I",
            "appid": "1888930",
            "aliases": ["The Last of Us Part 1", "TLOU1", "TLOU Part I"],
            "save_and_config": True,
            "patterns": [
                r"{SAVEDGAMES}\The Last of Us Part I",
                r"{SAVEDGAMES}\The Last of Us Part I\users\*\savedata",
                r"{DOCS}\The Last of Us Part I",
            ],
        },
        "thelastofuspartiiremastered": {
            "name": "The Last of Us Part II Remastered",
            "appid": "2531310",
            "aliases": ["The Last of Us Part 2", "TLOU2", "TLOU Part II"],
            "save_and_config": True,
            "patterns": [
                r"{DOCS}\The Last of Us Part II",
                r"{DOCS}\The Last of Us Part II\*\savedata",
                r"{SAVEDGAMES}\The Last of Us Part II",
                r"{SAVEDGAMES}\The Last of Us Part II\*\savedata",
            ],
        },
        # ── Kingdom Come ───────────────────────────────────────────────
        "kingdomcome2": {
            "name": "Kingdom Come: Deliverance II",
            "appid": "1771300",
            "aliases": ["Kingdom Come Deliverance 2", "KCD2"],
            "save_and_config": True,
            "patterns": [
                r"{SAVEDGAMES}\kingdomcome2",
                r"{SAVEDGAMES}\kingdomcome2\saves",
                r"{SAVEDGAMES}\kingdomcome2\profiles\default",
            ],
        },
        # ── Cairn ──────────────────────────────────────────────────────
        "cairn": {
            "name": "Cairn",
            "appid": "1588550",
            "aliases": ["Cairn_RETAIL", "Cairn RETAIL"],
            "save_and_config": True,
            "patterns": [
                r"{SAVEDGAMES}\TheGameBakers\Cairn_RETAIL",
                r"{SAVEDGAMES}\TheGameBakers\Cairn_RETAIL\SAVEGAMES\RETAIL\STORY",
                r"{SAVEDGAMES}\TheGameBakers\Cairn_RETAIL\PERSISTENT\PLAYER",
                r"{SAVEDGAMES}\TheGameBakers\Cairn",
            ],
        },
        # ── FromSoftware ────────────────────────────────────────────────
        "eldenring": {
            "name": "Elden Ring",
            "appid": "1245620",
            "aliases": ["Elden Ring", "ELDEN RING"],
            "save_and_config": True,
            "patterns": [r"{APPDATA}\EldenRing"],
        },
        "sekiro": {
            "name": "Sekiro: Shadows Die Twice",
            "appid": "814380",
            "aliases": ["Sekiro", "Sekiro Shadows Die Twice"],
            "patterns": [r"{APPDATA}\Sekiro"],
        },
        "darksoulsiii": {
            "name": "DARK SOULS III",
            "appid": "374320",
            "aliases": ["Dark Souls 3", "Dark Souls III", "DS3"],
            "patterns": [r"{APPDATA}\DarkSoulsIII"],
        },
        "darksoulsii": {
            "name": "DARK SOULS II",
            "appid": "236430",
            "aliases": ["Dark Souls 2", "Dark Souls II", "DS2"],
            "patterns": [r"{APPDATA}\DarkSoulsII"],
        },
        "armoredcore6": {
            "name": "ARMORED CORE VI",
            "appid": "1888160",
            "aliases": ["Armored Core 6", "Armored Core VI", "AC6", "ACVI"],
            "patterns": [r"{APPDATA}\ArmoredCore6"],
        },
        # ── Supergiant ─────────────────────────────────────────────────
        "hades": {
            "name": "Hades",
            "appid": "1145360",
            "aliases": ["Hades"],
            "save_and_config": True,
            "patterns": [r"{APPDATA}\Hades"],
        },
        "hadesii": {
            "name": "Hades II",
            "appid": "1145350",
            "aliases": ["Hades 2", "Hades II"],
            "save_and_config": True,
            "patterns": [r"{APPDATA}\HadesII"],
        },
        "bastion": {
            "name": "Bastion",
            "appid": "107100",
            "aliases": ["Bastion"],
            "patterns": [r"{LOCAL}\Bastion"],
        },
        # ── CD Projekt Red ──────────────────────────────────────────────
        "cyberpunk2077": {
            "name": "Cyberpunk 2077",
            "appid": "1091500",
            "aliases": ["Cyberpunk 2077", "Cyberpunk", "CP2077", "CP77"],
            "save_and_config": True,
            "patterns": [r"{LOCAL}\CD Projekt Red\Cyberpunk 2077"],
        },
        "thewitcher3": {
            "name": "The Witcher 3: Wild Hunt",
            "appid": "292030",
            "aliases": ["The Witcher 3", "Witcher 3", "TW3"],
            "save_and_config": True,
            "patterns": [r"{LOCAL}\CD Projekt Red\witcher3"],
        },
        # ── Larian Studios ──────────────────────────────────────────────
        "baldursgate3": {
            "name": "Baldur's Gate 3",
            "appid": "1086940",
            "aliases": ["Baldurs Gate 3", "Baldur's Gate 3", "BG3"],
            "save_and_config": True,
            "patterns": [
                r"{LOCAL}\Larian Studios\Baldur's Gate 3",
                r"{LOCAL}\Larian Studios\Baldurs Gate 3",
            ],
        },
        "divinityoriginalsin2": {
            "name": "Divinity: Original Sin 2",
            "appid": "435150",
            "aliases": ["Divinity Original Sin 2", "DOS2"],
            "save_and_config": True,
            "patterns": [r"{LOCAL}\Larian Studios\Divinity Original Sin 2"],
        },
        # ── Bethesda / id ───────────────────────────────────────────────
        "skyrim": {
            "name": "The Elder Scrolls V: Skyrim",
            "appid": "72850",
            "aliases": ["Skyrim", "Skyrim Special Edition", "Skyrim SE", "TESV"],
            "patterns": [
                r"{LOCAL}\Skyrim Special Edition",
                r"{DOCS}\My Games\Skyrim Special Edition",
                r"{DOCS}\My Games\Skyrim",
            ],
        },
        "fallout4": {
            "name": "Fallout 4",
            "appid": "377160",
            "aliases": ["Fallout 4", "FO4"],
            "save_and_config": True,
            "patterns": [
                r"{LOCAL}\Fallout4",
                r"{DOCS}\My Games\Fallout4",
            ],
        },
        "fallout76": {
            "name": "Fallout 76",
            "appid": "1151340",
            "aliases": ["Fallout 76", "FO76"],
            "save_and_config": True,
            "patterns": [
                r"{LOCAL}\Fallout76",
                r"{DOCS}\My Games\Fallout 76",
                r"{DOCS}\My Games\Fallout76",
            ],
        },
        "starfield": {
            "name": "Starfield",
            "appid": "1716740",
            "aliases": ["Starfield"],
            "save_and_config": True,
            "patterns": [
                r"{LOCAL}\Starfield",
                r"{DOCS}\My Games\Starfield",
            ],
        },
        "doometernal": {
            "name": "DOOM Eternal",
            "appid": "782330",
            "aliases": ["DOOM Eternal", "Doom Eternal"],
            "save_and_config": True,
            "patterns": [r"{LOCAL}\id Software\DOOMEternal"],
        },
        # ── Rockstar ────────────────────────────────────────────────────
        "gtav": {
            "name": "Grand Theft Auto V",
            "appid": "271590",
            "aliases": ["GTA 5", "GTA V", "GTA5", "Grand Theft Auto V"],
            "save_and_config": True,
            "patterns": [
                r"{LOCAL}\Rockstar Games\GTA V",
                r"{DOCS}\Rockstar Games\GTA V",
            ],
        },
        "rdr2": {
            "name": "Red Dead Redemption 2",
            "appid": "1174180",
            "aliases": ["Red Dead Redemption 2", "RDR2"],
            "save_and_config": True,
            "patterns": [
                r"{LOCAL}\Rockstar Games\Red Dead Redemption 2",
                r"{DOCS}\Rockstar Games\RDR2",
            ],
        },
        # ── ConcernedApe / indie ────────────────────────────────────────
        "stardewvalley": {
            "name": "Stardew Valley",
            "appid": "413150",
            "aliases": ["Stardew Valley", "Stardew"],
            "save_and_config": True,
            "patterns": [r"{APPDATA}\StardewValley"],
        },
        "terraria": {
            "name": "Terraria",
            "appid": "105600",
            "aliases": ["Terraria"],
            "save_and_config": True,
            "patterns": [
                r"{LOCAL}\Terraria",
                r"{DOCS}\My Games\Terraria",
            ],
        },
        "hollowknight": {
            "name": "Hollow Knight",
            "appid": "367520",
            "aliases": ["Hollow Knight", "HK"],
            "save_and_config": True,
            "patterns": [r"{LOCALLOW}\Team Cherry\Hollow Knight"],
        },
        "celeste": {
            "name": "Celeste",
            "appid": "504230",
            "aliases": ["Celeste"],
            "save_and_config": True,
            "patterns": [r"{LOCAL}\Celeste"],
        },
        "factorio": {
            "name": "Factorio",
            "appid": "427520",
            "aliases": ["Factorio"],
            "save_and_config": True,
            "patterns": [r"{APPDATA}\Factorio"],
        },
        "minecraft": {
            "name": "Minecraft",
            "aliases": ["Minecraft", "Minecraft Java Edition"],
            "save_and_config": True,
            "patterns": [r"{APPDATA}\.minecraft"],
        },
        # ── Multiplayer / live-service ──────────────────────────────────
        "deeprockgalactic": {
            "name": "Deep Rock Galactic",
            "appid": "548430",
            "aliases": ["Deep Rock Galactic", "DRG"],
            "save_and_config": True,
            "patterns": [r"{LOCAL}\Deep Rock Galactic"],
        },
        "valheim": {
            "name": "Valheim",
            "appid": "892970",
            "aliases": ["Valheim"],
            "save_and_config": True,
            "patterns": [r"{LOCALLOW}\IronGate\Valheim"],
        },
        "lethalcompany": {
            "name": "Lethal Company",
            "appid": "1966720",
            "aliases": ["Lethal Company"],
            "save_and_config": True,
            "patterns": [r"{LOCALLOW}\ZeekerssRBLX\Lethal Company"],
        },
        "palworld": {
            "name": "Palworld",
            "appid": "1623730",
            "aliases": ["Palworld"],
            "save_and_config": True,
            "patterns": [r"{LOCAL}\Pal\Saved"],
        },
        "helldivers2": {
            "name": "HELLDIVERS 2",
            "appid": "553850",
            "aliases": ["Helldivers 2", "HELLDIVERS 2", "HD2"],
            "save_and_config": True,
            "patterns": [r"{APPDATA}\Arrowhead\Helldivers2"],
        },
        "nomanssky": {
            "name": "No Man's Sky",
            "appid": "275850",
            "aliases": ["No Man's Sky", "No Mans Sky", "NMS"],
            "save_and_config": True,
            "patterns": [r"{LOCAL}\HelloGames\NMS"],
        },
        "satisfactory": {
            "name": "Satisfactory",
            "appid": "526870",
            "aliases": ["Satisfactory"],
            "save_and_config": True,
            "patterns": [r"{LOCAL}\FactoryGame\Saved"],
        },
        "subnautica": {
            "name": "Subnautica",
            "appid": "264710",
            "aliases": ["Subnautica"],
            "save_and_config": True,
            "patterns": [
                r"{LOCAL}\Subnautica",
                r"{APPDATA}\Unknown Worlds\Subnautica",
            ],
        },
        "monsterhunterworld": {
            "name": "Monster Hunter: World",
            "appid": "582010",
            "aliases": ["Monster Hunter World", "MHW"],
            "save_and_config": True,
            "patterns": [r"{LOCAL}\CAPCOM\MonsterHunterWorld"],
        },
        "monsterhunterrise": {
            "name": "Monster Hunter Rise",
            "appid": "1446780",
            "aliases": ["Monster Hunter Rise", "MHRise", "MHR"],
            "save_and_config": True,
            "patterns": [r"{LOCAL}\CAPCOM\MonsterHunterRise"],
        },
        "monsterhunterwilds": {
            "name": "Monster Hunter Wilds",
            "appid": "2246340",
            "aliases": ["Monster Hunter Wilds", "MHWilds", "MHWi"],
            "save_and_config": True,
            "patterns": [r"{LOCAL}\CAPCOM\MonsterHunterWilds"],
        },
        # ── EA / Ubisoft ────────────────────────────────────────────────
        "apexlegends": {
            "name": "Apex Legends",
            "appid": "1172470",
            "aliases": ["Apex Legends", "Apex"],
            "save_and_config": True,
            "patterns": [r"{LOCAL}\Respawn\Apex"],
        },
        "thecrewmotorfest": {
            "name": "The Crew Motorfest",
            "aliases": ["The Crew Motorfest"],
            "save_and_config": True,
            "patterns": [r"{LOCAL}\Ubisoft Game Launcher\savegame_storage"],
        },
        # ── Remedy ──────────────────────────────────────────────────────
        "control": {
            "name": "Control",
            "appid": "870780",
            "aliases": ["Control"],
            "save_and_config": True,
            "patterns": [r"{LOCAL}\Remedy\Control"],
        },
        "alanwake2": {
            "name": "Alan Wake 2",
            "appid": "1088850",
            "aliases": ["Alan Wake 2", "AW2"],
            "save_and_config": True,
            "patterns": [r"{LOCAL}\Remedy\AlanWake2"],
        },
        # ── Misc popular ────────────────────────────────────────────────
        "minecraftdungeons": {
            "name": "Minecraft Dungeons",
            "appid": "1672970",
            "aliases": ["Minecraft Dungeons"],
            "save_and_config": True,
            "patterns": [r"{LOCAL}\Mojang\Minecraft Dungeons"],
        },
        "godofwar": {
            "name": "God of War",
            "appid": "1593500",
            "aliases": ["God of War", "God of War 2018"],
            "save_and_config": True,
            "patterns": [r"{LOCAL}\GodOfWar"],
        },
        "godofwarragnarok": {
            "name": "God of War Ragnar\u00f6k",
            "appid": "2322010",
            "aliases": ["God of War Ragnarok", "God of War Ragnarok 2022"],
            "save_and_config": True,
            "patterns": [r"{LOCAL}\GodOfWarRagnarok"],
        },
        "horizonzerodawn": {
            "name": "Horizon Zero Dawn",
            "appid": "1151640",
            "aliases": ["Horizon Zero Dawn", "HZD"],
            "save_and_config": True,
            "patterns": [r"{LOCAL}\HorizonZeroDawn"],
        },
        "thehuntshowdown": {
            "name": "Hunt: Showdown 1896",
            "appid": "594650",
            "aliases": ["Hunt Showdown", "Hunt: Showdown", "Hunt"],
            "save_and_config": True,
            "patterns": [r"{USERPROFILE}\Saved Games\Hunt Showdown 1896"],
        },
        "forzahorizon5": {
            "name": "Forza Horizon 5",
            "appid": "1551360",
            "aliases": ["Forza Horizon 5", "FH5"],
            "save_and_config": True,
            "patterns": [r"{LOCAL}\Packages\Microsoft.624F8B84B80*"],
        },
        "seaofthieves": {
            "name": "Sea of Thieves",
            "appid": "1172620",
            "aliases": ["Sea of Thieves", "SoT"],
            "save_and_config": True,
            "patterns": [r"{LOCAL}\Packages\Microsoft.SeaofThieves*"],
        },
        "deathstranding": {
            "name": "Death Stranding",
            "appid": "1190460",
            "aliases": ["Death Stranding", "Death Stranding DC"],
            "save_and_config": True,
            "patterns": [r"{LOCAL}\KojimaProductions"],
        },
        "liesofp": {
            "name": "Lies of P",
            "appid": "1627720",
            "aliases": ["Lies of P"],
            "save_and_config": True,
            "patterns": [r"{LOCAL}\Lies of P"],
        },
        "returnal": {
            "name": "Returnal",
            "appid": "1649080",
            "aliases": ["Returnal"],
            "save_and_config": True,
            "patterns": [r"{LOCAL}\Returnal"],
        },
        "dragonsdogma2": {
            "name": "Dragon's Dogma 2",
            "appid": "2054970",
            "aliases": ["Dragons Dogma 2", "Dragon's Dogma 2", "DD2"],
            "save_and_config": True,
            "patterns": [r"{APPDATA}\Dragons Dogma 2"],
        },
        "warframe": {
            "name": "Warframe",
            "appid": "230410",
            "aliases": ["Warframe"],
            "save_and_config": True,
            "patterns": [r"{LOCAL}\Warframe"],
        },
        "pathofexile": {
            "name": "Path of Exile",
            "appid": "238960",
            "aliases": ["Path of Exile", "POE"],
            "save_and_config": True,
            "patterns": [r"{LOCAL}\GrindingGearGames\Path of Exile"],
        },
        "pathofexile2": {
            "name": "Path of Exile 2",
            "appid": "2694490",
            "aliases": ["Path of Exile 2", "POE2"],
            "save_and_config": True,
            "patterns": [r"{LOCAL}\GrindingGearGames\Path of Exile 2"],
        },
        # Curated LocalLow layouts verified from real user installations.
        # Engine/store-aware paths discovered from real installations. These
        # remain exact rules, not arbitrary LocalLow folder guesses.
        "catobutteredcat": {
            "name": "CATO: Buttered Cat", "appid": "1999520",
            "aliases": ["CATO", "CATO: Buttered Cat"],
            "patterns": [r"{LOCALLOW}\Team Woll\CATO"],
        },
        "fearstofathomscratchcreek": {
            "name": "Fears to Fathom - Scratch Creek", "appid": "4121170",
            "aliases": ["Fears to Fathom - Scratch Creek"],
            "patterns": [r"{LOCALLOW}\Rayll Studios\Fears to Fathom - Scratch Creek"],
        },
        "plagueincevolved": {
            "name": "Plague Inc: Evolved", "appid": "246620",
            "aliases": ["Plague Inc Evolved", "Plague Inc. Evolved"],
            "patterns": [r"{LOCAL}\Ndemic Creations\Plague Inc. Evolved"],
        },
        "deathstranding2": {
            "name": "DEATH STRANDING 2: ON THE BEACH", "appid": "3280350",
            "aliases": ["DEATH STRANDING 2 ON THE BEACH"],
            "patterns": [r"{LOCAL}\DEATH STRANDING 2 - ON THE BEACH"],
        },
        "towntocity": {
            "name": "Town To City", "appid": "3115220",
            "aliases": ["Town To City", "TownToCity"],
            "patterns": [r"{LOCAL}\TownToCity"],
        },
        "wildwestdynasty": {
            "name": "Wild West Dynasty", "appid": "1329880",
            "aliases": ["Wild West Dynasty", "wwd"],
            "patterns": [r"{LOCALLOW}\MPS\wwd"],
        },
        "goingmedieval": {
            "name": "Going Medieval", "appid": "1029780",
            "aliases": ["Going Medieval", "Foxy Voxel_Going Medieval"],
            "patterns": [r"{LOCALLOW}\Unity\Foxy Voxel_Going Medieval"],
        },
        "pcbuildingsimulator2": {
            "name": "PC Building Simulator 2",
            "aliases": ["PC Building Simulator 2", "PCBS2"],
            "patterns": [r"{LOCALLOW}\Epic Games Publishing\PCBS2", r"{LOCAL}\PCBS2\Saved\SaveGames"],
        },
        "mecchachameleon": {
            "name": "MECCHA CHAMELEON", "appid": "4704690",
            "aliases": ["MECCHA CHAMELEON", "Meccha Chameleon", "Chameleon"],
            "patterns": [r"{LOCAL}\Chameleon"],
        },
        "eurotrucksimulator2": {
            "name": "Euro Truck Simulator 2", "appid": "227300",
            "aliases": ["Euro Truck Simulator 2", "euro_truck_simulator_2", "ETS2"],
            "patterns": [],
        },
        "indianajonesandthegreatcircle": {
            "name": "Indiana Jones and the Great Circle", "appid": "2677660",
            "aliases": ["Indiana Jones and the Great Circle", "TheGreatCircle", "The Great Circle"],
            "patterns": [r"{SAVEDGAMES}\MachineGames\TheGreatCircle"],
        },
        "burglignomes": {
            "name": "Burglin' Gnomes", "appid": "3844970",
            "aliases": ["Burglin Gnomes", "Gnomium"],
            "patterns": [r"{LOCALLOW}\*\Gnomium"],
        },
        "bladeandsorcery": {
            "name": "Blade & Sorcery", "appid": "629730",
            "aliases": ["Blade and Sorcery", "Blade & Sorcery", "BladeAndSorcery"],
            "patterns": [r"{LOCALLOW}\Warpfrog\BladeAndSorcery"],
        },
        "castnchill": {
            "name": "Cast n Chill", "appid": "3483740",
            "aliases": ["Cast n Chill", "CastNChill"],
            "patterns": [r"{LOCALLOW}\Wombat Brawler\Cast n Chill"],
        },
        "spaceflightsimulator": {
            "name": "Spaceflight Simulator", "appid": "1718870",
            "aliases": ["Spaceflight Simulator", "SpaceflightSimulator"],
            "patterns": [r"{LOCALLOW}\Stef Morojna\Spaceflight Simulator"],
        },
        "botanymanor": {
            "name": "Botany Manor", "appid": "1425350", "aliases": ["Botany Manor"],
            "patterns": [r"{LOCALLOW}\Balloon Studios\Botany Manor"],
        },
        "dontsleepwiththefishes": {
            "name": "Don't Sleep With The Fishes", "appid": "4834070",
            "aliases": ["Dont Sleep With The Fishes", "DontSleepWithTheFishes"],
            "patterns": [r"{LOCALLOW}\DopplerGhost\DontSleepWithTheFishes"],
        },
        "inazumaelevenvictoryroad": {
            "name": "INAZUMA ELEVEN: Victory Road", "appid": "2799860",
            "aliases": ["INAZUMA ELEVEN Victory Road", "INAZUMA ELEVEN Victory Road"],
            "patterns": [r"{LOCALLOW}\LEVEL5 Inc_\INAZUMA ELEVEN Victory Road"],
        },
        "thepedestrian": {
            "name": "The Pedestrian", "appid": "466630", "aliases": ["The Pedestrian"],
            "patterns": [r"{LOCALLOW}\Skookum Arts\The Pedestrian"],
        },
        "theplanetcrafter": {
            "name": "The Planet Crafter", "appid": "1284190",
            "aliases": ["Planet Crafter", "The Planet Crafter"],
            "patterns": [r"{LOCALLOW}\MijuGames\Planet Crafter"],
        },
        "yeahyouwantthosegames": {
            "name": "YEAH! YOU WANT \"THOSE GAMES,\" RIGHT? SO HERE YOU GO! NOW, LET'S SEE YOU CLEAR THEM!", "appid": "2348100",
            "aliases": ["THOSE GAMES", "Yeah You Want Those Games"],
            "patterns": [r"{LOCALLOW}\D3PUBLISHER Inc_\THOSE GAMES"],
        },
        "remnant2": {
            "name": "Remnant 2",
            "appid": "1282100",
            "aliases": ["Remnant 2", "Remnant II"],
            "save_and_config": True,
            "patterns": [r"{LOCAL}\Remnant2"],
        },
    }

    NON_GAME_FOLDER_NAMES = {
        "achievements", "adobe", "amd", "apple", "atlauncher", "audacity", "blender foundation", "lua",
        "betterdiscord", "brave", "cache", "code", "discord", "docker", "dropbox", "electron", "powershell", "windowspowershell", "modules",
        "equicord", "epicgameslauncher", "githubdesktop", "google", "gog.com", "intel", "java",
        "jetbrains", "microsoft", "mozilla", "nodejs", "notepad++", "npm",
        "nvidia", "obs-studio", "obsstudio", "openasar", "opera software", "python", "qtproject",
        "spotify", "telegram desktop", "telegramdesktop", "unity", "unreal engine", "vencord",
        "valve", "vlc", "vscode", "windows", "zoom",
        # Non-game apps that commonly appear in AppData
        "everything", "arena", "battle.net", "battlenet", "blizzard", "curseforge",
        "directx", "dotnet", "eac", "easyanticheat", "epic online services",
        "fraps", "geforce experience", "hwinfo", "icue", "logitech",
        "mumble", "nvidia corporation", "obs", "origin", "overwolf",
        "razer", "realtek", "redist", "rockstar games launcher", "ryzen",
        "sharex", "steelseries", "streamlabs", "teamspeak", "twitch", "ubisoft",
        "vulkan", "xbox", "xboxgamebar", "xboxlive",
        # System/cache folders that appear in AppData
        "crashreports", "crashreportclient", "cryptneturlcache", "dxcache",
        "internet explorer", "shadercache", "d3dscache", "gpucache",
        "code cache", "gpu cache", "service worker", "blob_storage",
        "cache storage", "session storage", "indexeddb", "local storage",
        "shared storage", "webrtc event logs", "crashpad", "pending",
        "compatdata", "compatibility", "temp", "tmp",
        "poweryoys", "unknown unity application", "unitycrashhandler64",
        "unitycrashhandler32", "crashhandler", "dotnetruntime",
        "asp.net", "windowsapps", "packages", "temp", "tmp",
        "pending", "crashpad", "crashreportclient", "shadercache",
        "d3dscache", "gpucache", "code cache", "gpu cache",
        "service worker", "blob_storage", "cache storage",
        "session storage", "indexeddb", "local storage",
        "shared storage", "webrtc event logs", "compatdata",
        "compatibility", "crashreports", "cryptneturlcache",
        "dxcache", "internet explorer",
    }

    @staticmethod
    def env_map() -> dict[str, str]:
        user = os.environ.get("USERPROFILE") or str(Path.home())
        return {
            "{APPDATA}": os.environ.get("APPDATA", os.path.join(user, "AppData", "Roaming")),
            "{LOCAL}": os.environ.get("LOCALAPPDATA", os.path.join(user, "AppData", "Local")),
            "{LOCALLOW}": os.path.join(user, "AppData", "LocalLow"),
            "{DOCS}": os.path.join(user, "Documents"),
            "{PUBLICDOCS}": os.path.join(os.environ.get("PUBLIC", r"C:\Users\Public"), "Documents"),
            "{PROGRAMDATA}": os.environ.get("PROGRAMDATA", r"C:\ProgramData"),
            "{USERPROFILE}": user,
            "{SAVEDGAMES}": os.path.join(user, "Saved Games"),
            "{STEAM}": r"C:\Program Files (x86)\Steam",
            "{UBISOFT}": os.path.join(os.environ.get("PROGRAMFILES(X86)", os.environ.get("PROGRAMFILES", r"C:\Program Files (x86)")), "Ubisoft", "Ubisoft Game Launcher"),
        }

    @classmethod
    def expand_vars(cls, value: str) -> str:
        result = str(value or "")
        for key, replacement in cls.env_map().items():
            result = result.replace(key, replacement)
        result = os.path.expandvars(result)
        if os.sep == "/":
            result = result.replace("\\", os.sep)
        return result

    @staticmethod
    def _dedupe(values: list[str], limit: int = 32) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for value in values:
            value = str(value or "").strip()
            if not value:
                continue
            key = value.lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(value)
            if len(out) >= limit:
                break
        return out

    @classmethod
    def known_rule_for_name(cls, name: str) -> dict[str, Any] | None:
        norm = normalize_name(name)
        if not norm:
            return None
        if norm in cls.KNOWN_GAMES:
            return cls.KNOWN_GAMES[norm]
        for rule in cls.KNOWN_GAMES.values():
            keys = [rule.get("name", ""), *(rule.get("aliases") or [])]
            if norm in {normalize_name(item) for item in keys}:
                return rule
        return None

    @classmethod
    def known_rule_for_pattern(cls, pattern: str) -> dict[str, Any] | None:
        """Find the KNOWN_GAMES rule that owns a specific scan pattern."""
        wanted = str(pattern or "").lower()
        if not wanted:
            return None
        for rule in cls.KNOWN_GAMES.values():
            for candidate in rule.get("patterns") or []:
                if str(candidate or "").lower() == wanted:
                    return rule
        return None

    @classmethod
    def canonical_game_name(cls, name: str) -> str:
        rule = cls.known_rule_for_name(name)
        return str((rule or {}).get("name") or name or "").strip()

    @classmethod
    def folder_names_for_game(cls, game: dict[str, Any]) -> list[str]:
        raw = str(game.get("name") or "").strip()
        values = cls._title_save_folder_variants(raw)
        # Also generate common name variations (underscores, hyphens, no-spaces)
        for variant in list(values):
            values.extend(get_name_variations(variant))
        # Remove common non-game suffixes from store titles.
        if raw:
            values.append(re.sub(r"\s*[-+:|]?\s*(demo|playtest|soundtrack|dedicated server)$", "", raw, flags=re.I).strip())
        rule = cls.known_rule_for_name(raw)
        if rule:
            values.append(str(rule.get("name") or ""))
            values.extend(str(item) for item in (rule.get("aliases") or []))
        return cls._dedupe(values, limit=48)

    @classmethod
    def _title_save_folder_variants(cls, name: str) -> list[str]:
        """Generate conservative title variants used by save folders.

        Store titles often include trademark symbols or edition suffixes that
        folder names omit, and PC folders may use Roman numerals while Steam
        titles use Arabic numerals. Keep this bounded to exact title variants so
        Home search improves without reintroducing broad AppData scanning.
        """
        raw = str(name or "").strip()
        if not raw:
            return []
        cleaned = re.sub(r"[™®©]", "", raw).replace("(TM)", "").strip()
        variants = {raw, cleaned}
        suffix_pattern = r"\s*[-:–—]?\s*(remastered|remake|definitive edition|complete edition|director'?s cut|game of the year edition|goty edition)$"
        for value in list(variants):
            stripped = re.sub(suffix_pattern, "", value, flags=re.I).strip()
            if stripped and stripped != value:
                variants.add(stripped)
        roman_pairs = [
            (r"\bPart\s+1\b", "Part I"),
            (r"\bPart\s+I\b", "Part 1"),
            (r"\bPart\s+2\b", "Part II"),
            (r"\bPart\s+II\b", "Part 2"),
            (r"\bII\b", "2"),
            (r"\bIII\b", "3"),
            (r"\bIV\b", "4"),
        ]
        for value in list(variants):
            for pattern, replacement in roman_pairs:
                converted = re.sub(pattern, replacement, value, flags=re.I).strip()
                if converted and converted != value:
                    variants.add(converted)
        return [item for item in variants if item]

    @classmethod
    def _saved_games_folder_candidates(cls, game_name: str) -> list[str]:
        """Candidate folders under Saved Games/Documents for one title.

        These are still focused on a selected title, but they cover common
        nested layouts:
        - Saved Games/<Game>/users/<id>/savedata
        - Saved Games/<Studio>/<Game>/SAVEGAMES
        """
        folders: list[str] = []
        roots = [
            r"{SAVEDGAMES}\{GAME}",
            r"{SAVEDGAMES}\*\{GAME}",
            r"{DOCS}\{GAME}",
            r"{DOCS}\*\{GAME}",
        ]
        subfolders = [
            "",
            r"\savedata",
            r"\SaveData",
            r"\SAVEGAMES",
            r"\SaveGames",
            r"\savegames",
            r"\saves",
            r"\Saves",
            r"\PERSISTENT",
            r"\PERSISTENT\PLAYER",
            r"\users\*",
            r"\users\*\savedata",
            r"\users\*\SaveData",
            r"\users\*\saves",
            r"\users\*\Saves",
            r"\*\savedata",
            r"\*\SaveData",
            r"\*\SAVEGAMES",
            r"\*\saves",
            r"\*\Saves",
        ]
        for root in roots:
            for subfolder in subfolders:
                folders.append((root + subfolder).replace("{GAME}", game_name))
        return folders

    @classmethod
    def people_for_game(cls, game: dict[str, Any]) -> list[str]:
        values: list[str] = []
        for key in ("developers", "publishers"):
            for name in game.get(key, []) or []:
                clean = str(name or "").strip()
                if clean:
                    values.append(clean)
        return cls._dedupe(values, limit=10)

    @staticmethod
    def _nice_description(description: str, source: str = "") -> str:
        # Do not show "(Heuristic)" to users. It is developer jargon and made
        # entries look messy. PCGW/manifest labels remain useful and visible.
        if not source or source.lower() in {"heuristic", "common pattern", "verified", "save scan", "known rule"}:
            return description
        return f"{description} ({source})"

    @classmethod
    def _path_entry(cls, path: str, category: str, description: str, source: str = "") -> dict[str, Any] | None:
        if not path or not os.path.exists(path):
            return None
        return {
            "path": path,
            "category": category,
            "description": cls._nice_description(description, source),
            "source": source or "common_pattern",
            "risk": "caution",
            "size": path_size(path),
            "is_dir": os.path.isdir(path),
        }

    @classmethod
    def _add_matches(
        cls,
        results: list[dict[str, Any]],
        seen: set[str],
        pattern: str,
        category: str,
        description: str,
        source: str = "",
    ) -> None:
        expanded = cls.expand_vars(pattern)
        try:
            matches = glob.glob(expanded) if any(ch in expanded for ch in "*?") else ([expanded] if os.path.exists(expanded) else [])
        except Exception:
            matches = []
        for match in matches:
            entry = cls._path_entry(match, category, description, source)
            if not entry:
                continue
            norm = os.path.normcase(os.path.normpath(entry["path"]))
            if norm in seen:
                continue
            seen.add(norm)
            results.append(entry)

    @classmethod
    def common_save_paths(cls, game: dict[str, Any]) -> list[dict[str, Any]]:
        game_names = cls.folder_names_for_game(game)
        people = cls.people_for_game(game)
        results: list[dict[str, Any]] = []
        seen: set[str] = set()

        # Curated patterns first. These solve folder-name mismatches like
        # HITMAN3 and ACE without guessing through unrelated software folders.
        rule = cls.known_rule_for_name(str(game.get("name") or ""))
        if rule:
            for pattern in rule.get("patterns") or []:
                category = "Config Files" if "config" in str(pattern).lower() else "Save Files"
                description = "Save and config folder" if rule.get("save_and_config") else ("Config folder" if category == "Config Files" else "Save folder")
                if rule.get("save_and_config"):
                    category = "Save & Config Files"
                cls._add_matches(results, seen, pattern, category, description, "Known rule")
            if rule.get("patterns_only"):
                results.sort(key=lambda item: (item["category"], item["path"].lower()))
                return results

        for game_name in game_names:
            templates = [
                (r"{APPDATA}\Godot\app_userdata\{GAME}", "Save Files", "Godot app_userdata save folder"),
                (r"{LOCAL}\{GAME}\Saved\SaveGames", "Save Files", "Unreal Engine SaveGames folder"),
                (r"{LOCAL}\{GAME}\Saved", "Save Files", "Unreal Engine Saved folder"),
                (r"{LOCAL}\{GAME}\Saved\Config", "Config Files", "Unreal Engine config folder"),
                (r"{SAVEDGAMES}\{GAME}", "Save Files", "Windows Saved Games folder"),
                (r"{DOCS}\My Games\{GAME}", "Save Files", "Documents My Games folder"),
                (r"{DOCS}\{GAME}", "Save Files", "Documents game folder"),
                (r"{APPDATA}\{GAME}", "Save Files", "Roaming app data folder"),
                (r"{LOCAL}\{GAME}", "Save Files", "Local app data folder"),
                (r"{LOCALLOW}\{GAME}", "Save Files", "LocalLow app data folder"),
                (r"{APPDATA}\*\Epic\*\{GAME}", "Save Files", "Epic nested user save folder"),
                (r"{LOCAL}\*\Epic\*\{GAME}", "Save Files", "Epic nested local save folder"),
            ]
            # Unity engine common paths
            unity_templates = [
                (r"{LOCALLOW}\{GAME}", "Save Files", "Unity LocalLow save folder"),
                (r"{LOCALLOW}\{GAME}\*\*", "Save Files", "Unity LocalLow nested save"),
                (r"{LOCAL}\{GAME}\data", "Save Files", "Game data folder"),
                (r"{LOCAL}\{GAME}\profiles", "Save Files", "Game profiles folder"),
                (r"{SAVEDGAMES}\{GAME}\*", "Save Files", "Saved Games nested folder"),
                (r"{DOCS}\{GAME}\*", "Save Files", "Documents nested folder"),
            ]
            for template, category, description in unity_templates:
                cls._add_matches(results, seen, template.replace("{GAME}", game_name), category, description)

            for template, category, description in templates:
                cls._add_matches(results, seen, template.replace("{GAME}", game_name), category, description)

            # Focused Saved Games/Documents search for this specific game.
            # This is how v3.1 finds games in those locations without broad scanning.
            for candidate in cls._saved_games_folder_candidates(game_name):
                cls._add_matches(results, seen, candidate, "Save Files", "Saved Games/Documents save folder")

            for person in people:
                person_templates = [
                    (r"{APPDATA}\{PERSON}\{GAME}", "Save Files", "Developer/publisher Roaming folder"),
                    (r"{LOCAL}\{PERSON}\{GAME}", "Save Files", "Developer/publisher Local folder"),
                    (r"{LOCAL}\{PERSON}\{GAME}\SaveGames", "Save Files", "Developer/publisher SaveGames folder"),
                    (r"{LOCAL}\{PERSON}\{GAME}\Saved", "Save Files", "Developer/publisher Saved folder"),
                    (r"{LOCAL}\{PERSON}\{GAME}\Saved\SaveGames", "Save Files", "Developer/publisher Saved SaveGames folder"),
                    (r"{LOCAL}\{PERSON}\{GAME}\Saved\Config", "Config Files", "Developer/publisher config folder"),
                    (r"{LOCALLOW}\{PERSON}\{GAME}", "Save Files", "Unity LocalLow developer folder"),
                    (r"{APPDATA}\{PERSON}\Epic\*\{GAME}", "Save Files", "Publisher Epic nested user save folder"),
                    (r"{LOCAL}\{PERSON}\Epic\*\{GAME}", "Save Files", "Publisher Epic nested local save folder"),
                ]
                for template, category, description in person_templates:
                    cls._add_matches(
                        results,
                        seen,
                        template.replace("{PERSON}", person).replace("{GAME}", game_name),
                        category,
                        description,
                    )

        results.sort(key=lambda item: (item["category"], item["path"].lower()))
        return results

    @staticmethod
    def _pcgw_cache_key(game: dict[str, Any]) -> str:
        appid = str(game.get("appid") or "").strip()
        if appid.isdigit():
            return f"steam:{appid}"
        return f"name:{normalize_name(str(game.get('name', '')))}"

    @classmethod
    def _pcgw_api_json(cls, params: dict[str, str], timeout: int = 6) -> dict[str, Any] | None:
        url = "https://www.pcgamingwiki.com/w/api.php?" + urllib.parse.urlencode(params)
        request = urllib.request.Request(url, headers={"User-Agent": "GhostHunterPro/SaveScanner"})
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8", errors="replace"))
        except Exception:
            return None

    @classmethod
    def _pcgw_page_title(cls, game: dict[str, Any]) -> str:
        appid = str(game.get("appid") or "").strip()
        if appid.isdigit():
            data = cls._pcgw_api_json({
                "action": "cargoquery",
                "tables": "Infobox_game",
                "fields": "Infobox_game._pageName=Page",
                "where": f'Infobox_game.Steam_AppID HOLDS "{appid}"',
                "format": "json",
            })
            try:
                title = data["cargoquery"][0]["title"]["Page"]
                if title:
                    return str(title)
            except Exception:
                pass
        name = str(game.get("name") or "").strip()
        if not name:
            return ""
        data = cls._pcgw_api_json({
            "action": "opensearch",
            "search": name,
            "redirects": "resolve",
            "limit": "1",
            "format": "json",
        })
        try:
            return str(data[1][0]) if data and len(data) > 1 and data[1] else ""
        except Exception:
            return ""

    @classmethod
    def _pcgw_wikitext(cls, title: str) -> str:
        if not title:
            return ""
        data = cls._pcgw_api_json({"action": "parse", "format": "json", "page": title, "prop": "wikitext"})
        try:
            return str(data["parse"]["wikitext"]["*"])
        except Exception:
            return ""

    @staticmethod
    def _strip_wiki_markup(text: str) -> str:
        value = text or ""
        replacements = {
            r"{{p|appdata}}": "{APPDATA}",
            r"{{p|localappdata}}": "{LOCAL}",
            r"{{p|userprofile}}": "{USERPROFILE}",
            r"{{p|documents}}": "{DOCS}",
            r"{{p|savedgames}}": "{SAVEDGAMES}",
            r"{{p|programdata}}": "{PROGRAMDATA}",
            r"{{p|public}}": os.environ.get("PUBLIC", r"C:\Users\Public"),
            r"{{p|steam}}": "{STEAM}",
        }
        for old, new in replacements.items():
            # Lambda avoids re.sub interpreting Windows paths as escapes (\U).
            value = re.sub(re.escape(old), lambda _m, replacement=new: replacement, value, flags=re.I)
        value = re.sub(r"\[https?://[^\s\]]+\s+([^\]]+)\]", r"\1", value)
        value = re.sub(r"\[\[([^\]|]+\|)?([^\]]+)\]\]", r"\2", value)
        value = value.replace("&lt;", "<").replace("&gt;", ">")
        value = re.sub(r"<[^>]+>", "*", value)
        value = re.sub(r"{{[^{}]*}}", "", value)
        value = value.replace("[*]", "*")
        return value.strip()

    @classmethod
    def _extract_pcgw_paths(cls, wikitext: str) -> list[tuple[str, str]]:
        if not wikitext:
            return []
        section_match = re.search(
            r"(=+\s*Game data\s*=+.*?)(?:\n=+\s*(?:Video|Input|Audio|Network|Issues|Other information|System requirements)\s*=+|\Z)",
            wikitext,
            flags=re.I | re.S,
        )
        section = section_match.group(1) if section_match else wikitext
        results: list[tuple[str, str]] = []
        for raw_line in section.splitlines():
            line = raw_line.strip()
            low = line.lower()
            if not any(token in low for token in ("{{p|", "%appdata%", "%localappdata%", "%userprofile%", "windows")):
                continue
            cleaned = cls._strip_wiki_markup(line)
            candidates = re.findall(
                r"(?:\{(?:APPDATA|LOCAL|LOCALLOW|DOCS|USERPROFILE|SAVEDGAMES|PROGRAMDATA|STEAM)\}|%[A-Z_]+%|[A-Z]:\\)[^|\n\r}]+",
                cleaned,
                flags=re.I,
            )
            for candidate in candidates:
                candidate = candidate.strip().strip(" .;,:|").replace("/", "\\")
                if len(candidate) < 5:
                    continue
                kind = "Config Files" if "config" in low else "Save Files"
                results.append((candidate, kind))
        seen: set[str] = set()
        out: list[tuple[str, str]] = []
        for path, kind in results:
            key = path.lower()
            if key in seen:
                continue
            seen.add(key)
            out.append((path, kind))
        return out[:16]

    @classmethod
    def _pcgw_html_save_paths(cls, title: str) -> list[tuple[str, str]]:
        """Fallback: parse the 'Save game data location' section HTML directly.

        Ambidex uses this approach — it can catch paths that wikitext parsing
        misses because the HTML table rows are more structured.
        """
        if not title:
            return []
        # First find the section index for "Save game data location"
        sections_data = cls._pcgw_api_json({
            "action": "parse", "format": "json", "page": title, "prop": "sections",
        })
        if not sections_data or "parse" not in sections_data:
            return []
        save_section_index = None
        for section in sections_data["parse"].get("sections", []):
            if section.get("line", "").strip().lower() == "save game data location":
                save_section_index = section.get("index")
                break
        if not save_section_index:
            return []

        content_data = cls._pcgw_api_json({
            "action": "parse", "format": "json", "page": title,
            "section": save_section_index, "prop": "text",
        })
        if not content_data or "parse" not in content_data:
            return []

        html_content = ""
        try:
            html_content = content_data["parse"]["text"]["*"]
        except Exception:
            return []

        row_pattern = (
            r'<th\s+scope="row"\s+class="table-gamedata-body-system">(.*?)</th>'
            r'\s*?<td\s+class="table-gamedata-body-location"><span[^>]*>(.*?)</span></td>'
        )
        store_rows = re.findall(row_pattern, html_content, re.DOTALL)

        results: list[tuple[str, str]] = []
        seen: set[str] = set()

        for store_type_raw, path_html in store_rows:
            store_type = re.sub(r"<[^>]+>", "", store_type_raw).strip()
            store_lower = store_type.lower()
            if any(skip in store_lower for skip in ["linux", "macos", "os x", "playstation", "xbox", "switch", "android", "ios"]):
                continue

            # Split by <br> tags for multiple paths per platform
            parts = re.split(r"<br\s*/?>", path_html)
            for idx, part in enumerate(parts):
                clean = re.sub(r"<[^>]+>", "", part).strip()
                if not clean or len(clean) < 5:
                    continue
                if any(artifact in clean for artifact in ["</th>", "<td", "</tr>", "<tr", 'class="', 'scope="']):
                    continue

                # Expand environment variables
                expanded = clean
                env_map_local = {
                    "%USERPROFILE%": os.environ.get("USERPROFILE", ""),
                    "%APPDATA%": os.environ.get("APPDATA", ""),
                    "%LOCALAPPDATA%": os.environ.get("LOCALAPPDATA", ""),
                    "%PUBLIC%": os.environ.get("PUBLIC", ""),
                    "%PROGRAMDATA%": os.environ.get("PROGRAMDATA", ""),
                }
                for env_key, env_val in env_map_local.items():
                    if env_key.upper() in expanded.upper():
                        # Lambda avoids re.sub interpreting Windows paths as escapes (\U).
                        expanded = re.sub(re.escape(env_key), lambda _m, v=env_val: v, expanded, flags=re.IGNORECASE)
                # Also handle {{p|...}} wiki placeholders
                expanded = cls._strip_wiki_markup(expanded)

                norm_key = expanded.lower().replace("/", "\\")
                if norm_key in seen:
                    continue
                seen.add(norm_key)

                kind = "Config Files" if "config" in store_lower else "Save Files"
                label = f"{store_type} [{idx + 1}]" if len(parts) > 1 else store_type
                results.append((expanded, kind))

        return results[:16]

    @classmethod
    def pcgw_save_paths(cls, game: dict[str, Any], fetch_missing: bool = True) -> list[dict[str, Any]]:
        cache = safe_read_json(PCGW_CACHE_FILE, {})
        key = cls._pcgw_cache_key(game)
        if isinstance(cache, dict) and key in cache:
            raw_paths = cache.get(key) or []
        elif fetch_missing:
            title = cls._pcgw_page_title(game)
            # Try wikitext parsing first
            raw_paths = cls._extract_pcgw_paths(cls._pcgw_wikitext(title))
            # If wikitext found nothing, try HTML section parsing (ambidex approach)
            if not raw_paths and title:
                html_paths = cls._pcgw_html_save_paths(title)
                if html_paths:
                    raw_paths = html_paths
            if isinstance(cache, dict):
                cache[key] = raw_paths
                safe_write_json(PCGW_CACHE_FILE, cache)
        else:
            raw_paths = []

        results: list[dict[str, Any]] = []
        seen: set[str] = set()
        for path, kind in raw_paths or []:
            description = "Confirmed config file" if kind == "Config Files" else "Confirmed save folder"
            cls._add_matches(results, seen, path, kind, description, "verified")
        return results

    @staticmethod
    def _merge_categories(parent_category: str, child_category: str) -> str:
        categories = {str(parent_category or ""), str(child_category or "")}
        if "Save & Config Files" in categories:
            return "Save & Config Files"
        if "Save Files" in categories and "Config Files" in categories:
            return "Save & Config Files"
        return str(parent_category or child_category or "Save Files")

    @staticmethod
    def _description_for_category(category: str, fallback: str = "") -> str:
        if category == "Save & Config Files":
            return "Save and config folder"
        if category == "Config Files":
            return "Config folder"
        if category == "Save Files":
            return "Save folder"
        return fallback or "Detected folder"

    @classmethod
    def collapse_nested_paths(cls, paths: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Return one canonical displayed path list.

        If a file/folder is already inside another selected folder, keep the
        parent folder but merge the child's meaning into it. For example, if a
        game has saves and config files in the same folder, show one parent item
        as "Save & Config Files" instead of hiding the config meaning.
        """
        unique: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item in paths or []:
            raw = str(item.get("path") or "")
            if not raw or not os.path.exists(raw):
                continue
            norm = os.path.normcase(os.path.normpath(raw))
            if norm in seen:
                continue
            seen.add(norm)
            unique.append(dict(item))

        # Shortest paths first, so parents win over children.
        unique.sort(key=lambda item: (len(os.path.normpath(str(item.get("path") or ""))), str(item.get("path") or "").lower()))
        kept: list[dict[str, Any]] = []
        kept_norm_dirs: list[tuple[str, dict[str, Any]]] = []
        for item in unique:
            raw = str(item.get("path") or "")
            norm = os.path.normcase(os.path.normpath(raw))
            parent_item = next((parent for parent_norm, parent in kept_norm_dirs if norm == parent_norm or norm.startswith(parent_norm + os.sep)), None)
            if parent_item is not None:
                merged_category = cls._merge_categories(str(parent_item.get("category") or ""), str(item.get("category") or ""))
                parent_item["category"] = merged_category
                parent_item["description"] = cls._description_for_category(merged_category, str(parent_item.get("description") or ""))
                parent_item["contains_nested_paths"] = True
                continue
            kept.append(item)
            if os.path.isdir(raw):
                kept_norm_dirs.append((norm, item))

        kept.sort(key=lambda item: (str(item.get("category") or ""), str(item.get("path") or "").lower()))
        return kept

    @classmethod
    def find_save_paths(
        cls,
        game: dict[str, Any],
        include_online: bool = False,
        fetch_online: bool = True,
    ) -> list[dict[str, Any]]:
        results = cls.common_save_paths(game)
        seen = {os.path.normcase(os.path.normpath(item["path"])) for item in results}
        if include_online:
            for item in cls.pcgw_save_paths(game, fetch_missing=fetch_online):
                norm = os.path.normcase(os.path.normpath(item["path"]))
                if norm in seen:
                    continue
                seen.add(norm)
                results.append(item)
        return cls.collapse_nested_paths(results)

    @classmethod
    def _candidate_scan_patterns(cls) -> list[tuple[str, str]]:
        patterns: list[tuple[str, str]] = []
        for rule in cls.KNOWN_GAMES.values():
            for pattern in rule.get("patterns") or []:
                patterns.append((pattern, "known"))
        patterns.extend([
            (r"{APPDATA}\Godot\app_userdata\*", "godot"),
            (r"{LOCAL}\*\Saved", "unreal"),
            (r"{LOCAL}\*\Saved\SaveGames", "unreal"),
            (r"{LOCAL}\*\Saved\Config", "unreal_config"),
            (r"{LOCAL}\*\Saved\Config\Windows", "unreal_config"),
            (r"{LOCAL}\*\*\SaveGames", "publisher_savegames"),
            (r"{APPDATA}\*", "top_appdata"),
            (r"{DOCS}\My Games\*", "mygames"),
            (r"{DOCS}\*", "documents"),
            (r"{SAVEDGAMES}\*", "savedgames"),
            (r"{LOCALLOW}\*", "locallow"),
            (r"{LOCALLOW}\*\*", "locallow_nested"),
            (r"{UBISOFT}\savegames\*", "ubisoft"),
        ])
        return patterns

    @classmethod
    def _name_from_candidate_path(cls, path: str) -> str:
        current = Path(path)
        name = current.name
        norm = normalize_name(name)
        if norm in {"windows", "win64", "win32"} and normalize_name(current.parent.name) == "config":
            current = current.parent
            name = current.name
            norm = normalize_name(name)
        # Navigate up through save-related folder names to find the actual game.
        if norm in {
            "saved", "savegames", "savedata", "saves", "config", "cfg",
            "profiles", "profile", "persistent", "player", "story", "retail",
            "setups", "replay", "screenshots", "mods", "logs", "cache",
            "data", "userdata", "output", "input", "bin", "build",
            "backup", "bak", "old", "temp", "tmp", "copy", "archive",
            "exports", "imports", "settings", "preferences", "options",
            "autosave", "manualsave", "slots", "characters",
        }:
            parent = current.parent
            parent_norm = normalize_name(parent.name)
            if norm in {"savegames", "config", "cfg"} and parent_norm == "saved":
                parent = parent.parent
            elif norm in {"savedata", "saves"} and normalize_name(parent.parent.name) == "users":
                parent = parent.parent.parent
            elif norm == "story" and parent_norm == "retail" and normalize_name(parent.parent.name) in {"savegames", "savedata", "saves"}:
                parent = parent.parent.parent
            elif norm in {"story", "retail"} and parent_norm in {"savegames", "savedata", "saves"}:
                parent = parent.parent
            elif norm in {"player"} and normalize_name(parent.name) == "persistent":
                parent = parent.parent
            elif parent_norm in {"users", "user", "profiles", "profile"}:
                parent = parent.parent
            name = parent.name
        elif norm in {"users", "user"}:
            name = current.parent.name
        rule = cls.known_rule_for_name(name)
        return str((rule or {}).get("name") or name)

    @classmethod
    def _is_blocked_folder(cls, name: str) -> bool:
        low = str(name or "").strip().lower()
        return normalize_name(low) in {normalize_name(item) for item in cls.NON_GAME_FOLDER_NAMES}

    @classmethod
    def _has_save_like_content(cls, path: str) -> bool:
        if not os.path.isdir(path):
            return False
        save_words = ("save", "saves", "savegame", "savegames", "savedata", "profile", "player", "slot")
        save_exts = (".sav", ".save", ".dat", ".ini", ".cfg", ".json", ".profile", ".slot")
        try:
            checked = 0
            root_depth = len(Path(path).parts)
            for current, dirnames, filenames in os.walk(path):
                checked += 1
                if checked > 30:
                    return True
                depth = len(Path(current).parts) - root_depth
                if depth > 1:
                    dirnames[:] = []
                    continue
                if any(any(word in normalize_name(dirname) for word in save_words) for dirname in dirnames):
                    return True
                for file_name in filenames[:30]:
                    lowered = file_name.lower()
                    stem = normalize_name(Path(file_name).stem)
                    if lowered.endswith(save_exts) or any(word in stem for word in save_words):
                        return True
        except Exception:
            return False
        return False

    @classmethod
    def _resolve_library_game(
        cls,
        name: str,
        steam_api=None,
        known: bool = False,
        allow_safe_local: bool = False,
        allow_steam_lookup: bool = False,
    ) -> dict[str, Any] | None:
        if not name or cls._is_blocked_folder(name):
            return None
        rule = cls.known_rule_for_name(name)

        # Unknown AppData/LocalLow folders are not enough to create Library
        # cards. For curated known rules, always allow. For Saved Games,
        # Documents, and LocalLow folders, allow_safe_local permits a local-only card.
        # Skip very short names (< 4 chars) to avoid matching "cfg", "bin", etc.
        if not rule and not allow_safe_local and not allow_steam_lookup:
            return None
        if not rule and len(normalize_name(name)) < 4:
            return None

        canonical = str((rule or {}).get("name") or name).strip()
        appid = str((rule or {}).get("appid") or "").strip()

        resolved = None
        if steam_api is not None:
            try:
                if appid.isdigit():
                    resolved = steam_api.get_app_details(appid, timeout=2) or steam_api.seed_cache_entry(appid, canonical)
                elif allow_steam_lookup:
                    resolved = steam_api.resolve_candidate_name(canonical)
                    if resolved:
                        resolved_name = str(resolved.get("name") or "")
                        resolved_norm = normalize_name(resolved_name)
                        canonical_norm = normalize_name(canonical)
                        # Only accept exact normalized match.
                        if not resolved_norm or resolved_norm != canonical_norm:
                            resolved = None
            except Exception:
                resolved = None

        if resolved:
            return dict(resolved)

        if not rule and not allow_safe_local:
            return None

        header = ""
        if appid.isdigit() and steam_api is not None:
            try:
                header = steam_api.header_image_for_appid(appid)
            except Exception:
                header = ""
        return {
            "appid": appid if appid.isdigit() else f"local-save:{normalize_name(canonical)}",
            "name": canonical,
            "developers": [],
            "publishers": [],
            "header_image": header or placeholder_header_image(canonical, "Save/config folder"),
            "short_description": "Save/config folder found locally.",
            "local_only": not appid.isdigit(),
        }

    @classmethod
    def discover_save_library_entries(cls, steam_api=None) -> dict[str, dict[str, Any]]:
        """Discover save-only games for Library without listing normal apps.

        A candidate is added only if it is a curated known rule. This avoids
        turning AppData programs, Discord mods, and utility folders into game
        cards. Focused Home search handles Saved Games/Documents separately.
        """
        found: dict[str, dict[str, Any]] = {}
        seen_paths: set[str] = set()
        checked = 0
        max_candidates = 450

        for pattern, kind in cls._candidate_scan_patterns():
            try:
                matches = glob.glob(cls.expand_vars(pattern))
            except Exception:
                matches = []
            for match in matches:
                if checked >= max_candidates:
                    return found
                checked += 1
                if not os.path.isdir(match):
                    continue
                norm_path = os.path.normcase(os.path.normpath(match))
                if norm_path in seen_paths:
                    continue
                seen_paths.add(norm_path)

                pattern_rule = cls.known_rule_for_pattern(pattern) if kind == "known" else None
                if pattern_rule:
                    candidate_name = str(pattern_rule.get("name") or cls._name_from_candidate_path(match))
                else:
                    candidate_name = cls._name_from_candidate_path(match)
                known = kind == "known" or cls.known_rule_for_name(candidate_name) is not None
                if cls._is_blocked_folder(candidate_name):
                    continue
                if not known and len(normalize_name(candidate_name)) < 4:
                    continue
                rule = cls.known_rule_for_name(candidate_name)
                if rule and rule.get("patterns_only") and kind != "known":
                    continue

                # Skip publisher folders in LocalLow (one subfolder = likely publisher).
                # Let {LOCALLOW}\*\* catch the actual game inside.
                if kind == "locallow" and not known and os.path.isdir(match):
                    try:
                        children = [d for d in os.listdir(match) if os.path.isdir(os.path.join(match, d))]
                        if len(children) == 1:
                            child_norm = normalize_name(children[0])
                            if child_norm not in {"saves", "savegames", "savedata", "config", "data", "profiles", "logs", "cache"}:
                                continue
                    except Exception:
                        pass

                # Skip publisher folders (one non-generic subfolder = likely publisher).
                # Let nested patterns catch the actual game inside.
                if kind in {"locallow", "top_appdata"} and not known and os.path.isdir(match):
                    try:
                        children = [d for d in os.listdir(match) if os.path.isdir(os.path.join(match, d))]
                        if len(children) == 1:
                            child_norm = normalize_name(children[0])
                            if child_norm not in {"saves", "savegames", "savedata", "config", "data",
                                                  "profiles", "logs", "cache", "bin", "output"}:
                                continue
                    except Exception:
                        pass

                # For broad patterns, trust the name validation above.
                # For narrow patterns (top_appdata, godot, unreal), require save content.
                # LocalLow nested (publisher→game) allows local-only entries.
                trusted = kind in {"locallow_nested", "documents", "savedgames"}
                if not known and not trusted and not cls._has_save_like_content(match):
                    continue

                game = cls._resolve_library_game(
                    candidate_name,
                    steam_api=steam_api,
                    known=known,
                    allow_safe_local=known or kind in {"locallow_nested", "documents", "savedgames"},
                    allow_steam_lookup=False,
                )
                if not game:
                    continue

                appid = str(game.get("appid") or f"local-save:{normalize_name(game.get('name', candidate_name))}")
                if rule and rule.get("save_and_config"):
                    category = "Save & Config Files"
                    description = "Save and config folder"
                else:
                    match_norm = normalize_name(str(match))
                    category = "Config Files" if "config" in match_norm else "Save Files"
                    description = "Detected config folder" if category == "Config Files" else "Detected save folder"
                entry = cls._path_entry(match, category, description, "Save scan")
                if not entry:
                    continue

                bucket = found.setdefault(appid, {
                    **game,
                    "appid": appid,
                    "sources": [],
                    "paths": [],
                    "local_only": game.get("local_only", not appid.isdigit()),
                })
                if not any(os.path.normcase(os.path.normpath(item["path"])) == norm_path for item in bucket["paths"]):
                    bucket["paths"].append(entry)
        return found

    @classmethod
    def find_local_game_by_save_name(cls, query: str, steam_api=None) -> dict[str, Any] | None:
        query = (query or "").strip()
        if not query:
            return None
        rule = cls.known_rule_for_name(query)

        # If the query is one of a known game's aliases, search with the full
        # curated rule instead of a guessed local-only name. This catches cases
        # where the save folder name is unrelated to the public title, e.g.
        # LEGO Batman's config folder using "Dinner".
        if rule:
            canonical = str(rule.get("name") or query).strip()
            appid = str(rule.get("appid") or "").strip()
            game = cls._resolve_library_game(canonical, steam_api=steam_api, known=True, allow_safe_local=True) or {
                "appid": appid,
                "name": canonical,
                "developers": [],
                "publishers": [],
                "header_image": placeholder_header_image(canonical, "Local save search"),
                "short_description": "Local save/config search result.",
            }
        else:
            canonical = query
            game = {
                "appid": "",
                "name": canonical,
                "developers": [],
                "publishers": [],
                "header_image": placeholder_header_image(canonical, "Local save search"),
                "short_description": "Local save/config search result.",
            }

        paths = cls.find_save_paths(game, include_online=False)
        if not paths:
            return None
        return {**game, "paths": paths}
