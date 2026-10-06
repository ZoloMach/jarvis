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


@tool(
    "Ouvre une application installée par son nom (ex : 'chrome', 'spotify', 'discord', 'obs', 'premiere', 'davinci resolve', 'steam', 'bloc-notes'). "
    "Sous Windows, passe par le menu Démarrer si le nom exact n'est pas connu.",
    {"nom": {"type": "string", "description": "Nom de l'application"}},
)
def ouvrir_application(nom):
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
    "Ouvre une URL ou un fichier/dossier avec le programme par défaut.",
    {"cible": {"type": "string", "description": "URL, chemin de fichier ou de dossier"}},
)
def ouvrir(cible):
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
