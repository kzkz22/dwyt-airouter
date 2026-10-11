"""dwyt-airouter: the AI router's tools.

  dwyt-airouter [--config models.yaml] generate [--out DIR]   write the llama-swap / LiteLLM configs,
                                                               models.ini and downloads.json
  dwyt-airouter container run ENTRY | stop ENTRY [PID]        llama-swap's cmd / cmdStop
  dwyt-airouter wake                                          wake the GPU host and wait for it
  dwyt-airouter check                                         config, GPU host, containers
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys

from . import __version__, container, generate, wake
from .config import DEFAULT_CONFIG, ConfigError, load, secret
from .starters import StarterError, starter_for

DEFAULT_OUT = "/etc/dwyt-airouter/generated"


def _check(cfg) -> int:
    ok = True

    def report(good: bool, text: str) -> None:
        nonlocal ok
        ok &= good
        print(f"{'rendben' if good else 'HIBA   '}  {text}")

    report(True, f"models.yaml: {cfg.path} ({len(cfg.local_models)} helyi, {len(cfg.cloud_models)} felhős modell, "
                 f"{len(cfg.names)} stabil név)")
    starter = starter_for(cfg)
    up = starter.reachable()
    report(up or bool(cfg.gpu_host.wake), f"GPU-gép ({cfg.gpu_host.starter}): "
           + ("elérhető" if up else "nem érhető el" + (" (ébresztéssel indítható)" if cfg.gpu_host.wake else "")))
    if up:
        for c in cfg.containers():
            try:
                state = starter.state(c.container)
                report(state is not None, f"konténer {c.container}: "
                       + {"running": "fut", "stopped": "leállítva", None: "nincs ilyen"}[state])
            except StarterError as exc:
                report(False, f"konténer {c.container}: {exc}")
    if cfg.gpu_host.starter == "unraid":
        report(bool(secret(cfg, "UNRAID_API_KEY")), "UNRAID_API_KEY (környezet vagy airouter.env)")
    if cfg.litellm and cfg.cloud_models:
        print(f"         a felhős kulcs ({cfg.cloud_key_env}) és a LITELLM_MASTER_KEY a litellm.env-ben legyen")
    if not shutil.which("llama-swap") and not os.path.exists("/opt/llama-swap/llama-swap"):
        print("figyelem  a llama-swap nincs a szokásos helyen (/opt/llama-swap/llama-swap)")
    print("Minden rendben." if ok else "Van javítanivaló (lásd fent).")
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(prog="dwyt-airouter", description="A dwyt AI-router eszközei.")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--config", help=f"models.yaml (alapból DWYT_AIROUTER_CONFIG vagy {DEFAULT_CONFIG})")
    sub = parser.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("generate", help="beállítások készítése a models.yaml-ból")
    g.add_argument("--out", default=DEFAULT_OUT, help=f"célmappa (alapból {DEFAULT_OUT})")
    c = sub.add_parser("container", help="a llama-swap indító- és leállítóparancsa")
    c.add_argument("action", choices=("run", "stop"))
    c.add_argument("entry")
    c.add_argument("pid", nargs="?", type=int)
    sub.add_parser("wake", help="a GPU-gép felébresztése")
    sub.add_parser("check", help="ellenőrzés")
    args = parser.parse_args(argv)
    container.setup_logging()
    try:
        cfg = load(args.config)
        if args.cmd == "generate":
            changed = generate.write(cfg, args.out)
            for path in changed:
                print(f"frissült: {path}")
            if not changed:
                print("nincs változás")
            if any(p.name == "litellm.yaml" for p in changed):
                print("A LiteLLM-et újra kell indítani: systemctl restart dwyt-litellm")
            if any(p.name in ("models.ini", "downloads.json") for p in changed):
                print("A models.ini-t másold a GPU-gép modellmappájába, és töltsd le az új modelleket "
                      "(dwyt-gpu download downloads.json).")
            return 0
        if args.cmd == "container":
            if args.action == "run":
                return container.run(cfg, args.entry)
            return container.stop(cfg, args.entry, args.pid)
        if args.cmd == "wake":
            if not cfg.gpu_host.wake:
                print("Nincs ébresztés beállítva (gpu_host.wake).", file=sys.stderr)
                return 1
            starter = starter_for(cfg)
            ok = starter.reachable() or wake.wake_and_wait(cfg.gpu_host.wake, starter.reachable)
            print("A GPU-gép elérhető." if ok else "A GPU-gép nem ébredt fel.")
            return 0 if ok else 1
        return _check(cfg)
    except ConfigError as exc:
        print(f"Beállítási hiba: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
