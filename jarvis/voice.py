"""Synthèse vocale : Edge TTS (voix neuronale gratuite, nécessite Internet), repli sur pyttsx3 hors ligne."""
import asyncio
import queue
import threading
import time

import numpy as np
import sounddevice as sd

from . import config

SR = 24000


def _tone(freqs, dur=0.09, vol=0.25):
    parts = []
    for f in freqs:
        t = np.linspace(0, dur, int(SR * dur), False)
        env = np.minimum(1, np.minimum(t, dur - t) * 40)
        parts.append(np.sin(2 * np.pi * f * t) * env * vol)
    return (np.concatenate(parts) * 32767).astype(np.int16)


BEEP_WAKE = _tone([880, 1320])
BEEP_SLEEP = _tone([1320, 660])


class Speaker:
    """File d'attente de phrases jouées dans l'ordre, interruptible à tout moment."""

    def __init__(self, enabled=True):
        self.enabled = enabled
        self._q: queue.Queue = queue.Queue()
        self._stop = threading.Event()
        self._busy = threading.Event()
        self._offline = None
        threading.Thread(target=self._worker, daemon=True).start()

    # --- API publique ---
    def say(self, text):
        text = text.strip()
        if text:
            print(f"🤖 {config.NAME} : {text}")
            if self.enabled:
                self._q.put(("text", text))

    def beep(self, sound=BEEP_WAKE):
        if self.enabled:
            self._q.put(("pcm", sound))

    def stop(self):
        """Coupe la parole immédiatement et vide la file."""
        self._stop.set()
        while not self._q.empty():
            try:
                self._q.get_nowait()
            except queue.Empty:
                break

    @property
    def speaking(self):
        return self._busy.is_set() or not self._q.empty()

    def wait(self, poll=None):
        """Attend la fin de la parole. `poll()` peut renvoyer True pour interrompre (barge-in)."""
        while self.speaking:
            if poll and poll():
                self.stop()
                return True
            time.sleep(0.02)
        return False

    # --- interne ---
    def _worker(self):
        while True:
            kind, payload = self._q.get()
            self._busy.set()
            self._stop.clear()
            try:
                pcm = payload if kind == "pcm" else self._synth(payload)
                if pcm is not None and not self._stop.is_set():
                    self._play(pcm)
            except Exception as e:  # noqa: BLE001
                print(f"[voix] {e}")
            finally:
                if self._q.empty():
                    self._busy.clear()

    def _play(self, pcm):
        sd.play(pcm, SR)
        time.sleep(0.05)
        while sd.get_stream().active:
            if self._stop.is_set():
                sd.stop()
                return
            time.sleep(0.02)

    def _synth(self, text):
        try:
            return self._edge(text)
        except Exception as e:  # noqa: BLE001
            print(f"[voix] Edge TTS indisponible ({e}), voix hors ligne.")
            self._say_offline(text)
            return None

    def _edge(self, text):
        import edge_tts
        import miniaudio

        async def fetch():
            data = bytearray()
            async for chunk in edge_tts.Communicate(text, config.TTS_VOICE, rate=config.TTS_RATE).stream():
                if chunk["type"] == "audio":
                    data.extend(chunk["data"])
            return bytes(data)

        mp3 = asyncio.run(fetch())
        dec = miniaudio.decode(mp3, output_format=miniaudio.SampleFormat.SIGNED16, nchannels=1, sample_rate=SR)
        return np.array(dec.samples, dtype=np.int16)

    def _say_offline(self, text):
        import pyttsx3

        if self._offline is None:
            self._offline = pyttsx3.init()
            for v in self._offline.getProperty("voices"):
                if "fr" in (v.id + v.name).lower():
                    self._offline.setProperty("voice", v.id)
                    break
        self._offline.say(text)
        self._offline.runAndWait()
