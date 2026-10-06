"""Mode console : python -m jarvis [--texte] [--sans-mot-eveil] [--muet] ; la fenêtre : python -m jarvis --fenetre"""
import argparse
import sys

from . import config, tools
from .brain import Brain
from .engine import NAME_RE, YES, is_stop, norm  # noqa: F401
from .voice import BEEP_SLEEP, BEEP_WAKE, Speaker


def text_mode(brain, speaker):
    print(f"{config.NAME} en mode texte. Tape 'quitter' pour sortir.\n")

    def confirm(action, details=""):
        speaker.say(f"Je dois confirmer avant de {action}. On y va ?")
        print(details)
        return input("   Confirmer ? (o/n) > ").strip().lower() in ("o", "oui", "y", "yes")

    while True:
        try:
            text = input("🧑 Toi : ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if text.lower() in ("quitter", "exit", "quit"):
            break
        if text:
            brain.ask(text, speaker.say, confirm)
            speaker.wait()


def voice_mode(brain, speaker, use_wakeword):
    from .ears import Ears

    ears = Ears(use_wakeword=use_wakeword)

    def listen(timeout):
        audio = ears.record(start_timeout=timeout)
        if audio is None:
            return None
        text = ears.transcribe(audio)
        if text:
            print(f"🧑 {config.USER_NAME} : {text}")
        return text

    def confirm(action, details=""):
        print(details)
        speaker.say(f"Je dois confirmer avant de {action}. Je le fais ?")
        speaker.wait()
        answer = listen(8) or ""
        ok = any(w in norm(answer) for w in YES) and "non" not in norm(answer).split()
        if not ok:
            speaker.say("Très bien, j'annule.")
        return ok

    hint = f"dis « Hey {config.NAME} »" if use_wakeword else f"commence ta phrase par « {config.NAME} »"
    speaker.say(f"{config.NAME} en ligne. À votre service, {config.USER_NAME}.")
    speaker.wait()
    print(f"\n[écoute] Prêt : {hint}. « Merci {config.NAME} » pour terminer une conversation. Ctrl+C pour quitter.\n")

    in_conversation = False
    while True:
        if not in_conversation:
            if use_wakeword:
                ears.wait_wakeword()
                speaker.stop()
                speaker.beep(BEEP_WAKE)
                speaker.wait()
                timeout = 6
            else:
                timeout = None  # écoute permanente, on filtre sur le nom
        else:
            timeout = config.FOLLOWUP_SECONDS

        text = listen(timeout)
        if text is None:
            if in_conversation:
                speaker.beep(BEEP_SLEEP)
            in_conversation = False
            continue
        if not text:
            continue
        if not use_wakeword and not in_conversation:
            if not NAME_RE.search(text):
                continue  # on ne parlait pas à Jarvis
            speaker.beep(BEEP_WAKE)
        if is_stop(text):
            speaker.say("À votre service.")
            speaker.wait()
            in_conversation = False
            continue

        try:
            brain.ask(text, speaker.say, confirm)
        except Exception as e:  # noqa: BLE001
            print(f"[erreur] {e}")
            speaker.say("Désolé, j'ai rencontré un problème en traitant ça.")
        # Pendant qu'il parle, dire « Hey Jarvis » le coupe.
        ears.clear()
        speaker.wait(poll=ears.poll_wakeword if use_wakeword else None)
        in_conversation = True


def main():
    ap = argparse.ArgumentParser(description=f"{config.NAME}, assistant personnel vocal")
    ap.add_argument("--texte", action="store_true", help="Discuter au clavier au lieu de la voix")
    ap.add_argument("--sans-mot-eveil", action="store_true", help="Écoute permanente : réagit quand on dit son nom")
    ap.add_argument("--muet", action="store_true", help="Pas de synthèse vocale (réponses écrites seulement)")
    ap.add_argument("--fenetre", action="store_true", help="Ouvrir la fenêtre graphique")
    args = ap.parse_args()
    if args.fenetre:
        from .gui import main as gui_main

        return gui_main()

    tools.load_all()
    try:
        if config.BRAIN == "api":
            brain = Brain()
        else:
            from .claude_brain import ClaudeCodeBrain

            brain = ClaudeCodeBrain()
    except Exception as e:  # noqa: BLE001
        raise SystemExit(str(e)) from e
    speaker = Speaker(enabled=not args.muet)
    tools.meta.notify = speaker.say  # les rappels sont annoncés à voix haute
    print(f"[outils] {len(tools.REGISTRY)} outils chargés.")

    try:
        if args.texte:
            text_mode(brain, speaker)
        else:
            voice_mode(brain, speaker, use_wakeword=not args.sans_mot_eveil)
    except KeyboardInterrupt:
        pass
    print("\nÀ bientôt.")
    sys.exit(0)


if __name__ == "__main__":
    main()
