"""Cerveau « abonnement » : Jarvis réfléchit avec Claude Code, inclus dans les abonnements Claude Pro et Max,
au lieu de l'API payée à l'usage.

Fonctionnement : pour chaque demande, Jarvis lance `claude -p` (mode sans fenêtre de Claude Code) et lit sa
réponse en direct. Les outils de Jarvis (OBS, jeux, montage...) sont fournis à Claude Code par un petit
serveur MCP (mcp_bridge.py) qui renvoie chaque appel vers ce processus, où l'outil s'exécute avec la
confirmation vocale habituelle.
"""
import json
import os
import platform
import queue
import re
import secrets
import shutil
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import config, tools
from .brain import system_prompt

IS_WINDOWS = platform.system() == "Windows"
NO_WINDOW = 0x08000000 if IS_WINDOWS else 0  # pas de fenêtre console pour les sous-processus
NEW_CONSOLE = 0x00000010 if IS_WINDOWS else 0
SESSION_IDLE = 20 * 60  # après 20 min sans parler, on repart sur une conversation neuve
SILENCE_TIMEOUT = 90  # secondes sans aucun signe de Claude Code (hors outil en cours) avant abandon
TOTAL_TIMEOUT = 10 * 60
EXTRA_PROMPT = (
    "\n\nTes outils Jarvis portent le préfixe mcp__jarvis__. Tu peux aussi chercher sur le web avec "
    "WebSearch et lire une page avec WebFetch."
)


class ClaudeCodeError(RuntimeError):
    pass


def log(message):
    print(f"[cerveau] {message}", flush=True)


def _kill_tree(proc):
    """Arrête Claude Code et ses sous-processus (serveur MCP compris)."""
    try:
        if IS_WINDOWS:
            subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True,
                           creationflags=NO_WINDOW)  # fmt: skip
        else:
            os.killpg(proc.pid, 9)
    except Exception:  # noqa: BLE001
        try:
            proc.kill()
        except Exception:  # noqa: BLE001
            pass


def explain_error(message):
    """Traduit une erreur de Claude Code en phrase compréhensible."""
    m = message.lower()
    if any(k in m for k in ("login", "log in", "not logged", "invalid api key", "authentication", "oauth")):
        return "Ton abonnement Claude n'est pas connecté : ouvre les Réglages et clique sur « Connecter mon abonnement »."
    if any(k in m for k in ("usage limit", "limit reached", "rate limit", "limite")):
        return "Tu as atteint la limite d'utilisation de ton abonnement Claude pour le moment. Réessaie plus tard."
    if "n'est pas installé" in m:
        return message
    if "ne répond pas" in m:
        return ("Claude Code ne répond pas, j'ai arrêté la demande. Réessaie ; si ça recommence, clique sur "
                "« Journal » et colle le texte copié dans ta conversation avec Claude.")
    return f"Claude Code a rencontré un problème : {message[:300]}"


def find_claude():
    exe = shutil.which("claude")
    if exe:
        return exe
    for p in (Path.home() / ".local" / "bin" / "claude.exe", Path.home() / ".local" / "bin" / "claude"):
        if p.exists():
            return str(p)
    return None


def _env():
    env = dict(os.environ)
    # Avec une clé API dans l'environnement, Claude Code facturerait à l'usage : on force l'abonnement.
    env.pop("ANTHROPIC_API_KEY", None)
    env.pop("ANTHROPIC_AUTH_TOKEN", None)
    # Si Jarvis a été lancé depuis une session Claude Code, on ne s'y rattache pas.
    env.pop("CLAUDECODE", None)
    env.pop("CLAUDE_CODE_SESSION_ID", None)
    return env


def auth_status():
    """Renvoie "absent" (Claude Code pas installé), "deconnecte" ou "connecte"."""
    exe = find_claude()
    if not exe:
        return "absent"
    try:
        r = subprocess.run([exe, "auth", "status", "--json"], capture_output=True, text=True, timeout=60,
                           env=_env(), creationflags=NO_WINDOW)  # fmt: skip
        return "connecte" if json.loads(r.stdout or "{}").get("loggedIn") else "deconnecte"
    except Exception:  # noqa: BLE001
        return "deconnecte"


def login():
    """Ouvre une fenêtre qui connecte Claude Code au compte Claude de l'utilisateur (via le navigateur)."""
    exe = find_claude()
    if not exe:
        raise ClaudeCodeError("Claude Code n'est pas installé.")
    subprocess.Popen([exe, "auth", "login", "--claudeai"], env=_env(), creationflags=NEW_CONSOLE)


