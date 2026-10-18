# -*- coding: utf-8 -*-
"""无界面 Python sidecar：给 Tauri/WebView2/浏览器提供 HTTP API。

启动：
    python sidecar_server.py --port 18765

页面：http://127.0.0.1:18765/
API： POST /api/<method>  {"args": [...]}，需 X-Xinyu-Token
健康：GET /health
"""
import argparse
import json
import os
import secrets
import signal
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlparse

BASE = os.path.dirname(os.path.abspath(__file__))
if BASE not in sys.path:
    sys.path.insert(0, BASE)

BOOT = time.perf_counter()


class SidecarServer(ThreadingHTTPServer):
    allow_reuse_address = True
    daemon_threads = True


class Handler(BaseHTTPRequestHandler):
    server_version = "XinyuSidecar/1.0"

    def log_message(self, fmt, *args):
        if os.environ.get("XINYU_SIDECAR_DEBUG"):
            sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def _send(self, status, body, content_type="application/json; charset=utf-8"):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _json(self, status, data):
        self._send(status, json.dumps(data, ensure_ascii=False, default=str))

    def do_GET(self):
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            self._send(200, self.server.html, "text/html; charset=utf-8")
        elif path == "/health":
            self._json(200, {
                "ok": True,
                "version": self.server.version,
                "pid": os.getpid(),
                "port": self.server.server_address[1],
            })
        elif path == "/favicon.ico":
            self._send(204, b"", "image/x-icon")
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self):
        path = urlparse(self.path).path
        if not path.startswith("/api/"):
            return self._json(404, {"error": "not found"})
        if self.headers.get("X-Xinyu-Token") != self.server.token:
            return self._json(403, {"error": "forbidden"})
        name = unquote(path[len("/api/"):])
        if not name or name.startswith("_") or "." in name:
            return self._json(400, {"error": "invalid method"})
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return self._json(400, {"error": "invalid length"})
        if length > 8 * 1024 * 1024:
            return self._json(413, {"error": "body too large"})
        try:
            payload = json.loads(self.rfile.read(length) or b"{}")
            args = payload.get("args", [])
            if not isinstance(args, list):
                raise ValueError("args must be a list")
        except (ValueError, TypeError):
            return self._json(400, {"error": "invalid json"})
        method = getattr(self.server.api, name, None)
        if not callable(method) or name.startswith("_"):
            return self._json(404, {"error": "method not found"})
        try:
            result = method(*args)
            self._json(200, result)
        except Exception as exc:  # noqa: BLE001 - sidecar 边界
            self._json(500, {"__error__": {"code": "INTERNAL", "message": str(exc)[:300]}})


def _write_ready_file(data_root, port, token):
    path = os.path.join(data_root, "data", "sidecar.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    temp = path + ".tmp"
    with open(temp, "w", encoding="utf-8") as handle:
        json.dump({"port": port, "token": token, "pid": os.getpid(), "at": time.time()}, handle)
    os.replace(temp, path)
    return path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=18765)
    parser.add_argument("--data-dir", default="")
    parser.add_argument("--token", default="")
    args = parser.parse_args()

    if args.data_dir:
        os.environ["XINYU_DATA_DIR"] = os.path.abspath(args.data_dir)
    os.environ.setdefault("MMKV_LOG_LEVEL", "off")

    import_started = time.perf_counter()
    from api import API
    from html_ui import build_html
    from utils import DATA_ROOT
    from version import VERSION

    import_ms = (time.perf_counter() - import_started) * 1000
    os.makedirs(DATA_ROOT, exist_ok=True)
    os.chdir(DATA_ROOT)
    api_started = time.perf_counter()
    api = API()
    api_ms = (time.perf_counter() - api_started) * 1000
    token = args.token or secrets.token_hex(16)
    html = build_html(web_mode=True, token=token)
    server = SidecarServer(("127.0.0.1", args.port), Handler)
    server.api = api
    server.token = token
    server.html = html
    server.version = VERSION
    ready = _write_ready_file(DATA_ROOT, server.server_address[1], token)
    total_ms = (time.perf_counter() - BOOT) * 1000
    perf_path = os.path.join(DATA_ROOT, "data", "sidecar_perf.json")
    try:
        with open(perf_path, "w", encoding="utf-8") as handle:
            json.dump({
                "import_api_ms": round(import_ms, 1),
                "api_init_ms": round(api_ms, 1),
                "total_ms": round(total_ms, 1),
                "port": server.server_address[1],
                "at": time.time(),
            }, handle)
    except OSError:
        pass
    print(
        "SIDECAR_READY port=%s pid=%s import_ms=%.0f api_ms=%.0f total_ms=%.0f file=%s"
        % (server.server_address[1], os.getpid(), import_ms, api_ms, total_ms, ready),
        flush=True,
    )

    def stop(_signum=None, _frame=None):
        threading.Thread(target=server.shutdown, daemon=True).start()

    try:
        signal.signal(signal.SIGINT, stop)
        signal.signal(signal.SIGTERM, stop)
    except Exception:
        pass
    try:
        server.serve_forever(poll_interval=0.2)
    finally:
        try:
            os.remove(ready)
        except OSError:
            pass
        server.server_close()
        api.close()
        print("SIDECAR_STOPPED", flush=True)


if __name__ == "__main__":
    main()
