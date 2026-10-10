"""Fakes: a `docker` command on PATH (state in a JSON file) and a small Unraid GraphQL server."""
from __future__ import annotations

import json
import os
import stat
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

FAKE_DOCKER = '''#!{python}
import json, os, sys
state_file = os.environ["FAKE_DOCKER_STATE"]
args = sys.argv[1:]
with open(state_file + ".log", "a") as log:
    log.write(" ".join(args) + "\\n")
if args[:1] == ["-H"]:
    args = args[2:]
state = json.load(open(state_file))
name = args[-1]
if name not in state:
    sys.stderr.write("Error: No such container: " + name + "\\n"); sys.exit(1)
if args[0] == "inspect":
    print(state[name]); sys.exit(0)
state[name] = "running" if args[0] == "start" else "exited"
json.dump(state, open(state_file, "w"))
print(name)
'''


class FakeDocker:
    def __init__(self, tmp: Path, monkeypatch, containers: dict[str, str]) -> None:
        bindir = tmp / "bin"
        bindir.mkdir()
        exe = bindir / "docker"
        exe.write_text(FAKE_DOCKER.format(python=sys.executable))
        exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
        self.state_file = tmp / "docker.json"
        self.set(containers)
        monkeypatch.setenv("PATH", f"{bindir}{os.pathsep}{os.environ['PATH']}")
        monkeypatch.setenv("FAKE_DOCKER_STATE", str(self.state_file))

    def set(self, containers: dict[str, str]) -> None:
        self.state_file.write_text(json.dumps(containers))

    def state(self) -> dict[str, str]:
        return json.loads(self.state_file.read_text())

    def calls(self) -> list[str]:
        log = Path(str(self.state_file) + ".log")
        return log.read_text().splitlines() if log.exists() else []


class FakeUnraid:
    def __init__(self, key: str = "unraid-key") -> None:
        self.key = key
        self.containers = {"dwyt-llama": "EXITED", "dwyt-whisper": "EXITED", "other-gpu": "RUNNING"}
        self.queries: list[str] = []
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["content-length"])))
                if self.headers.get("x-api-key") != fake.key:
                    self.send_response(401)
                    self.end_headers()
                    return
                q = body["query"]
                fake.queries.append(q)
                if q.startswith("query"):
                    data = {"docker": {"containers": [{"id": f"id-{n}", "names": [f"/{n}"], "state": s}
                                                      for n, s in fake.containers.items()]}}
                else:
                    action = "start" if "start(" in q else "stop"
                    cid = q.split('id: "')[1].split('"')[0]
                    name = cid[3:]
                    fake.containers[name] = "RUNNING" if action == "start" else "EXITED"
                    data = {"docker": {action: {"id": cid, "state": fake.containers[name]}}}
                out = json.dumps({"data": data}).encode()
                self.send_response(200)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(out)))
                self.end_headers()
                self.wfile.write(out)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self) -> None:
        self.server.shutdown()


@pytest.fixture
def unraid():
    fake = FakeUnraid()
    yield fake
    fake.close()


def write_config(tmp: Path, text: str) -> Path:
    path = tmp / "models.yaml"
    path.write_text(text)
    return path


BASE = """
version: 1
gpu_host:
  starter: docker
llama_server:
  container: dwyt-llama
whisper:
  container: dwyt-whisper
  models: [large-v3]
local_models:
  - name: Qwen-Gnrl
    file: org/Qwen-GGUF/Qwen-Q4.gguf
    args: {ctx-size: 32768, temp: 0.7}
    max_input_tokens: 32768
  - name: Qwen-Code
    file: org/Qwen-GGUF/Qwen-Q4.gguf
    mmproj: org/Qwen-GGUF/mmproj-F16.gguf
    vision: true
cloud:
  models:
    - {name: cloud/flash, model: openrouter/qwen/flash}
    - {name: cloud/flash-gyors, model: openrouter/qwen/flash, thinking: false}
names:
  - {name: auto, model: Qwen-Code, fallback: cloud/flash}
  - {name: osszefoglalo, model: Qwen-Gnrl, thinking: false, fallback: [cloud/flash-gyors]}
  - {name: osszefoglalo-helyi, model: Qwen-Gnrl, thinking: false}
"""
