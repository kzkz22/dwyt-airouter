"""Wake-on-LAN: a magic packet, then wait until the GPU host answers."""
from __future__ import annotations

import logging
import socket
import threading
import time
from typing import Callable

from .config import Wake

log = logging.getLogger("dwyt-airouter")
RESEND_S = 30


def magic_packet(mac: str) -> bytes:
    raw = bytes.fromhex(mac.replace(":", "").replace("-", ""))
    return b"\xff" * 6 + raw * 16


def send(w: Wake) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        s.sendto(magic_packet(w.mac), (w.broadcast, w.port))


def wake_and_wait(w: Wake, reachable: Callable[[], bool], stop: threading.Event | None = None) -> bool:
    stop = stop or threading.Event()
    deadline = time.monotonic() + w.wait_s
    last_sent = 0.0
    while time.monotonic() < deadline and not stop.is_set():
        if time.monotonic() - last_sent >= RESEND_S:
            log.info("waking the GPU host (%s)", w.mac)
            send(w)
            last_sent = time.monotonic()
        if reachable():
            log.info("the GPU host is up")
            return True
        stop.wait(3)
    return False