def install():
    """Installe Claude Code avec l'installeur officiel. Renvoie True si c'est bon."""
    if IS_WINDOWS:
        cmd = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command",
               "irm https://claude.ai/install.ps1 | iex"]  # fmt: skip
    else:
        cmd = ["bash", "-c", "curl -fsSL https://claude.ai/install.sh | bash"]
    subprocess.run(cmd, capture_output=True, timeout=900, creationflags=NO_WINDOW)
    return find_claude() is not None


class ToolBridge:
    """Serveur HTTP local (127.0.0.1, protégé par un jeton) qui exécute les outils de Jarvis pour mcp_bridge.py."""

    def __init__(self):
        self.token = secrets.token_hex(16)
        self.confirm = lambda action, details="": False
        self.on_tool = lambda name, args: None
        self.active = 0  # outils en cours d'exécution (le chien de garde patiente pendant ce temps)
        self.last_done = 0.0
        bridge = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def _ok(self):
                if self.headers.get("X-Jarvis-Token") != bridge.token:
                    self.send_error(403)
                    return False
                return True

            def _send(self, obj):
                body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):  # noqa: N802
                if self._ok() and self.path == "/tools":
                    self._send([
                        {"name": t.name, "description": t.description, "inputSchema": t.schema()["input_schema"]}
                        for t in tools.REGISTRY.values()
                    ])  # fmt: skip

            def do_POST(self):  # noqa: N802
                if not self._ok() or self.path != "/call":
                    return
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
                name, args = body.get("name", ""), body.get("args") or {}
                bridge.on_tool(name, args)
                log(f"Outil {name} {json.dumps(args, ensure_ascii=False)[:200]}")
                bridge.active += 1
                try:
                    result = tools.run(name, args, bridge.confirm)
                finally:
                    bridge.active -= 1
                    bridge.last_done = time.time()
                self._send({"result": result if isinstance(result, list) else str(result)[:20000]})

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True, name="jarvis-bridge").start()


def _python_for_bridge():
    # pythonw.exe n'a pas d'entrée/sortie standard fiable : on prend python.exe à côté s'il existe.
    exe = Path(sys.executable)
    console = exe.with_name("python.exe")
    return str(console if exe.name.lower() == "pythonw.exe" and console.exists() else exe)


