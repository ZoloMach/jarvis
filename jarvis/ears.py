"""Écoute : micro en continu, mot d'éveil (openWakeWord), détection de parole (VAD) et transcription (faster-whisper)."""
import collections
import queue
import time

import numpy as np
import sounddevice as sd

from . import config

SR = 16000
FRAME = 1280  # 80 ms, taille attendue par openWakeWord
VAD_FRAME = 320  # 20 ms pour webrtcvad


class Ears:
    def __init__(self, use_wakeword=True):
        import webrtcvad

        self.vad = webrtcvad.Vad(2)
        self.q: queue.Queue = queue.Queue()
        self.use_wakeword = use_wakeword
        self.oww = None
        self.level = 0.0
        if use_wakeword:
            self._init_wakeword()
        print("[écoute] Chargement de Whisper...")
        from faster_whisper import WhisperModel

        # Sur processeur, int8 est rapide et léger ; « auto » tente la carte graphique NVIDIA si CUDA est installé.
        device = config.WHISPER_DEVICE
        compute = "int8" if device == "cpu" else "default"
        try:
            self.whisper = WhisperModel(config.WHISPER_MODEL, device=device, compute_type=compute)
        except Exception as e:  # noqa: BLE001 - carte graphique mal configurée : on se rabat sur le processeur
            print(f"[écoute] Whisper sur {device} impossible ({e}), passage sur le processeur.")
            self.whisper = WhisperModel(config.WHISPER_MODEL, device="cpu", compute_type="int8")
        print(f"[écoute] Whisper « {config.WHISPER_MODEL} » prêt.", flush=True)
        self.stream = sd.InputStream(samplerate=SR, channels=1, dtype="int16", blocksize=FRAME, callback=self._cb)
        self.stream.start()

    def _init_wakeword(self):
        import openwakeword
        from openwakeword.model import Model

        try:
            openwakeword.utils.download_models([config.WAKEWORD_MODEL])
        except Exception as e:  # noqa: BLE001
            print(f"[écoute] Téléchargement du modèle de mot d'éveil : {e}")
        self.oww = Model(wakeword_models=[config.WAKEWORD_MODEL], inference_framework="onnx")

    def _cb(self, indata, frames, t, status):
        frame = indata[:, 0].copy()
        # Niveau du micro entre 0 et 1, pour l'animation de la fenêtre.
        self.level = min(1.0, float(np.sqrt(np.mean(frame.astype(np.float32) ** 2))) / 6000)
        self.q.put(frame)

    def clear(self):
        while not self.q.empty():
            try:
                self.q.get_nowait()
            except queue.Empty:
                break

    def _frame(self, timeout=None):
        try:
            return self.q.get(timeout=timeout)
        except queue.Empty:
            return None

    # --- Mot d'éveil ---
    def heard_wakeword(self, frame):
        scores = self.oww.predict(frame)
        if max(scores.values()) >= config.WAKEWORD_THRESHOLD:
            self.oww.reset()
            return True
        return False

    def wait_wakeword(self, interrupt=None):
        """Bloque jusqu'au mot d'éveil (renvoie True) ou jusqu'à ce que `interrupt()` soit vrai (renvoie False)."""
        self.clear()
        while True:
            if interrupt and interrupt():
                return False
            f = self._frame(timeout=0.1)
            if f is not None and self.heard_wakeword(f):
                return True

    def poll_wakeword(self):
        """Non bloquant : traite les trames en attente, True si le mot d'éveil a été entendu (pour interrompre Jarvis)."""
        if not self.oww:
            return False
        hit = False
        while not self.q.empty():
            f = self._frame(0)
            if f is not None and self.heard_wakeword(f):
                hit = True
        return hit

    # --- Enregistrement d'une phrase ---
    def _is_speech(self, frame):
        voiced = sum(self.vad.is_speech(frame[i : i + VAD_FRAME].tobytes(), SR) for i in range(0, FRAME, VAD_FRAME))
        return voiced >= 2

    def record(self, start_timeout=6.0, end_silence=0.9, max_len=30.0):
        """Attend que l'utilisateur parle (au plus `start_timeout` s), puis enregistre jusqu'à un silence.

        Renvoie un tableau float32 ou None si personne n'a parlé.
        """
        self.clear()
        pre = collections.deque(maxlen=4)  # garde ~300 ms avant le début de la parole
        t0 = time.time()
        speech, started, silent, streak = [], False, 0.0, 0
        while True:
            f = self._frame(timeout=0.5)
            if f is None:
                if not started and start_timeout is not None and time.time() - t0 > start_timeout:
                    return None
                continue
            if not started:
                pre.append(f)
                streak = streak + 1 if self._is_speech(f) else 0
                if streak >= 2:
                    started = True
                    speech.extend(pre)
                elif start_timeout is not None and time.time() - t0 > start_timeout:
                    return None
                continue
            speech.append(f)
            silent = 0.0 if self._is_speech(f) else silent + FRAME / SR
            if silent >= end_silence or len(speech) * FRAME / SR > max_len:
                break
        return np.concatenate(speech).astype(np.float32) / 32768.0

    def transcribe(self, audio):
        segments, _ = self.whisper.transcribe(
            audio, language=config.LANGUAGE, beam_size=1, vad_filter=True, initial_prompt=f"{config.NAME}, "
        )
        return " ".join(s.text.strip() for s in segments).strip()
