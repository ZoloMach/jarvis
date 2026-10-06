"""Enregistrement et streaming via OBS Studio (WebSocket intégré à OBS 28+)."""
import functools

from .. import config
from . import tool

_client = None


def _obs():
    global _client
    if _client is None:
        import logging

        import obsws_python as obs

        logging.getLogger("obsws_python").setLevel(logging.CRITICAL)

        _client = obs.ReqClient(host=config.OBS_HOST, port=config.OBS_PORT, password=config.OBS_PASSWORD, timeout=5)
    return _client


def _reset_on_error(func):
    @functools.wraps(func)
    def wrapper(*a, **kw):
        global _client
        try:
            return func(*a, **kw)
        except (ConnectionError, OSError) as e:
            _client = None
            return (
                f"Impossible de joindre OBS ({e}). Vérifie qu'OBS est ouvert et que le serveur WebSocket est activé "
                "(Outils > Paramètres du serveur WebSocket)."
            )

    return wrapper


@tool(
    "Contrôle l'enregistrement OBS : démarrer, arrêter, pause, reprendre, état.",
    {"action": {"type": "string", "enum": ["demarrer", "arreter", "pause", "reprendre", "etat"]}},
)
@_reset_on_error
def obs_enregistrement(action):
    c = _obs()
    if action == "demarrer":
        c.start_record()
        return "Enregistrement démarré."
    if action == "arreter":
        r = c.stop_record()
        return f"Enregistrement arrêté. Fichier : {getattr(r, 'output_path', 'inconnu')}"
    if action == "pause":
        c.pause_record()
        return "Enregistrement en pause."
    if action == "reprendre":
        c.resume_record()
        return "Enregistrement repris."
    s = c.get_record_status()
    return f"Enregistrement actif : {s.output_active}, en pause : {s.output_paused}, durée : {s.output_timecode}."


@tool(
    "Sauvegarde le replay buffer OBS (les dernières secondes de jeu, pour garder un clip). Le démarre s'il est éteint.",
)
@_reset_on_error
def obs_clip():
    c = _obs()
    if not c.get_replay_buffer_status().output_active:
        c.start_replay_buffer()
        return "Le replay buffer était éteint, je viens de le démarrer. Redemande-moi un clip dans un moment."
    c.save_replay_buffer()
    return "Clip sauvegardé."


@tool(
    "Contrôle le direct (stream) OBS.",
    {"action": {"type": "string", "enum": ["demarrer", "arreter", "etat"]}},
)
@_reset_on_error
def obs_stream(action):
    c = _obs()
    if action == "demarrer":
        c.start_stream()
        return "Stream lancé."
    if action == "arreter":
        c.stop_stream()
        return "Stream arrêté."
    s = c.get_stream_status()
    return f"Stream actif : {s.output_active}, durée : {s.output_timecode}."


@tool(
    "Liste les scènes OBS ou change de scène.",
    {"scene": {"type": "string", "description": "Nom de la scène à activer ; vide pour lister"}},
    required=[],
)
@_reset_on_error
def obs_scene(scene=""):
    c = _obs()
    if scene:
        c.set_current_program_scene(scene)
        return f"Scène '{scene}' activée."
    scenes = [s["sceneName"] for s in c.get_scene_list().scenes]
    return "Scènes : " + ", ".join(scenes)


@tool(
    "Coupe ou réactive une source audio OBS (ex : 'Mic/Aux', 'Audio du bureau').",
    {"source": {"type": "string"}, "muet": {"type": "boolean"}},
)
@_reset_on_error
def obs_micro(source, muet):
    _obs().set_input_mute(source, muet)
    return f"{source} {'coupé' if muet else 'réactivé'}."