class ClaudeCodeBrain:
    def __init__(self):
        self.exe = find_claude()
        if not self.exe:
            raise ClaudeCodeError("Claude Code n'est pas installé : ouvre les Réglages pour connecter ton abonnement.")
        self.bridge = ToolBridge()
        self.session_id = None
        self.last = 0.0
        self.proc = None
        self._cancelled = False
        self.mcp_config = config.DATA_DIR / "mcp-jarvis.json"
        self.mcp_config.write_text(json.dumps({"mcpServers": {"jarvis": {
            "type": "stdio",
            "command": _python_for_bridge(),
            "args": [str(Path(__file__).with_name("mcp_bridge.py"))],
            "env": {"JARVIS_BRIDGE_PORT": str(self.bridge.port), "JARVIS_BRIDGE_TOKEN": self.bridge.token},
        }}}), encoding="utf-8")  # fmt: skip

    def reset(self):
        self.session_id = None

    def cancel(self):
        """Arrête la demande en cours (bouton « Arrêter »)."""
        self._cancelled = True
        if self.proc and self.proc.poll() is None:
            log("Demande annulée par l'utilisateur.")
            _kill_tree(self.proc)

    def ask(self, text, on_sentence, confirm, on_tool=None):
        self._cancelled = False
        self.bridge.confirm = confirm
        self.bridge.on_tool = on_tool or (lambda name, args: None)
        if time.time() - self.last > SESSION_IDLE:
            self.session_id = None
        model = next((m for m in ("opus", "haiku") if m in config.MODEL), "sonnet")
        cmd = [
            self.exe, "-p",
            "--output-format", "stream-json", "--verbose", "--include-partial-messages",
            "--model", model,
            "--system-prompt", system_prompt() + EXTRA_PROMPT,
            "--mcp-config", str(self.mcp_config), "--strict-mcp-config",
            "--tools", "WebSearch,WebFetch",
            # Personne ne peut répondre à une demande d'autorisation ici : tout ce qui n'est pas
            # explicitement autorisé est refusé, au lieu de rester bloqué à attendre.
            "--permission-mode", "dontAsk", "--permission-prompts", "none",
            "--allowedTools", "mcp__jarvis", "WebSearch", "WebFetch",
        ]  # fmt: skip
        if self.session_id:
            cmd += ["--resume", self.session_id]
        env = _env()
        env["MCP_TOOL_TIMEOUT"] = "900000"  # une confirmation peut prendre du temps
        t0 = time.time()
        log(f"Appel de Claude Code ({model}, {'suite' if self.session_id else 'nouvelle conversation'}) : {text!r}")
        proc = self.proc = subprocess.Popen(
            cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace", cwd=str(config.DATA_DIR), env=env,
            creationflags=NO_WINDOW, start_new_session=not IS_WINDOWS,
        )  # fmt: skip
        err_lines = []

        def read_err():
            for line in proc.stderr:
                err_lines.append(line)
                log(f"[claude stderr] {line.rstrip()[:300]}")

        threading.Thread(target=read_err, daemon=True).start()
        proc.stdin.write(text)
        proc.stdin.close()

        # Chien de garde : si Claude Code ne donne plus signe de vie (hors outil en cours), on l'arrête.
        state = {"last": time.time(), "timeout": None}

        def watchdog():
            while proc.poll() is None:
                now = time.time()
                if self.bridge.active == 0 and now - max(state["last"], self.bridge.last_done) > SILENCE_TIMEOUT:
                    state["timeout"] = f"aucune réponse depuis {SILENCE_TIMEOUT} secondes"
                elif now - t0 > TOTAL_TIMEOUT:
                    state["timeout"] = f"plus de {TOTAL_TIMEOUT // 60} minutes"
                if state["timeout"]:
                    log(f"Délai dépassé ({state['timeout']}) : arrêt de Claude Code.")
                    _kill_tree(proc)
                    return
                time.sleep(1)

        threading.Thread(target=watchdog, daemon=True).start()

        buf, final, first = "", None, True

        def flush(all_text=False):
            nonlocal buf
            parts = re.split(r"(?<=[.!?…])\s+", buf)
            done, buf = (parts, "") if all_text else (parts[:-1], parts[-1])
            for sentence in done:
                if sentence.strip():
                    on_sentence(sentence)

        # Lecture dans un fil à part : la boucle ci-dessous ne peut jamais rester bloquée sur le tuyau.
        lines = queue.Queue()

        def read_out():
            for out_line in proc.stdout:
                lines.put(out_line)
            lines.put(None)

        threading.Thread(target=read_out, daemon=True).start()
        while True:
            try:
                line = lines.get(timeout=0.5)
            except queue.Empty:
                if state["timeout"] or self._cancelled:
                    break
                continue
            if line is None:
                break
            state["last"] = time.time()
            try:
                ev = json.loads(line)
            except ValueError:
                continue
            kind = ev.get("type")
            if kind == "system" and ev.get("subtype") == "init":
                self.session_id = ev.get("session_id") or self.session_id
                log(f"Claude Code a démarré en {time.time() - t0:.1f} s (outils MCP : "
                    f"{[s.get('status') for s in ev.get('mcp_servers', [])]}).")  # fmt: skip
            elif kind == "stream_event":
                e = ev.get("event", {})
                if e.get("type") == "content_block_delta" and e.get("delta", {}).get("type") == "text_delta":
                    if first:
                        log(f"Premiers mots reçus après {time.time() - t0:.1f} s.")
                        first = False
                    buf += e["delta"]["text"]
                    flush()
                elif e.get("type") in ("content_block_stop", "message_stop"):
                    flush(all_text=True)
            elif kind == "result":
                final = ev
                self.session_id = ev.get("session_id") or self.session_id
                log(f"Réponse terminée en {time.time() - t0:.1f} s ({ev.get('subtype')}).")
                break  # la réponse est complète : inutile d'attendre la fin du processus
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _kill_tree(proc)
        flush(all_text=True)
        self.proc = None
        if self._cancelled:
            return
        if state["timeout"]:
            self.session_id = None
            raise ClaudeCodeError(f"Claude Code ne répond pas ({state['timeout']}).")
        if final is None or final.get("is_error"):
            detail = (final or {}).get("result") or "".join(err_lines)[-500:] or f"code {proc.returncode}"
            if final is None and self.session_id:
                self.session_id = None  # conversation peut-être corrompue : on repartira de zéro
            log(f"Erreur de Claude Code : {detail.strip()[:500]}")
            raise ClaudeCodeError(detail.strip())
        self.last = time.time()
