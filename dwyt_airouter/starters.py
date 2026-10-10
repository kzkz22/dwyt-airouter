"""Starting and stopping the GPU host's containers: local Docker, Docker over SSH, Unraid API.

Every starter only starts and stops containers that already exist on the GPU host (dwyt-gpu's
compose file creates them; on Unraid they come from templates). States are normalised to
"running", "stopped" or None (no such container).
"""
from __future__ import annotations

import json
import os
import socket
import ssl
import subprocess
import urllib.error
import urllib.request
from urllib.parse import urlsplit

from .config import Config, GpuHost


class StarterError(Exception):
    """The GPU host or its API could not be reached or refused the request."""


class Unreachable(StarterError):
    pass


def tcp_open(host: str, port: int, timeout: float = 3) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


class Docker:
    """`docker` CLI, locally or with -H ssh://user@host (key-based SSH login needed)."""

    def __init__(self, host: GpuHost) -> None:
        self.host = host
        self.prefix = ["docker"] + (["-H", f"ssh://{host.ssh}"] if host.starter == "docker-ssh" else [])

    def _run(self, *args: str, timeout: float = 60) -> subprocess.CompletedProcess:
        try:
            return subprocess.run([*self.prefix, *args], capture_output=True, text=True, timeout=timeout,
                                  check=False)
        except FileNotFoundError as exc:
            raise StarterError("A docker parancs nincs telepítve ezen a gépen.") from exc
        except subprocess.TimeoutExpired as exc:
            raise Unreachable(f"A docker nem válaszolt {int(timeout)} s alatt.") from exc

    def reachable(self) -> bool:
        if self.host.starter == "docker":
            return True
        target = self.host.ssh.split("@")[-1]
        name, _, port = target.partition(":")
        return tcp_open(name, int(port or 22))

    def state(self, name: str) -> str | None:
        proc = self._run("inspect", "--format", "{{.State.Status}}", name)
        if proc.returncode != 0:
            err = (proc.stderr or "").lower()
            if "no such" in err:
                return None
            raise Unreachable(f"docker inspect {name}: {(proc.stderr or proc.stdout).strip()[:300]}")
        return "running" if proc.stdout.strip() in ("running", "restarting") else "stopped"

    def start(self, name: str) -> None:
        proc = self._run("start", name, timeout=120)
        if proc.returncode != 0:
            raise StarterError(f"docker start {name}: {(proc.stderr or proc.stdout).strip()[:300]}")

    def stop(self, name: str) -> None:
        proc = self._run("stop", "--time", "30", name, timeout=120)
        if proc.returncode != 0 and "no such" not in (proc.stderr or "").lower():
            raise StarterError(f"docker stop {name}: {(proc.stderr or proc.stdout).strip()[:300]}")


class Unraid:
    """Unraid API (GraphQL), key with DOCKER read + update permission only (UNRAID_API_KEY)."""

    def __init__(self, host: GpuHost) -> None:
        self.host = host
        self.url = host.unraid_url + "/graphql"
        self.key = os.environ.get("UNRAID_API_KEY", "")
        self.ctx = ssl._create_unverified_context() if host.unraid_insecure_tls else None  # noqa: S323

    def reachable(self) -> bool:
        parts = urlsplit(self.host.unraid_url)
        return tcp_open(parts.hostname or "", parts.port or (443 if parts.scheme == "https" else 80))

    def gql(self, query: str) -> dict:
        if not self.key:
            raise StarterError("Hiányzik az UNRAID_API_KEY (az /etc/dwyt-airouter/airouter.env fájlban).")
        req = urllib.request.Request(self.url, data=json.dumps({"query": query}).encode(), method="POST",
                                     headers={"x-api-key": self.key, "content-type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=30, context=self.ctx) as resp:
                data = json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            raise StarterError(f"Az Unraid API HTTP {exc.code} hibát adott"
                               + (" (rossz vagy kevés jogú API-kulcs?)" if exc.code in (401, 403) else "")) from exc
        except (urllib.error.URLError, OSError, ValueError) as exc:
            raise Unreachable(f"Az Unraid API nem érhető el: {exc}") from exc
        if data.get("errors"):
            raise StarterError(f"Az Unraid API hibát adott: {json.dumps(data['errors'])[:300]}")
        return data.get("data") or {}

    def _find(self, name: str) -> tuple[str, str] | None:
        data = self.gql("query { docker { containers { id names state } } }")
        for c in (data.get("docker") or {}).get("containers") or []:
            if any(str(n).lstrip("/") == name for n in c.get("names") or []):
                return c["id"], c.get("state", "")
        return None

    def state(self, name: str) -> str | None:
        found = self._find(name)
        if found is None:
            return None
        return "running" if found[1].upper() == "RUNNING" else "stopped"

    def _mutate(self, action: str, name: str) -> None:
        found = self._find(name)
        if found is None:
            raise StarterError(f"Nincs ilyen konténer az Unraidon: {name}")
        self.gql(f'mutation {{ docker {{ {action}(id: {json.dumps(found[0])}) {{ id state }} }} }}')

    def start(self, name: str) -> None:
        self._mutate("start", name)

    def stop(self, name: str) -> None:
        if self.state(name) == "running":
            self._mutate("stop", name)


def starter_for(cfg: Config) -> Docker | Unraid:
    return Unraid(cfg.gpu_host) if cfg.gpu_host.starter == "unraid" else Docker(cfg.gpu_host)
