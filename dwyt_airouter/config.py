"""models.yaml: the one file that describes the GPU host, its containers and every model.

From it `dwyt-airouter generate` writes the llama-swap and LiteLLM configs, the llama-server
presets (models.ini) and the GPU host's download list. See models.example.yaml.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

DEFAULT_CONFIG = "/etc/dwyt-airouter/models.yaml"
STARTERS = ("docker", "docker-ssh", "unraid")
NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/+-]{0,127}$")
CONTAINER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
ENTRY = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
ARG = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
MAC = re.compile(r"^([0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}$")
HF_FILE = re.compile(r"^[A-Za-z0-9][\w.-]*/[\w.-]+/[\w./-]+$")
HF_REPO = re.compile(r"^[A-Za-z0-9][\w.-]*/[\w.-]+$")
DIARIZATION_REPO = "pyannote/speaker-diarization-community-1"
WHISPER_REPOS = {"large-v3": "Systran/faster-whisper-large-v3",
                 "large-v3-turbo": "mobiuslabsgmbh/faster-whisper-large-v3-turbo",
                 "large-v2": "Systran/faster-whisper-large-v2",
                 "medium": "Systran/faster-whisper-medium",
                 "small": "Systran/faster-whisper-small"}


class ConfigError(Exception):
    """A user-facing problem with models.yaml (Hungarian)."""


@dataclass
class Wake:
    mac: str
    broadcast: str = "255.255.255.255"
    port: int = 9
    wait_s: int = 240


@dataclass
class GpuHost:
    starter: str
    address: str
    ssh: str = ""
    unraid_url: str = ""
    unraid_insecure_tls: bool = False
    wake: Wake | None = None
    other_gpu_containers: list[str] = field(default_factory=list)
    start_timeout_s: int = 180


@dataclass
class Container:
    entry: str            # llama-swap entry name (also the /upstream/<entry> path)
    container: str        # container name on the GPU host
    port: int
    ttl: int = 0
    unlisted: bool = False
    check: str = "/health"
    title: str = ""


@dataclass
class LocalModel:
    name: str
    file: str
    mmproj: str = ""
    args: dict[str, Any] = field(default_factory=dict)
    max_input_tokens: int | None = None
    max_output_tokens: int | None = None
    vision: bool = False


@dataclass
class CloudModel:
    name: str
    model: str
    thinking: bool | None = None
    max_input_tokens: int | None = None
    max_output_tokens: int | None = None


@dataclass
class StableName:
    name: str
    model: str
    thinking: bool | None = None
    fallback: list[str] = field(default_factory=list)


@dataclass
class Config:
    path: Path
    gpu_host: GpuHost
    llama: Container
    llama_args: dict[str, Any]
    whisper: Container | None
    whisper_models: list[str]
    diarization: bool
    prefetch: list[str]
    extra: list[Container]
    local_models: list[LocalModel]
    cloud_key_env: str
    cloud_models: list[CloudModel]
    names: list[StableName]
    litellm: bool
    litellm_port: int
    litellm_listen: str
    swap_port: int
    swap_listen: str
    program: str

    def containers(self) -> list[Container]:
        return [self.llama] + ([self.whisper] if self.whisper else []) + self.extra

    def by_entry(self, entry: str) -> Container:
        for c in self.containers():
            if c.entry == entry:
                return c
        raise ConfigError(f"Nincs ilyen bejegyzés a models.yaml-ban: {entry} "
                          f"(van: {', '.join(c.entry for c in self.containers())})")

    def gpu_containers(self) -> list[str]:
        return [c.container for c in self.containers()] + self.gpu_host.other_gpu_containers


def secret(cfg: "Config", name: str) -> str:
    """A secret from the environment, else from airouter.env next to models.yaml (KEY=value lines).

    llama-swap's unit loads airouter.env into the environment of the starters; reading the file
    here as well lets `dwyt-airouter check` and manual runs work without exporting it first."""
    if os.environ.get(name):
        return os.environ[name]
    path = cfg.path.parent / "airouter.env"
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return ""
    for n, line in enumerate(lines, 1):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ConfigError(f"{path} {n}. sora nem NÉV=érték alakú. A helyes sor: {name}=a-kulcs")
        key, _, value = line.partition("=")
        if key.strip().removeprefix("export ").strip() == name:
            return value.strip().strip("\"'")
    return ""


# ---- reading ------------------------------------------------------------------------------

class _Reader:
    def __init__(self, data: Any, where: str) -> None:
        if data is None:
            data = {}
        if not isinstance(data, dict):
            raise ConfigError(f"{where}: kulcs–érték párokat vártam.")
        self.data, self.where, self.used = data, where, set()

    def get(self, key: str, kind: type | tuple, default: Any = None, required: bool = False) -> Any:
        self.used.add(key)
        if key not in self.data or self.data[key] is None:
            if required:
                raise ConfigError(f"{self.where}: hiányzik a(z) '{key}'.")
            return default
        value = self.data[key]
        kinds = kind if isinstance(kind, tuple) else (kind,)
        if bool in kinds or not isinstance(value, bool):
            if isinstance(value, kinds):
                return value
        raise ConfigError(f"{self.where}.{key}: rossz típus ({type(value).__name__}).")

    def sub(self, key: str) -> _Reader:
        return _Reader(self.get(key, dict, {}), f"{self.where}.{key}")

    def done(self) -> None:
        unknown = set(self.data) - self.used
        if unknown:
            raise ConfigError(f"{self.where}: ismeretlen kulcs: {', '.join(sorted(map(str, unknown)))}")


def _port(value: int, where: str) -> int:
    if not 1 <= value <= 65535:
        raise ConfigError(f"{where}: a port 1 és 65535 között legyen.")
    return value


def _args(data: dict, where: str) -> dict[str, Any]:
    out = {}
    for key, value in (data or {}).items():
        key = str(key)
        if not ARG.match(key) or key in ("model", "mmproj", "host", "port", "models-preset", "models-max"):
            raise ConfigError(f"{where}: ezt a kapcsolót itt nem lehet megadni: {key}")
        if not isinstance(value, (str, int, float, bool)) or (isinstance(value, str) and "\n" in value):
            raise ConfigError(f"{where}.{key}: egyszerű érték kell (szöveg, szám, igen/nem).")
        out[key] = value
    return out


def _container(r: _Reader, entry: str, default_name: str, default_port: int, default_ttl: int,
               unlisted: bool) -> Container:
    c = Container(entry=r.get("entry", str, entry), container=r.get("container", str, default_name),
                  port=_port(r.get("port", int, default_port), r.where), ttl=r.get("ttl", int, default_ttl),
                  unlisted=r.get("unlisted", bool, unlisted), check=r.get("check", str, "/health"),
                  title=r.get("title", str, ""))
    if not ENTRY.match(c.entry):
        raise ConfigError(f"{r.where}.entry: csak kisbetű, szám, '-' és '_' lehet: {c.entry}")
    if not CONTAINER.match(c.container):
        raise ConfigError(f"{r.where}.container: érvénytelen konténernév: {c.container}")
    if not c.check.startswith("/"):
        raise ConfigError(f"{r.where}.check: '/'-rel kezdődő útvonal kell.")
    return c


def load(path: str | Path | None = None) -> Config:
    path = Path(path or os.environ.get("DWYT_AIROUTER_CONFIG") or DEFAULT_CONFIG)
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ConfigError(f"A models.yaml nem olvasható ({path}): {exc}") from exc
    except yaml.YAMLError as exc:
        raise ConfigError(f"A models.yaml hibás ({path}): {exc}") from exc
    top = _Reader(raw, "models.yaml")
    if top.get("version", int, required=True) != 1:
        raise ConfigError("models.yaml: csak a version: 1 ismert.")

    g = top.sub("gpu_host")
    starter = g.get("starter", str, required=True)
    if starter not in STARTERS:
        raise ConfigError(f"gpu_host.starter: {' | '.join(STARTERS)} lehet, nem {starter}.")
    wake = None
    if g.data.get("wake"):
        w = g.sub("wake")
        wake = Wake(mac=w.get("mac", str, required=True), broadcast=w.get("broadcast", str, "255.255.255.255"),
                    port=_port(w.get("port", int, 9), "gpu_host.wake"), wait_s=w.get("wait_s", int, 240))
        if not MAC.match(wake.mac):
            raise ConfigError(f"gpu_host.wake.mac: érvénytelen MAC-cím: {wake.mac}")
        w.done()
    else:
        g.get("wake", dict)
    host = GpuHost(starter=starter, address=g.get("address", str, "127.0.0.1" if starter == "docker" else None,
                                                  required=starter != "docker"),
                   ssh=g.get("ssh", str, ""), unraid_url=g.get("unraid_url", str, "").rstrip("/"),
                   unraid_insecure_tls=g.get("unraid_insecure_tls", bool, False), wake=wake,
                   other_gpu_containers=[str(x) for x in g.get("other_gpu_containers", list, [])],
                   start_timeout_s=g.get("start_timeout_s", int, 180))
    g.done()
    if starter == "docker-ssh" and not re.match(r"^[\w.-]+@[\w.-]+(:\d+)?$|^[\w.-]+$", host.ssh or ""):
        raise ConfigError("gpu_host.ssh: a docker-ssh indítóhoz felhasználó@gép kell (például root@192.168.1.20).")
    if starter == "unraid" and not host.unraid_url.startswith(("http://", "https://")):
        raise ConfigError("gpu_host.unraid_url: az Unraid címe kell (például http://192.168.1.20).")
    for name in host.other_gpu_containers:
        if not CONTAINER.match(name):
            raise ConfigError(f"gpu_host.other_gpu_containers: érvénytelen konténernév: {name}")
    if wake and starter == "docker":
        raise ConfigError("gpu_host.wake: helyi Docker esetén nincs mit felébreszteni.")

    lr = top.sub("llama_server")
    llama = _container(lr, "llama-server", "dwyt-llama", 8001, 0, False)
    llama_args = _args(lr.get("args", dict, {}), "llama_server.args")
    lr.done()

    whisper, whisper_models, diarization, prefetch = None, [], False, []
    if top.data.get("whisper") is not False:
        wr = top.sub("whisper")
        if wr.data.get("enabled", True):
            whisper = _container(wr, "whisper", "dwyt-whisper", 8766, 600, True)
        wr.get("enabled", bool, True)
        whisper_models = [str(m) for m in wr.get("models", list, ["large-v3", "large-v3-turbo"])]
        for m in whisper_models:
            if m not in WHISPER_REPOS:
                raise ConfigError(f"whisper.models: ismeretlen Whisper-modell: {m} (ismert: {', '.join(WHISPER_REPOS)})")
        diarization = wr.get("diarization", bool, True)
        prefetch = [str(p) for p in wr.get("prefetch", list, [])]
        for p in prefetch:
            if not HF_REPO.match(p):
                raise ConfigError(f"whisper.prefetch: Hugging Face-repó kell (szervezet/név): {p}")
        wr.done()
    else:
        top.get("whisper", bool)

    extra = []
    for i, item in enumerate(top.get("extra_containers", list, [])):
        er = _Reader(item, f"extra_containers[{i}]")
        er.get("entry", str, required=True)
        extra.append(_container(er, "", "", 0, er.data.get("ttl", 600), True))
        er.done()

    local_models = []
    for i, item in enumerate(top.get("local_models", list, [])):
        mr = _Reader(item, f"local_models[{i}]")
        m = LocalModel(name=mr.get("name", str, required=True), file=mr.get("file", str, required=True),
                       mmproj=mr.get("mmproj", str, ""), args=_args(mr.get("args", dict, {}), f"{mr.where}.args"),
                       max_input_tokens=mr.get("max_input_tokens", int), max_output_tokens=mr.get("max_output_tokens", int),
                       vision=mr.get("vision", bool, False))
        mr.done()
        for f in [m.file] + ([m.mmproj] if m.mmproj else []):
            if not HF_FILE.match(f) or ".." in f or not f.endswith(".gguf"):
                raise ConfigError(f"{mr.where}: a fájl alakja szervezet/repó/fájl.gguf legyen: {f}")
        local_models.append(m)

    cr = top.sub("cloud")
    cloud_key_env = cr.get("api_key_env", str, "OPENROUTER_API_KEY")
    cloud_models = []
    for i, item in enumerate(cr.get("models", list, [])):
        mr = _Reader(item, f"cloud.models[{i}]")
        cloud_models.append(CloudModel(name=mr.get("name", str, required=True), model=mr.get("model", str, required=True),
                                       thinking=mr.get("thinking", bool), max_input_tokens=mr.get("max_input_tokens", int),
                                       max_output_tokens=mr.get("max_output_tokens", int)))
        mr.done()
    cr.done()
    if not re.match(r"^[A-Z][A-Z0-9_]*$", cloud_key_env):
        raise ConfigError("cloud.api_key_env: egy környezeti változó neve kell (például OPENROUTER_API_KEY).")

    names = []
    for i, item in enumerate(top.get("names", list, [])):
        nr = _Reader(item, f"names[{i}]")
        fallback = nr.get("fallback", (str, list), [])
        names.append(StableName(name=nr.get("name", str, required=True), model=nr.get("model", str, required=True),
                                thinking=nr.get("thinking", bool),
                                fallback=[fallback] if isinstance(fallback, str) else [str(f) for f in fallback]))
        nr.done()

    lt = top.sub("litellm")
    litellm = lt.get("enabled", bool, True)
    litellm_port = _port(lt.get("port", int, 4000), "litellm")
    litellm_listen = lt.get("listen", str, "0.0.0.0")
    lt.done()
    sw = top.sub("llama_swap")
    swap_port = _port(sw.get("port", int, 8080), "llama_swap")
    swap_listen = sw.get("listen", str, "0.0.0.0")
    sw.done()
    program = top.get("program", str, "/opt/dwyt-airouter/venv/bin/dwyt-airouter")
    top.done()

    cfg = Config(path=path.resolve(), gpu_host=host, llama=llama, llama_args=llama_args, whisper=whisper,
                 whisper_models=whisper_models, diarization=diarization, prefetch=prefetch, extra=extra,
                 local_models=local_models, cloud_key_env=cloud_key_env, cloud_models=cloud_models, names=names,
                 litellm=litellm, litellm_port=litellm_port, litellm_listen=litellm_listen, swap_port=swap_port,
                 swap_listen=swap_listen, program=program)
    _cross_check(cfg)
    return cfg


def _cross_check(cfg: Config) -> None:
    seen: dict[str, str] = {}
    for kind, name in ([("helyi modell", m.name) for m in cfg.local_models]
                       + [("felhős modell", m.name) for m in cfg.cloud_models]
                       + [("stabil név", n.name) for n in cfg.names]):
        if not NAME.match(name):
            raise ConfigError(f"Érvénytelen modellnév: {name!r}")
        if name in seen:
            raise ConfigError(f"A(z) {name} név kétszer szerepel ({seen[name]}, {kind}).")
        seen[name] = kind
    entries = [c.entry for c in cfg.containers()]
    if len(set(entries)) != len(entries):
        raise ConfigError(f"Két konténer-bejegyzés neve egyezik: {', '.join(entries)}")
    containers = [c.container for c in cfg.containers()]
    if len(set(containers)) != len(containers):
        raise ConfigError(f"Két bejegyzés ugyanazt a konténert használja: {', '.join(containers)}")
    local = {m.name for m in cfg.local_models}
    cloud = {m.name for m in cfg.cloud_models}
    if cfg.cloud_models and not cfg.litellm:
        raise ConfigError("Felhős modellekhez LiteLLM kell (litellm.enabled: true).")
    for n in cfg.names:
        if n.model not in local | cloud:
            raise ConfigError(f"names: a(z) {n.name} ismeretlen modellre mutat: {n.model}")
        for f in n.fallback:
            if f not in local | cloud:
                raise ConfigError(f"names: a(z) {n.name} tartaléka ismeretlen modell: {f}")
        if n.fallback and not cfg.litellm:
            raise ConfigError(f"names: a(z) {n.name} tartalékához LiteLLM kell (litellm.enabled: true).")
        if not cfg.litellm and n.model in cloud:
            raise ConfigError(f"names: a(z) {n.name} felhős modellre mutat; ehhez LiteLLM kell.")
