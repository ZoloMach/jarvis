"""Outils « méta » : minuteurs, rappels, et création de nouveaux outils par Jarvis lui-même."""
import ast
import re
import threading
import time

from .. import config
from . import REGISTRY, load_plugins, tool

# Fonction appelée pour parler spontanément (branchée par l'assistant au démarrage).
notify = print

_timers: dict[int, tuple[str, float, threading.Timer]] = {}
_next_id = 1


@tool(
    "Programme un minuteur ou un rappel vocal dans X minutes (ex : 'sortir les pâtes', 'pause dans 1 h').",
    {"minutes": {"type": "number"}, "message": {"type": "string"}},
)
def minuteur(minutes, message):
    global _next_id
    tid = _next_id
    _next_id += 1

    def fire():
        _timers.pop(tid, None)
        notify(f"Rappel : {message}")

    t = threading.Timer(minutes * 60, fire)
    t.daemon = True
    t.start()
    _timers[tid] = (message, time.time() + minutes * 60, t)
    return f"Minuteur n°{tid} réglé dans {minutes} min."


@tool("Liste ou annule les minuteurs en cours.", {"annuler_id": {"type": "integer"}}, required=[])
def minuteurs(annuler_id=None):
    if annuler_id is not None:
        item = _timers.pop(annuler_id, None)
        if item:
            item[2].cancel()
            return "Minuteur annulé."
        return "Minuteur introuvable."
    if not _timers:
        return "Aucun minuteur en cours."
    now = time.time()
    return "\n".join(f"n°{i} : {m} (dans {(end - now) / 60:.1f} min)" for i, (m, end, _) in _timers.items())


@tool("Liste toutes tes capacités (outils disponibles).")
def lister_outils():
    return "\n".join(f"- {t.name} : {t.description[:90]}" for t in REGISTRY.values())


@tool(
    "Crée un NOUVEL outil permanent pour toi-même, quand aucun outil existant ne permet de faire ce que l'utilisateur "
    "demande de façon répétée. Le code est un module Python qui importe `from jarvis.tools import tool` et déclare "
    "une ou plusieurs fonctions décorées, sur ce modèle :\n"
    "from jarvis.tools import tool\n\n"
    "@tool('Description claire.', {'param': {'type': 'string', 'description': '...'}})\n"
    "def mon_outil(param):\n    ...\n    return 'résultat en texte'\n\n"
    "Le fichier est enregistré dans plugins/ et chargé immédiatement. N'importe que des bibliothèques standard ou déjà "
    "installées.",
    {
        "nom_fichier": {"type": "string", "description": "Nom court en snake_case, sans .py"},
        "code": {"type": "string"},
    },
    sensitive=True,
    label="me créer un nouvel outil",
)
def creer_outil(nom_fichier, code):
    if not re.fullmatch(r"[a-z][a-z0-9_]{1,40}", nom_fichier):
        return "Nom de fichier invalide (snake_case, lettres minuscules)."
    try:
        ast.parse(code)
    except SyntaxError as e:
        return f"Erreur de syntaxe : {e}"
    path = config.PLUGINS_DIR / f"{nom_fichier}.py"
    before = set(REGISTRY)
    path.write_text(code, encoding="utf-8")
    load_plugins()
    added = sorted(set(REGISTRY) - before)
    return f"Plugin {path.name} enregistré. Nouveaux outils : {', '.join(added) or 'aucun (vérifie le décorateur)'}."
