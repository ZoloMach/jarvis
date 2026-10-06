"""Jeux : lister et lancer les jeux Steam, mode jeu."""
import os
import platform
import re
import webbrowser
from pathlib import Path

from . import tool


def _steam_root():
    if platform.system() == "Windows":
        try:
            import winreg

            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as k:
                return Path(winreg.QueryValueEx(k, "SteamPath")[0])
        except OSError:
            return Path(r"C:\Program Files (x86)\Steam")
    if platform.system() == "Darwin":
        return Path.home() / "Library/Application Support/Steam"
    return Path.home() / ".steam/steam"


def _steam_games():
    root = _steam_root()
    libs = {root / "steamapps"}
    vdf = root / "steamapps" / "libraryfolders.vdf"
    if vdf.exists():
        for path in re.findall(r'"path"\s+"([^"]+)"', vdf.read_text(encoding="utf-8", errors="ignore")):
            libs.add(Path(path.replace("\\\\", "\\")) / "steamapps")
    games = {}
    for lib in libs:
        for mf in lib.glob("appmanifest_*.acf"):
            txt = mf.read_text(encoding="utf-8", errors="ignore")
            appid = re.search(r'"appid"\s+"(\d+)"', txt)
            name = re.search(r'"name"\s+"([^"]+)"', txt)
            if appid and name and "Steamworks" not in name.group(1) and "Redistributable" not in name.group(1):
                games[name.group(1)] = appid.group(1)
    return games


@tool("Liste les jeux Steam installés.")
def lister_jeux():
    games = _steam_games()
    return ", ".join(sorted(games)) if games else "Aucun jeu Steam trouvé (Steam est-il installé ?)."


@tool(
    "Lance un jeu Steam installé par son nom (correspondance approximative acceptée).",
    {"nom": {"type": "string"}},
)
def lancer_jeu(nom):
    import difflib

    games = _steam_games()
    if not games:
        return "Aucun jeu Steam trouvé."
    lower = {g.lower(): g for g in games}
    match = next((lower[k] for k in lower if nom.lower() in k), None)
    if not match:
        close = difflib.get_close_matches(nom.lower(), lower.keys(), n=1, cutoff=0.4)
        match = lower[close[0]] if close else None
    if not match:
        return f"Je ne trouve pas '{nom}'. Jeux installés : {', '.join(sorted(games))}"
    webbrowser.open(f"steam://rungameid/{games[match]}")
    return f"Lancement de {match}."


@tool(
    "Active le mode jeu : ferme les applis gourmandes listées et ouvre Discord. "
    "Personnalisable dans la variable JARVIS_GAME_MODE_CLOSE du .env.",
)
def mode_jeu():
    import psutil

    to_close = [n.strip().lower() for n in os.getenv("JARVIS_GAME_MODE_CLOSE", "").split(",") if n.strip()]
    closed = []
    for p in psutil.process_iter(["name"]):
        if (p.info["name"] or "").lower() in to_close:
            p.terminate()
            closed.append(p.info["name"])
    webbrowser.open("discord://")
    return f"Mode jeu activé. Fermé : {', '.join(closed) or 'rien'}. Discord ouvert."
