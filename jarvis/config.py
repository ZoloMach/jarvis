"""Configuration de Jarvis, lue depuis le fichier .env à la racine du projet (modifiable depuis la fenêtre Réglages)."""
import os
from pathlib import Path

from dotenv import dotenv_values, set_key

ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = ROOT / ".env"
DATA_DIR = ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)
PLUGINS_DIR = ROOT / "plugins"
PLUGINS_DIR.mkdir(exist_ok=True)


def reload():
    """(Re)lit le .env et met à jour les variables du module."""
    values = dotenv_values(ENV_FILE) if ENV_FILE.exists() else {}
    for k, v in values.items():
        if v is not None:
            os.environ[k] = v

    def get(name, default=None):
        value = os.getenv(name)
        return value if value not in (None, "") else default

    g = globals()
    # Cerveau : "abonnement" (Claude Code, inclus dans Claude Pro/Max) ou "api" (clé API payée à l'usage).
    g["BRAIN"] = get("JARVIS_BRAIN", "abonnement")
    g["SETUP_DONE"] = get("JARVIS_SETUP_DONE", "0") == "1"
    g["ANTHROPIC_API_KEY"] = get("ANTHROPIC_API_KEY")
    g["MODEL"] = get("JARVIS_MODEL", "claude-sonnet-5-5")

    # Nom affiché et utilisé dans les phrases de l'assistant.
    g["NAME"] = get("JARVIS_NAME", "Jarvis")
    g["USER_NAME"] = get("JARVIS_USER_NAME", "Michel")

    # Écoute
    g["WAKEWORD_MODEL"] = get("JARVIS_WAKEWORD", "hey_jarvis")
    g["WAKEWORD_THRESHOLD"] = float(get("JARVIS_WAKEWORD_THRESHOLD", "0.5"))
    g["WHISPER_MODEL"] = get("JARVIS_WHISPER_MODEL", "small")
    g["WHISPER_DEVICE"] = get("JARVIS_WHISPER_DEVICE", "cpu")  # cpu, cuda ou auto
    g["LANGUAGE"] = get("JARVIS_LANGUAGE", "fr")
    # Secondes pendant lesquelles Jarvis continue d'écouter sans mot d'éveil après avoir répondu.
    g["FOLLOWUP_SECONDS"] = float(get("JARVIS_FOLLOWUP_SECONDS", "8"))

    # Voix
    g["TTS_VOICE"] = get("JARVIS_VOICE", "fr-FR-HenriNeural")
    g["TTS_RATE"] = get("JARVIS_VOICE_RATE", "+8%")

    # Outils
    g["OBS_HOST"] = get("OBS_HOST", "localhost")
    g["OBS_PORT"] = int(get("OBS_PORT", "4455"))
    g["OBS_PASSWORD"] = get("OBS_PASSWORD", "")
    g["FFMPEG"] = get("FFMPEG_PATH", "ffmpeg")
    # Si "1", les actions sensibles s'exécutent sans demander confirmation vocale.
    g["AUTO_CONFIRM"] = get("JARVIS_AUTO_CONFIRM", "0") == "1"

    # Mises à jour : à chaque lancement, Jarvis récupère les corrections publiées sur ce dépôt GitHub (updater.py).
    g["UPDATE_REPO"] = get("JARVIS_UPDATE_REPO", "ZoloMach/jarvis")
    g["AUTO_UPDATE"] = get("JARVIS_AUTO_UPDATE", "1") == "1"


def save(**values):
    """Enregistre des réglages dans le .env (ex : save(ANTHROPIC_API_KEY="sk-...")) puis recharge."""
    ENV_FILE.touch(exist_ok=True)
    for k, v in values.items():
        set_key(str(ENV_FILE), k, str(v), quote_mode="never")
        os.environ[k] = str(v)
    reload()


reload()
