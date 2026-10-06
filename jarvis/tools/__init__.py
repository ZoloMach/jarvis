"""Registre des outils que Claude peut appeler.

Chaque outil est une fonction Python décorée par @tool. Le décorateur fabrique
le schéma JSON envoyé à Claude à partir de la description et des paramètres.
Pour ajouter une capacité, il suffit de déposer un fichier .py dans le dossier
plugins/ (Jarvis peut aussi en écrire lui-même avec l'outil creer_outil).
"""
import importlib
import importlib.util
import inspect
import sys
from dataclasses import dataclass
from typing import Callable

from .. import config


@dataclass
class Tool:
    name: str
    description: str
    params: dict
    required: list
    func: Callable
    sensitive: bool = False
    label: str = ""

    def schema(self):
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": {
                "type": "object",
                "properties": self.params,
                "required": self.required,
            },
        }


REGISTRY: dict[str, Tool] = {}


def tool(description, params=None, required=None, sensitive=False, label=None):
    """Déclare un outil.

    params: {"nom": {"type": "string", "description": "..."}}
    required: liste des paramètres obligatoires (par défaut : ceux sans valeur par défaut).
    sensitive: si True, Jarvis demande une confirmation vocale avant d'agir.
    label: courte description de l'action, lue à voix haute lors de la confirmation.
    """

    def deco(func):
        p = params or {}
        if required is None:
            sig = inspect.signature(func)
            req = [n for n, v in sig.parameters.items() if v.default is inspect.Parameter.empty and n in p]
        else:
            req = required
        lbl = label or func.__name__.replace("_", " ")
        REGISTRY[func.__name__] = Tool(func.__name__, description, p, req, func, sensitive, lbl)
        return func

    return deco


def schemas():
    return [t.schema() for t in REGISTRY.values()]


def run(name, args, confirm: Callable[[str, str], bool]):
    """Exécute un outil et renvoie son résultat (texte, ou liste de blocs pour une image)."""
    t = REGISTRY.get(name)
    if t is None:
        return f"Outil inconnu : {name}"
    if t.sensitive and not config.AUTO_CONFIRM:
        details = "\n".join(f"{k} : {str(v)[:300]}" for k, v in args.items())
        if not confirm(t.label, details):
            return "L'utilisateur a refusé cette action."
    try:
        result = t.func(**args)
        return result if result is not None else "OK"
    except Exception as e:  # noqa: BLE001 - on renvoie l'erreur à Claude pour qu'il s'adapte
        print(f"[outil {name}] {type(e).__name__}: {e}")
        return f"Erreur : {type(e).__name__}: {e}"


def load_all():
    """Charge les outils intégrés puis les plugins utilisateur."""
    for mod in ("system", "files", "media", "obs", "video", "games", "memory", "meta"):
        importlib.import_module(f"{__name__}.{mod}")
    load_plugins()


def load_plugins():
    loaded = []
    for path in sorted(config.PLUGINS_DIR.glob("*.py")):
        if path.name.startswith("_"):
            continue
        mod_name = f"jarvis_plugin_{path.stem}"
        try:
            spec = importlib.util.spec_from_file_location(mod_name, path)
            module = importlib.util.module_from_spec(spec)
            sys.modules[mod_name] = module
            spec.loader.exec_module(module)
            loaded.append(path.stem)
        except Exception as e:  # noqa: BLE001
            print(f"[plugins] Impossible de charger {path.name} : {e}")
    return loaded
