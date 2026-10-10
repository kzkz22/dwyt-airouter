"""What llama-swap runs for a GPU container (its `cmd` and `cmdStop`).

  run ENTRY        wake the GPU host if needed, stop the other GPU containers, start ENTRY's
                   container, then keep running while it runs. llama-swap treats this process
                   as the model: when it exits, the model counts as stopped.
  stop ENTRY [PID] stop the container, wait until it has stopped, then end the `run` process.
"""
from __future__ import annotations

import logging
import os
import signal
import sys
import threading
import time

from . import wake
from .config import Config
from .starters import StarterError, Unreachable, starter_for

log = logging.getLogger("dwyt-airouter")
POLL_S = float(os.environ.get("DWYT_AIROUTER_POLL_S", "5"))
STOP_WAIT_S = 60


def run(cfg: Config, entry: str, stop_event: threading.Event | None = None) -> int:
    target = cfg.by_entry(entry).container
    starter = starter_for(cfg)
    stop_event = stop_event or threading.Event()
    if threading.current_thread() is threading.main_thread():
        signal.signal(signal.SIGTERM, lambda *_: stop_event.set())
        signal.signal(signal.SIGINT, lambda *_: stop_event.set())
    try:
        if not starter.reachable():
            if not cfg.gpu_host.wake:
                log.error("the GPU host is not reachable and no wake-up is configured")
                return 1
            if not wake.wake_and_wait(cfg.gpu_host.wake, starter.reachable, stop_event):
                log.error("the GPU host did not come up within %s s", cfg.gpu_host.wake.wait_s)
                return 1
            # Just booted: its Docker service may need a while before the containers show up.
            deadline = time.monotonic() + cfg.gpu_host.wake.wait_s
            while not stop_event.is_set():
                try:
                    if starter.state(target) is not None:
                        break
                except Unreachable:
                    pass
                if time.monotonic() > deadline:
                    break
                stop_event.wait(3)
        for other in cfg.gpu_containers():
            if other == target:
                continue
            if starter.state(other) == "running":
                log.info("stopping %s: the GPU is needed by %s", other, target)
                starter.stop(other)
        state = starter.state(target)
        if state is None:
            log.error("there is no container named %s on the GPU host", target)
            return 1
        if state != "running":
            log.info("starting %s", target)
            starter.start(target)
        else:
            log.info("%s is already running", target)
    except StarterError as exc:
        log.error("%s", exc)
        return 1

    fails = 0
    while not stop_event.wait(POLL_S):
        try:
            state = starter.state(target)
            fails = 0
        except Unreachable as exc:
            fails += 1
            log.warning("cannot check %s (%s)", target, exc)
            if fails >= 3:
                log.error("lost contact with the GPU host")
                return 1
            continue
        except StarterError as exc:
            log.error("%s", exc)
            return 1
        if state != "running":
            log.info("%s is %s", target, state or "gone")
            return 0
    return 0


def stop(cfg: Config, entry: str, pid: int | None) -> int:
    target = cfg.by_entry(entry).container
    starter = starter_for(cfg)
    code = 0
    try:
        if starter.reachable() and starter.state(target) == "running":
            log.info("stopping %s", target)
            starter.stop(target)
            deadline = time.monotonic() + STOP_WAIT_S
            while time.monotonic() < deadline and starter.state(target) == "running":
                time.sleep(2)
    except StarterError as exc:
        log.error("%s", exc)
        code = 1
    if pid:
        try:
            os.kill(pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            pass
    return code


def setup_logging() -> None:
    logging.basicConfig(level=logging.INFO, stream=sys.stderr,
                        format="[dwyt-airouter] %(message)s")
