"""Pilotage du système : applications, web, clavier, souris, écran, commandes."""
import base64
import io
import os
import platform
import shutil
import subprocess
import time
import urllib.parse
import webbrowser

from .. import config
from . import tool

IS_WINDOWS = platform.system() == "Windows"
IS_MAC = platform.system() == "Darwin"


def _pyautogui():
    import pyautogui

    pyautogui.FAILSAFE = True  # coin haut-gauche de l'écran = arrêt d'urgence
    return pyautogui


@tool(
    "Donne la date, l'heure et des infos système (OS, batterie, CPU, mémoire).",
)
def infos_systeme():
    import psutil

    from ..brain import _now_fr

    now = _now_fr()
    bat = psutil.sensors_battery()
    bat_txt = f"{bat.percent:.0f}% {'sur secteur' if bat.power_plugged else 'sur batterie'}" if bat else "pas de batterie"
    mem = psutil.virtual_memory()
    return (
        f"Date : {now}. OS : {platform.platform()}. CPU : {psutil.cpu_percent(interval=0.5)}%. "
        f"Mémoire : {mem.percent}% utilisée. Batterie : {bat_txt}."
    )


ECRAN_PARAM = {
    "type": "string",
    "description": "Écran où afficher la fenêtre, si l'utilisateur en précise un : 'haut', 'bas', 'gauche', "
    "'droite', 'principal', 'grand', 'autre' ou son numéro (voir lister_ecrans)",
}


@tool(
    "Ouvre une application installée par son nom (ex : 'chrome', 'spotify', 'discord', 'obs', 'premiere', 'davinci resolve', 'steam', 'bloc-notes'). "
    "Sous Windows, passe par le menu Démarrer si le nom exact n'est pas connu. Peut l'afficher sur un écran précis.",
    {"nom": {"type": "string", "description": "Nom de l'application"}, "ecran": ECRAN_PARAM},
    required=["nom"],
)
def ouvrir_application(nom, ecran=None):
    if ecran and IS_WINDOWS:
        before = {w._hWnd for w in _windows()}
        message = ouvrir_application(nom)
        return f"{message} {_place_new_window(nom, before, ecran)}"
    exe = shutil.which(nom)
    if exe:
        subprocess.Popen([exe])
        return f"{nom} lancé."
    if IS_WINDOWS:
        aliases = {"bloc-notes": "notepad", "calculatrice": "calc", "explorateur": "explorer", "paint": "mspaint"}
        if nom.lower() in aliases:
            subprocess.Popen(aliases[nom.lower()])
            return f"{nom} lancé."
        # Recherche dans le menu Démarrer : touche Windows, on tape le nom, Entrée.
        pg = _pyautogui()
        pg.press("win")
        time.sleep(0.6)
        pg.write(nom, interval=0.03)
        time.sleep(0.9)
        pg.press("enter")
        return f"J'ai lancé '{nom}' via le menu Démarrer."
    if IS_MAC:
        subprocess.Popen(["open", "-a", nom])
        return f"{nom} lancé."
    subprocess.Popen([nom])
    return f"{nom} lancé."


@tool(
    "Ouvre une URL ou un fichier/dossier avec le programme par défaut, éventuellement sur un écran précis.",
    {"cible": {"type": "string", "description": "URL, chemin de fichier ou de dossier"}, "ecran": ECRAN_PARAM},
    required=["cible"],
)
def ouvrir(cible, ecran=None):
    if ecran and IS_WINDOWS:
        before = {w._hWnd for w in _windows()}
        message = ouvrir(cible)
        hint = os.path.splitext(os.path.basename(cible.rstrip("/\\")))[0] if "://" not in cible else ""
        return f"{message} {_place_new_window(hint, before, ecran)}"
    if cible.startswith(("http://", "https://", "steam://", "mailto:")):
        webbrowser.open(cible)
    elif IS_WINDOWS:
        os.startfile(os.path.expanduser(cible))  # noqa: S606
    else:
        subprocess.Popen(["open" if IS_MAC else "xdg-open", os.path.expanduser(cible)])
    return f"Ouvert : {cible}"


@tool(
    "Lance une recherche dans le navigateur (Google, YouTube...).",
    {
        "requete": {"type": "string"},
        "site": {"type": "string", "enum": ["google", "youtube", "maps", "wikipedia"], "description": "Par défaut google"},
    },
)
def rechercher_web(requete, site="google"):
    q = urllib.parse.quote_plus(requete)
    urls = {
        "google": f"https://www.google.com/search?q={q}",
        "youtube": f"https://www.youtube.com/results?search_query={q}",
        "maps": f"https://www.google.com/maps/search/{q}",
        "wikipedia": f"https://fr.wikipedia.org/w/index.php?search={q}",
    }
    webbrowser.open(urls[site])
    return f"Recherche '{requete}' ouverte sur {site}."


