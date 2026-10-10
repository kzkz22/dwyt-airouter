import os
import socket
import subprocess
import sys
import threading
import time

import pytest
from conftest import BASE, FakeDocker, write_config

from dwyt_airouter import container, wake
from dwyt_airouter.config import Wake, load
from dwyt_airouter.starters import StarterError, Unraid


@pytest.fixture(autouse=True)
def fast_poll(monkeypatch):
    monkeypatch.setattr(container, "POLL_S", 0.2)


def run_in_thread(cfg, entry):
    stop = threading.Event()
    result = {}
    t = threading.Thread(target=lambda: result.setdefault("code", container.run(cfg, entry, stop)), daemon=True)
    t.start()
    return stop, t, result


def wait_for(cond, timeout=10):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if cond():
            return True
        time.sleep(0.1)
    return False


def test_local_docker_run_stops_the_other_gpu_container_and_follows_the_target(tmp_path, monkeypatch):
    docker = FakeDocker(tmp_path, monkeypatch, {"dwyt-llama": "running", "dwyt-whisper": "exited",
                                                "old-gpu": "running"})
    cfg = load(write_config(tmp_path, BASE.replace("starter: docker", "starter: docker\n  other_gpu_containers: [old-gpu]")))
    stop, t, result = run_in_thread(cfg, "whisper")
    assert wait_for(lambda: docker.state()["dwyt-whisper"] == "running")
    assert docker.state() == {"dwyt-llama": "exited", "dwyt-whisper": "running", "old-gpu": "exited"}
    time.sleep(0.5)
    assert t.is_alive(), "run must keep going while the container runs"
    docker.set({**docker.state(), "dwyt-whisper": "exited"})  # stopped from outside
    t.join(5)
    assert result["code"] == 0


def test_run_ends_on_sigterm_and_stop_stops_the_container_and_the_run_process(tmp_path, monkeypatch):
    docker = FakeDocker(tmp_path, monkeypatch, {"dwyt-llama": "exited", "dwyt-whisper": "exited"})
    cfg_path = write_config(tmp_path, BASE)
    env = {**os.environ, "DWYT_AIROUTER_POLL_S": "0.2"}
    proc = subprocess.Popen([sys.executable, "-m", "dwyt_airouter.cli", "--config", str(cfg_path), "container", "run",
                             "llama-server"], env=env)
    assert wait_for(lambda: docker.state()["dwyt-llama"] == "running")
    assert proc.poll() is None
    code = subprocess.run([sys.executable, "-m", "dwyt_airouter.cli", "--config", str(cfg_path), "container", "stop",
                           "llama-server", str(proc.pid)], env=env, timeout=30).returncode
    assert code == 0 and docker.state()["dwyt-llama"] == "exited"
    assert proc.wait(timeout=10) == 0


def test_missing_container_fails(tmp_path, monkeypatch):
    FakeDocker(tmp_path, monkeypatch, {"dwyt-llama": "exited"})
    cfg = load(write_config(tmp_path, BASE))
    assert container.run(cfg, "whisper", threading.Event()) == 1


def test_docker_over_ssh_uses_the_remote_host(tmp_path, monkeypatch):
    docker = FakeDocker(tmp_path, monkeypatch, {"dwyt-llama": "exited", "dwyt-whisper": "exited"})
    monkeypatch.setattr("dwyt_airouter.starters.tcp_open", lambda host, port, timeout=3: (host, port) == ("gpu", 2222))
    cfg = load(write_config(tmp_path, BASE.replace("starter: docker", "starter: docker-ssh\n  address: gpu\n"
                                                                       "  ssh: root@gpu:2222")))
    stop, t, _ = run_in_thread(cfg, "llama-server")
    assert wait_for(lambda: docker.state()["dwyt-llama"] == "running")
    stop.set()
    t.join(5)
    assert all(c.startswith("-H ssh://root@gpu:2222 ") for c in docker.calls())


def test_unreachable_host_without_wake_fails_fast(tmp_path, monkeypatch):
    FakeDocker(tmp_path, monkeypatch, {"dwyt-llama": "exited"})
    monkeypatch.setattr("dwyt_airouter.starters.tcp_open", lambda *a, **k: False)
    cfg = load(write_config(tmp_path, BASE.replace("starter: docker", "starter: docker-ssh\n  address: gpu\n"
                                                                       "  ssh: root@gpu")))
    started = time.time()
    assert container.run(cfg, "llama-server", threading.Event()) == 1
    assert time.time() - started < 3


def test_unraid_starter(tmp_path, monkeypatch, unraid):
    monkeypatch.setenv("UNRAID_API_KEY", unraid.key)
    cfg = load(write_config(tmp_path, BASE.replace(
        "starter: docker", f"starter: unraid\n  address: 127.0.0.1\n  unraid_url: {unraid.url}\n"
                           "  other_gpu_containers: [other-gpu]")))
    stop, t, _ = run_in_thread(cfg, "llama-server")
    assert wait_for(lambda: unraid.containers["dwyt-llama"] == "RUNNING")
    assert unraid.containers["other-gpu"] == "EXITED"
    stop.set()
    t.join(5)
    assert container.stop(cfg, "llama-server", None) == 0
    assert unraid.containers["dwyt-llama"] == "EXITED"


def test_unraid_wrong_key(tmp_path, monkeypatch, unraid):
    monkeypatch.setenv("UNRAID_API_KEY", "wrong")
    cfg = load(write_config(tmp_path, BASE.replace(
        "starter: docker", f"starter: unraid\n  address: 127.0.0.1\n  unraid_url: {unraid.url}")))
    with pytest.raises(StarterError, match="API-kulcs"):
        Unraid(cfg.gpu_host).state("dwyt-llama")
    assert container.run(cfg, "llama-server", threading.Event()) == 1


def test_wake_on_lan_sends_magic_packets_until_the_host_answers(monkeypatch):
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as listener:
        listener.bind(("127.0.0.1", 0))
        listener.settimeout(5)
        port = listener.getsockname()[1]
        calls = {"n": 0}

        def reachable():
            calls["n"] += 1
            return calls["n"] >= 2

        monkeypatch.setattr(wake, "RESEND_S", 0)
        w = Wake(mac="aa:bb:cc:dd:ee:ff", broadcast="127.0.0.1", port=port, wait_s=20)
        assert wake.wake_and_wait(w, reachable) is True
        packet, _ = listener.recvfrom(200)
        assert packet == b"\xff" * 6 + bytes.fromhex("aabbccddeeff") * 16


def test_run_wakes_the_host_first(tmp_path, monkeypatch):
    docker = FakeDocker(tmp_path, monkeypatch, {"dwyt-llama": "exited", "dwyt-whisper": "exited"})
    awake = {"up": False}
    monkeypatch.setattr("dwyt_airouter.starters.tcp_open", lambda *a, **k: awake["up"])
    monkeypatch.setattr(wake, "send", lambda w: awake.update(up=True))
    cfg = load(write_config(tmp_path, BASE.replace(
        "starter: docker", "starter: docker-ssh\n  address: gpu\n  ssh: root@gpu\n  wake: {mac: 'aa:bb:cc:dd:ee:ff'}")))
    stop, t, _ = run_in_thread(cfg, "llama-server")
    assert wait_for(lambda: docker.state()["dwyt-llama"] == "running")
    stop.set()
    t.join(5)
