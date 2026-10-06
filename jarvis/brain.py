"""Le cerveau : Claude, avec ses outils, en streaming phrase par phrase pour répondre vite à voix haute."""
import datetime as dt
import json
import platform
import re

import anthropic

from . import config, tools
from .tools import memory

SYSTEM = """Tu es {name}, l'assistant personnel vocal de {user}, inspiré du J.A.R.V.I.S. d'Iron Man : \
efficace, loyal, avec une pointe d'humour pince-sans-rire. Tu vis sur son ordinateur ({os}) et tu peux tout y faire \
grâce à tes outils : ouvrir et piloter des applications (sur l'écran de son choix), voir l'écran, cliquer, taper, \
gérer les fichiers, lancer des jeux, enregistrer avec OBS, monter des vidéos avec FFmpeg, régler le son, chercher \
sur le web, programmer des rappels, et même créer de nouveaux outils pour toi-même quand il t'en manque un.

Règles :
- Tu parles à voix haute : réponses COURTES (une à trois phrases), naturelles, sans markdown, sans listes, \
sans emoji, sans URL lue à voix haute. Les nombres et unités s'écrivent comme on les dit.
- Agis plutôt que d'expliquer : si une demande se fait avec tes outils, fais-la directement, enchaîne plusieurs \
outils si nécessaire, puis confirme brièvement ce qui a été fait.
- Avant de cliquer quelque part, regarde l'écran. Après une action importante à l'écran, vérifie le résultat.
- Si rien ne convient, utilise executer_commande (PowerShell) ; si la demande reviendra souvent, crée un outil \
avec creer_outil.
- Si une demande est ambiguë, pose UNE question courte.
- La transcription vocale peut contenir des erreurs : devine l'intention la plus probable.
- Retiens ce qui est utile pour plus tard avec memoriser.

Ce que tu sais de {user} (mémoire) :
{memory}

Date et heure : {now}."""

JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre", "novembre", "décembre"]


def _now_fr():
    n = dt.datetime.now()
    return f"{JOURS[n.weekday()]} {n.day} {MOIS[n.month - 1]} {n.year}, {n:%H:%M}"


def system_prompt():
    return SYSTEM.format(
        name=config.NAME,
        user=config.USER_NAME,
        os=platform.platform(),
        memory=memory.as_prompt(),
        now=_now_fr(),
    )


MAX_TURNS = 40  # messages gardés en contexte


class Brain:
    def __init__(self):
        if not config.ANTHROPIC_API_KEY:
            raise RuntimeError("Clé API Claude manquante : renseigne-la dans les Réglages (ou ANTHROPIC_API_KEY dans .env).")
        self._client = None
        self._key = None
        self.history: list = []

    @property
    def client(self):
        # Recréé si la clé a changé depuis la fenêtre Réglages.
        if self._client is None or self._key != config.ANTHROPIC_API_KEY:
            self._key = config.ANTHROPIC_API_KEY
            self._client = anthropic.Anthropic(api_key=self._key)
        return self._client

    @client.setter
    def client(self, value):
        self._client, self._key = value, config.ANTHROPIC_API_KEY

    def _system(self):
        return system_prompt()

    def _trim(self):
        # Les captures d'écran anciennes coûtent cher : on les remplace par une mention.
        for msg in self.history[:-2]:
            if msg["role"] == "user" and isinstance(msg["content"], list):
                for block in msg["content"]:
                    if block.get("type") == "tool_result" and isinstance(block.get("content"), list):
                        block["content"] = [
                            c if c.get("type") != "image" else {"type": "text", "text": "[capture d'écran]"}
                            for c in block["content"]
                        ]
        if len(self.history) > MAX_TURNS:
            cut = len(self.history) - MAX_TURNS
            # Recommencer sur un message utilisateur « texte » pour ne pas couper une paire outil/résultat.
            while cut < len(self.history) and not (
                self.history[cut]["role"] == "user" and isinstance(self.history[cut]["content"], str)
            ):
                cut += 1
            self.history = self.history[cut:]

    def ask(self, text, on_sentence, confirm, on_tool=None):
        """Envoie `text` à Claude, exécute les outils demandés et lit la réponse phrase par phrase."""
        self.history.append({"role": "user", "content": text})
        self._trim()
        for _ in range(25):  # nombre max d'allers-retours d'outils par demande
            msg = self._stream(on_sentence)
            self.history.append({"role": "assistant", "content": [b.model_dump(exclude_none=True) for b in msg.content]})
            calls = [b for b in msg.content if b.type == "tool_use"]
            if msg.stop_reason != "tool_use" or not calls:
                return
            results = []
            for call in calls:
                if on_tool:
                    on_tool(call.name, call.input)
                print(f"   🔧 {call.name} {json.dumps(call.input, ensure_ascii=False)[:200]}")
                out = tools.run(call.name, call.input, confirm)
                content = out if isinstance(out, list) else str(out)[:20000]
                results.append({"type": "tool_result", "tool_use_id": call.id, "content": content})
            self.history.append({"role": "user", "content": results})
        on_sentence("J'ai enchaîné beaucoup d'actions, je m'arrête là pour l'instant.")

    def _stream(self, on_sentence):
        buf = ""
        with self.client.messages.stream(
            model=config.MODEL,
            max_tokens=2048,
            system=[{"type": "text", "text": self._system()}],
            tools=tools.schemas(),
            messages=self.history,
        ) as stream:
            for event in stream:
                if event.type == "text":
                    buf += event.text
                    # Dès qu'une phrase est complète, on la prononce sans attendre la suite.
                    parts = re.split(r"(?<=[.!?…])\s+", buf)
                    for sentence in parts[:-1]:
                        on_sentence(sentence)
                    buf = parts[-1]
            if buf.strip():
                on_sentence(buf)
            return stream.get_final_message()

    def reset(self):
        self.history = []