@tool(
    "Récupère le texte d'une page web pour pouvoir la lire ou la résumer.",
    {"url": {"type": "string"}},
)
def lire_page_web(url):
    import requests
    from bs4 import BeautifulSoup

    html = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"}).text
    soup = BeautifulSoup(html, "html.parser")
    for s in soup(["script", "style", "nav", "footer"]):
        s.decompose()
    text = " ".join(soup.get_text(" ").split())
    return text[:12000]


@tool(
    "Prend une capture d'écran et te la montre, pour voir ce que l'utilisateur a à l'écran "
    "(utile avant de cliquer, pour lire un message d'erreur, aider dans un jeu, etc.).",
)
def regarder_ecran():
    pg = _pyautogui()
    img = pg.screenshot()
    w, h = img.size
    img.thumbnail((1568, 1568))
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="JPEG", quality=80)
    data = base64.standard_b64encode(buf.getvalue()).decode()
    sx, sy = w / img.size[0], h / img.size[1]
    return [
        {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": data}},
        {
            "type": "text",
            "text": f"Écran réel {w}x{h}. Image réduite à {img.size[0]}x{img.size[1]} : "
            f"pour cliquer, multiplie x par {sx:.3f} et y par {sy:.3f}.",
        },
    ]


@tool(
    "Clique à une position de l'écran (coordonnées réelles en pixels).",
    {
        "x": {"type": "integer"},
        "y": {"type": "integer"},
        "bouton": {"type": "string", "enum": ["left", "right", "middle"]},
        "double": {"type": "boolean"},
    },
)
def cliquer(x, y, bouton="left", double=False):
    pg = _pyautogui()
    pg.click(x, y, clicks=2 if double else 1, button=bouton)
    return f"Clic {bouton} en ({x}, {y})."


@tool(
    "Tape du texte au clavier dans la fenêtre active.",
    {"texte": {"type": "string"}},
)
def taper_texte(texte):
    # pyautogui.write ne gère pas les accents : on passe par le presse-papiers.
    import pyperclip

    pg = _pyautogui()
    old = pyperclip.paste()
    pyperclip.copy(texte)
    pg.hotkey("command" if IS_MAC else "ctrl", "v")
    time.sleep(0.2)
    pyperclip.copy(old)
    return "Texte tapé."


@tool(
    "Appuie sur une touche ou un raccourci clavier. Exemples : ['ctrl','s'], ['alt','tab'], ['f11'], ['win','d'].",
    {"touches": {"type": "array", "items": {"type": "string"}}},
)
def raccourci_clavier(touches):
    _pyautogui().hotkey(*touches)
    return f"Raccourci {'+'.join(touches)} envoyé."


@tool(
    "Fait défiler la fenêtre active (positif = haut, négatif = bas).",
    {"quantite": {"type": "integer"}},
)
def defiler(quantite):
    _pyautogui().scroll(quantite * 100)
    return "Défilement effectué."


@tool("Lit le contenu du presse-papiers.")
def lire_presse_papiers():
    import pyperclip

    return pyperclip.paste()[:8000] or "(presse-papiers vide)"


@tool("Copie du texte dans le presse-papiers.", {"texte": {"type": "string"}})
def copier_presse_papiers(texte):
    import pyperclip

    pyperclip.copy(texte)
    return "Copié."


@tool("Liste les fenêtres ouvertes (titres).")
def lister_fenetres():
    if not IS_WINDOWS:
        return "Disponible seulement sous Windows."
    import pygetwindow as gw

    titles = [t for t in gw.getAllTitles() if t.strip()]
    return "\n".join(titles[:60])


@tool(
    "Met au premier plan une fenêtre dont le titre contient le texte donné.",
    {"titre": {"type": "string"}},
)
def activer_fenetre(titre):
    import pygetwindow as gw

    wins = [w for w in gw.getAllWindows() if titre.lower() in w.title.lower()]
    if not wins:
        return f"Aucune fenêtre contenant '{titre}'."
    w = wins[0]
    if w.isMinimized:
        w.restore()
    w.activate()
    return f"Fenêtre '{w.title}' activée."


# --- Plusieurs écrans ---
def _monitors():
    """Écrans branchés, l'écran principal d'abord : position, taille, zone utile (sans la barre des tâches), nom."""
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32

    class MONITORINFOEXW(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT), ("rcWork", wintypes.RECT),
                    ("dwFlags", wintypes.DWORD), ("szDevice", wintypes.WCHAR * 32)]  # fmt: skip

    class DISPLAY_DEVICEW(ctypes.Structure):  # noqa: N801
        _fields_ = [("cb", wintypes.DWORD), ("DeviceName", wintypes.WCHAR * 32), ("DeviceString", wintypes.WCHAR * 128),
                    ("StateFlags", wintypes.DWORD), ("DeviceID", wintypes.WCHAR * 128),
                    ("DeviceKey", wintypes.WCHAR * 128)]  # fmt: skip

    found = []
    proc_type = ctypes.WINFUNCTYPE(ctypes.c_int, wintypes.HMONITOR, wintypes.HDC, ctypes.POINTER(wintypes.RECT),
                                   wintypes.LPARAM)  # fmt: skip

    def callback(hmon, hdc, rect, data):
        info = MONITORINFOEXW()
        info.cbSize = ctypes.sizeof(MONITORINFOEXW)
        user32.GetMonitorInfoW(wintypes.HMONITOR(hmon), ctypes.byref(info))
        device = DISPLAY_DEVICEW()
        device.cb = ctypes.sizeof(DISPLAY_DEVICEW)
        name = info.szDevice.replace("\\\\.\\", "")
        if user32.EnumDisplayDevicesW(info.szDevice, 0, ctypes.byref(device), 0) and device.DeviceString:
            name = device.DeviceString
        r, w = info.rcMonitor, info.rcWork
        found.append({"x": r.left, "y": r.top, "w": r.right - r.left, "h": r.bottom - r.top, "nom": name,
                      "zone": (w.left, w.top, w.right - w.left, w.bottom - w.top),
                      "principal": bool(info.dwFlags & 1)})  # fmt: skip
        return 1

    user32.EnumDisplayMonitors(None, None, proc_type(callback), 0)
    return _describe_monitors(found)


