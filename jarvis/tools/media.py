"""Son et lecture multimédia (Spotify, YouTube, lecteurs...)."""
import platform

from . import tool

IS_WINDOWS = platform.system() == "Windows"


def _volume_endpoint():
    from ctypes import POINTER, cast

    from comtypes import CLSCTX_ALL
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume

    dev = AudioUtilities.GetSpeakers()
    iface = dev.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
    return cast(iface, POINTER(IAudioEndpointVolume))


@tool(
    "Règle le volume général du PC (0 à 100), ou coupe/rétablit le son.",
    {"niveau": {"type": "integer", "description": "0-100"}, "muet": {"type": "boolean"}},
    required=[],
)
def volume(niveau=None, muet=None):
    if IS_WINDOWS:
        ep = _volume_endpoint()
        if muet is not None:
            ep.SetMute(1 if muet else 0, None)
        if niveau is not None:
            ep.SetMasterVolumeLevelScalar(max(0, min(100, niveau)) / 100, None)
        return f"Volume à {round(ep.GetMasterVolumeLevelScalar() * 100)}%{' (muet)' if ep.GetMute() else ''}."
    import pyautogui

    if muet is not None:
        pyautogui.press("volumemute")
    return "Réglage exact du volume disponible seulement sous Windows."


@tool(
    "Contrôle la lecture multimédia en cours (Spotify, YouTube, VLC...) via les touches média.",
    {"action": {"type": "string", "enum": ["lecture_pause", "suivant", "precedent", "stop"]}},
)
def controle_media(action):
    import pyautogui

    keys = {"lecture_pause": "playpause", "suivant": "nexttrack", "precedent": "prevtrack", "stop": "stop"}
    pyautogui.press(keys[action])
    return f"Média : {action}."


@tool(
    "Lance de la musique : ouvre Spotify sur une recherche (artiste, titre, playlist, ambiance).",
    {"recherche": {"type": "string"}},
)
def jouer_musique(recherche):
    import urllib.parse
    import webbrowser

    webbrowser.open(f"spotify:search:{urllib.parse.quote(recherche)}")
    return (
        f"Spotify ouvert sur la recherche '{recherche}'. Pour lancer le premier résultat, "
        "regarde l'écran et clique dessus si besoin."
    )
