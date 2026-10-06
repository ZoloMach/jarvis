"""Fichiers et dossiers."""
import os
import shutil
from pathlib import Path

from . import tool


def _p(path):
    return Path(os.path.expandvars(os.path.expanduser(path)))


@tool(
    "Liste le contenu d'un dossier. Raccourcis : '~' (dossier perso), '~/Desktop', '~/Documents', '~/Videos', '~/Downloads'.",
    {"dossier": {"type": "string"}},
)
def lister_dossier(dossier="~"):
    p = _p(dossier)
    items = sorted(p.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True)[:80]
    return "\n".join(f"{'[D]' if i.is_dir() else '   '} {i.name}" for i in items) or "(vide)"


@tool(
    "Cherche des fichiers par motif (ex : '*.mp4') dans un dossier et ses sous-dossiers.",
    {"dossier": {"type": "string"}, "motif": {"type": "string"}},
)
def chercher_fichiers(dossier, motif):
    res = []
    for f in _p(dossier).rglob(motif):
        res.append(str(f))
        if len(res) >= 50:
            break
    return "\n".join(res) or "Aucun fichier trouvé."


@tool("Lit un fichier texte.", {"chemin": {"type": "string"}})
def lire_fichier(chemin):
    return _p(chemin).read_text(encoding="utf-8", errors="replace")[:15000]


@tool(
    "Écrit (ou ajoute à) un fichier texte. Crée les dossiers manquants.",
    {"chemin": {"type": "string"}, "contenu": {"type": "string"}, "ajouter": {"type": "boolean"}},
    sensitive=True,
    label="écrire dans un fichier",
)
def ecrire_fichier(chemin, contenu, ajouter=False):
    p = _p(chemin)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a" if ajouter else "w", encoding="utf-8") as f:
        f.write(contenu)
    return f"Écrit dans {p}."


@tool(
    "Déplace ou renomme un fichier ou dossier.",
    {"source": {"type": "string"}, "destination": {"type": "string"}},
    sensitive=True,
    label="déplacer un fichier",
)
def deplacer(source, destination):
    shutil.move(_p(source), _p(destination))
    return "Déplacé."


@tool("Crée un dossier.", {"chemin": {"type": "string"}})
def creer_dossier(chemin):
    _p(chemin).mkdir(parents=True, exist_ok=True)
    return "Dossier créé."