def _describe_monitors(monitors):
    """Classe les écrans (principal d'abord) et note où chacun se trouve par rapport au principal."""
    if not monitors:
        return []
    main = next((m for m in monitors if m["principal"]), monitors[0])
    others = sorted((m for m in monitors if m is not main), key=lambda m: (m["y"], m["x"]))
    mx, my = main["x"] + main["w"] / 2, main["y"] + main["h"] / 2
    main["position"] = "principal"
    for m in others:
        dx, dy = m["x"] + m["w"] / 2 - mx, m["y"] + m["h"] / 2 - my
        if abs(dy) > abs(dx):
            m["position"] = "en haut" if dy < 0 else "en bas"
        else:
            m["position"] = "à gauche" if dx < 0 else "à droite"
    return [main, *others]


def _pick_monitor(monitors, ecran):
    """Trouve l'écran désigné en langage courant : 'haut', 'principal', 'le grand', 'autre', '2', un nom..."""
    e = str(ecran or "").lower().strip()
    if not monitors or not e:
        return None
    digits = "".join(c for c in e if c.isdigit())
    if digits and 1 <= int(digits) <= len(monitors):
        return monitors[int(digits) - 1]
    for word, position in (("haut", "en haut"), ("dessus", "en haut"), ("bas", "en bas"), ("dessous", "en bas"),
                           ("gauche", "à gauche"), ("droit", "à droite")):  # fmt: skip
        if word in e:
            return next((m for m in monitors if m["position"] == position), None)
    if any(k in e for k in ("principal", "premier")):
        return monitors[0]
    if "grand" in e:
        return max(monitors, key=lambda m: m["w"] * m["h"])
    if "petit" in e:
        return min(monitors, key=lambda m: m["w"] * m["h"])
    named = [m for m in monitors if m["nom"].lower() in e or e in m["nom"].lower()]
    if named:  # « G241 » doit désigner le G241 et pas le G2412F : le nom le plus proche gagne
        return min(named, key=lambda m: abs(len(m["nom"]) - len(e)))
    if any(k in e for k in ("autre", "second", "deux", "secondaire")) and len(monitors) > 1:
        return monitors[1]
    return None


def _windows():
    import pygetwindow as gw

    return [w for w in gw.getAllWindows() if w.title.strip() and w.visible]


