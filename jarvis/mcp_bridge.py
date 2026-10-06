"""Petit serveur MCP (stdio) lancé par Claude Code : il relaie les outils de Jarvis.

Claude Code démarre ce script ; chaque appel d'outil est transmis à la fenêtre Jarvis
(qui l'exécute, avec sa confirmation vocale) via http://127.0.0.1:JARVIS_BRIDGE_PORT.
Le protocole MCP stdio est du JSON-RPC, un message JSON par ligne.
"""
import json
import os
import sys
import urllib.request

PORT = os.environ["JARVIS_BRIDGE_PORT"]
TOKEN = os.environ["JARVIS_BRIDGE_TOKEN"]
BASE = f"http://127.0.0.1:{PORT}"


def _http(path, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(BASE + path, data=data, headers={"X-Jarvis-Token": TOKEN,
                                                                  "Content-Type": "application/json"})  # fmt: skip
    with urllib.request.urlopen(req, timeout=900) as r:
        return json.loads(r.read())


def _to_mcp(result):
    """Convertit un résultat d'outil Jarvis (texte ou blocs façon API Claude) en contenu MCP."""
    if isinstance(result, str):
        return [{"type": "text", "text": result}]
    out = []
    for block in result:
        if block.get("type") == "image":
            src = block["source"]
            out.append({"type": "image", "data": src["data"], "mimeType": src["media_type"]})
        else:
            out.append({"type": "text", "text": block.get("text", "")})
    return out


def handle(msg):
    method = msg.get("method")
    params = msg.get("params") or {}
    if method == "initialize":
        return {
            "protocolVersion": params.get("protocolVersion", "2025-06-18"),
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "jarvis", "version": "1.0"},
        }
    if method == "ping":
        return {}
    if method == "tools/list":
        return {"tools": _http("/tools")}
    if method == "tools/call":
        try:
            r = _http("/call", {"name": params["name"], "args": params.get("arguments") or {}})
            return {"content": _to_mcp(r["result"]), "isError": False}
        except Exception as e:  # noqa: BLE001
            return {"content": [{"type": "text", "text": f"Erreur du pont Jarvis : {e}"}], "isError": True}
    raise KeyError(method)


def main():
    sys.stdin.reconfigure(encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        msg = json.loads(line)
        if "id" not in msg:  # notification : pas de réponse
            continue
        try:
            reply = {"jsonrpc": "2.0", "id": msg["id"], "result": handle(msg)}
        except KeyError:
            reply = {"jsonrpc": "2.0", "id": msg["id"], "error": {"code": -32601, "message": "Méthode inconnue"}}
        sys.stdout.write(json.dumps(reply) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
