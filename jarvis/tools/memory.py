"""Mémoire à long terme : Jarvis retient ce que tu lui demandes de retenir, d'une session à l'autre."""
import datetime as dt
import json

from .. import config
from . import tool

FILE = config.DATA_DIR / "memoire.json"


def load():
    if FILE.exists():
        return json.loads(FILE.read_text(encoding="utf-8"))
    return []


def _save(items):
    FILE.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")


def as_prompt():
    items = load()
    if not items:
        return "(rien pour l'instant)"
    return "\n".join(f"- [{i['id']}] {i['texte']}" for i in items[-100:])


@tool(
    "Mémorise durablement une information (préférence, fait sur l'utilisateur, chemin utile, projet en cours...). "
    "Utilise-le dès que l'utilisateur dit 'retiens', ou quand tu apprends quelque chose d'utile pour plus tard.",
    {"texte": {"type": "string"}},
)
def memoriser(texte):
    items = load()
    new_id = max((i["id"] for i in items), default=0) + 1
    items.append({"id": new_id, "texte": texte, "date": dt.date.today().isoformat()})
    _save(items)
    return f"Mémorisé (n°{new_id})."


@tool("Oublie un souvenir par son numéro.", {"id": {"type": "integer"}})
def oublier(id):  # noqa: A002
    items = [i for i in load() if i["id"] != id]
    _save(items)
    return "Oublié."