def _place(win, monitor, maximize=True):
    x, y, w, h = monitor["zone"]
    if win.isMinimized or win.isMaximized:
        win.restore()
        time.sleep(0.2)
    win.resizeTo(min(max(win.width, 500), w - 60), min(max(win.height, 400), h - 60))
    win.moveTo(x + (w - win.width) // 2, y + (h - win.height) // 2)
    if maximize:
        win.maximize()
    try:
        win.activate()
    except Exception:  # noqa: BLE001 - pygetwindow signale parfois une « erreur » alors que tout a marché
        pass


def _place_new_window(hint, before, ecran, timeout=12):
    """Attend la fenêtre qui vient de s'ouvrir (ou celle qui porte ce nom) et la met sur l'écran demandé."""
    monitor = _pick_monitor(_monitors(), ecran)
    if not monitor:
        return f"Je n'ai pas trouvé l'écran « {ecran} »."
    import pygetwindow as gw

    hint, start = (hint or "").lower(), time.time()
    while time.time() - start < timeout:
        elapsed, wins = time.time() - start, _windows()
        new = [w for w in wins if w._hWnd not in before]
        candidates = [w for w in new if hint and hint in w.title.lower()]
        if not candidates and elapsed > 3:  # application déjà ouverte : sa fenêtre existante, sinon toute nouvelle
            candidates = [w for w in wins if hint and hint in w.title.lower()] or new
        if not candidates and elapsed > 5:  # une page ouverte dans un onglet : la fenêtre passée au premier plan
            active = gw.getActiveWindow()
            if active and active.title.strip() and active.title != config.NAME.upper():
                candidates = [active]
        if candidates:
            _place(candidates[0], monitor)
            return f"Fenêtre « {candidates[0].title} » placée sur l'écran {monitor['position']}."
        time.sleep(0.4)
    return "La fenêtre est ouverte mais je ne l'ai pas trouvée pour la déplacer."


@tool("Liste les écrans branchés (numéro, position par rapport à l'écran principal, taille, nom).")
def lister_ecrans():
    if not IS_WINDOWS:
        return "Disponible seulement sous Windows."
    return "\n".join(f"Écran {i} : {m['position']}, {m['w']}x{m['h']}, {m['nom']}" for i, m in enumerate(_monitors(), 1))


@tool(
    "Déplace une fenêtre ouverte (dont le titre contient le texte donné) sur un autre écran, en plein écran par défaut.",
    {
        "titre": {"type": "string", "description": "Texte contenu dans le titre de la fenêtre (ex : 'Discord', 'Chrome')"},
        "ecran": ECRAN_PARAM,
        "plein_ecran": {"type": "boolean", "description": "Agrandir la fenêtre sur cet écran (défaut : oui)"},
    },
    required=["titre", "ecran"],
)
def placer_fenetre(titre, ecran, plein_ecran=True):
    if not IS_WINDOWS:
        return "Disponible seulement sous Windows."
    monitor = _pick_monitor(_monitors(), ecran)
    if not monitor:
        return f"Je n'ai pas trouvé l'écran « {ecran} ». Écrans disponibles :\n{lister_ecrans()}"
    wins = [w for w in _windows() if titre.lower() in w.title.lower()]
    if not wins:
        return f"Aucune fenêtre contenant '{titre}'."
    _place(wins[0], monitor, plein_ecran)
    return f"Fenêtre « {wins[0].title} » placée sur l'écran {monitor['position']}."


@tool(
    "Ferme un programme par son nom de processus (ex : 'chrome.exe', 'Discord.exe').",
    {"processus": {"type": "string"}},
    sensitive=True,
    label="fermer un programme",
)
def fermer_programme(processus):
    import psutil

    n = 0
    for p in psutil.process_iter(["name"]):
        if (p.info["name"] or "").lower() == processus.lower():
            p.terminate()
            n += 1
    return f"{n} processus fermé(s)." if n else f"Aucun processus '{processus}'."


@tool(
    "Exécute une commande shell (PowerShell sous Windows, bash ailleurs) et renvoie la sortie. "
    "Permet de faire presque tout ce qui n'a pas d'outil dédié.",
    {"commande": {"type": "string"}, "timeout": {"type": "integer", "description": "Secondes, défaut 60"}},
    sensitive=True,
    label="lancer une commande sur ton PC",
)
def executer_commande(commande, timeout=60):
    cmd = ["powershell", "-NoProfile", "-Command", commande] if IS_WINDOWS else ["bash", "-lc", commande]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, encoding="utf-8", errors="replace")
    out = (r.stdout + ("\n" + r.stderr if r.stderr else "")).strip()
    return f"Code {r.returncode}\n{out[-6000:]}"


@tool(
    "Verrouille la session, met en veille, redémarre ou éteint l'ordinateur.",
    {"action": {"type": "string", "enum": ["verrouiller", "veille", "redemarrer", "eteindre"]}},
    sensitive=True,
    label="changer l'alimentation du PC",
)
def alimentation(action):
    if not IS_WINDOWS:
        return "Implémenté seulement pour Windows."
    cmds = {
        "verrouiller": "rundll32.exe user32.dll,LockWorkStation",
        "veille": "rundll32.exe powrprof.dll,SetSuspendState 0,1,0",
        "redemarrer": "shutdown /r /t 5",
        "eteindre": "shutdown /s /t 5",
    }
    subprocess.Popen(cmds[action], shell=True)  # noqa: S602
    return f"Action '{action}' lancée."
