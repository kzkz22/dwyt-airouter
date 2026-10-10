import json

import pytest
import yaml
from conftest import BASE, ROOT, write_config

from dwyt_airouter import cli, generate
from dwyt_airouter.config import ConfigError, load


def test_example_config_is_valid(tmp_path):
    assert cli.main(["--config", str(ROOT / "models.example.yaml"), "generate", "--out", str(tmp_path)]) == 0
    assert {p.name for p in tmp_path.iterdir()} == {"llama-swap.yaml", "litellm.yaml", "models.ini",
                                                    "downloads.json", "ports.env"}


def test_generated_configs(tmp_path):
    cfg = load(write_config(tmp_path, BASE))
    swap = generate.llama_swap(cfg)
    llama, whisper = swap["models"]["llama-server"], swap["models"]["whisper"]
    assert llama["aliases"] == ["Qwen-Gnrl", "Qwen-Code"]
    assert llama["proxy"] == "http://127.0.0.1:8001"
    assert llama["cmd"].endswith(f"--config {cfg.path} container run llama-server")
    assert llama["cmdStop"].endswith("container stop llama-server ${PID}")
    assert whisper["unlisted"] is True and whisper["ttl"] == 600 and whisper["proxy"].endswith(":8766")

    lite = generate.litellm(cfg)
    by_name = {e["model_name"]: e for e in lite["model_list"]}
    assert by_name["Qwen-Code"]["litellm_params"]["api_base"] == "http://127.0.0.1:8080/v1"
    assert by_name["osszefoglalo"]["litellm_params"]["extra_body"] == {"chat_template_kwargs": {"enable_thinking": False}}
    assert "extra_body" not in by_name["auto"]["litellm_params"]
    assert by_name["cloud/flash-gyors"]["litellm_params"]["extra_body"] == {"reasoning": {"enabled": False}}
    assert by_name["cloud/flash"]["litellm_params"]["api_key"] == "os.environ/OPENROUTER_API_KEY"
    assert lite["router_settings"]["fallbacks"] == [{"auto": ["cloud/flash"]}, {"osszefoglalo": ["cloud/flash-gyors"]}]
    assert "osszefoglalo-helyi" not in json.dumps(lite["router_settings"])  # own recordings never go to the cloud

    ini = generate.models_ini(cfg)
    assert "[Qwen-Code]\nmodel = /models/gguf/Qwen-Q4.gguf\nmmproj = /models/gguf/mmproj-F16.gguf" in ini
    assert "temp = 0.7" in ini and "[osszefoglalo]" not in ini

    dl = generate.downloads(cfg)
    assert dl["files"] == [{"repo": "org/Qwen-GGUF", "path": "Qwen-Q4.gguf"},
                           {"repo": "org/Qwen-GGUF", "path": "mmproj-F16.gguf"}]
    assert [s["repo"] for s in dl["snapshots"]] == ["Systran/faster-whisper-large-v3",
                                                    "pyannote/speaker-diarization-community-1"]


def test_without_litellm_stable_names_become_presets(tmp_path):
    text = BASE.split("cloud:")[0] + """
names:
  - {name: osszefoglalo-helyi, model: Qwen-Gnrl, thinking: false}
litellm: {enabled: false}
"""
    cfg = load(write_config(tmp_path, text))
    assert generate.llama_swap(cfg)["models"]["llama-server"]["aliases"] == ["Qwen-Gnrl", "Qwen-Code",
                                                                            "osszefoglalo-helyi"]
    ini = generate.models_ini(cfg)
    assert '[osszefoglalo-helyi]\nmodel = /models/gguf/Qwen-Q4.gguf\nctx-size = 32768\ntemp = 0.7\n' \
           'chat-template-kwargs = {"enable_thinking": false}' in ini
    assert "litellm.yaml" not in generate.outputs(cfg)


def test_write_reports_only_changes(tmp_path):
    cfg = load(write_config(tmp_path, BASE))
    out = tmp_path / "out"
    assert len(generate.write(cfg, out)) == 5
    assert generate.write(cfg, out) == []
    yaml.safe_load((out / "llama-swap.yaml").read_text())
    assert "SWAP_LISTEN=0.0.0.0:8080" in (out / "ports.env").read_text()


@pytest.mark.parametrize("change, message", [
    (("starter: docker", "starter: podman"), "starter"),
    (("model: Qwen-Code, fallback", "model: Nope, fallback"), "ismeretlen modellre"),
    (("file: org/Qwen-GGUF/Qwen-Q4.gguf\n    args", "file: org/Qwen-GGUF/../x.gguf\n    args"), "fájl alakja"),
    (("args: {ctx-size: 32768", "args: {port: 1, ctx-size: 32768"), "kapcsolót"),
    (("models: [large-v3]", "models: [tiny]"), "Whisper-modell"),
    (("name: Qwen-Code", "name: Qwen-Gnrl"), "kétszer"),
    (("version: 1", "version: 1\nunknown: 3"), "ismeretlen kulcs"),
    (("container: dwyt-whisper", "container: dwyt-llama"), "ugyanazt a konténert"),
])
def test_config_errors(tmp_path, change, message):
    old, new = change
    with pytest.raises(ConfigError, match=message):
        load(write_config(tmp_path, BASE.replace(old, new, 1)))


def test_fallback_and_cloud_need_litellm(tmp_path):
    with pytest.raises(ConfigError, match="LiteLLM"):
        load(write_config(tmp_path, BASE + "litellm: {enabled: false}\n"))


def test_starter_specific_settings(tmp_path):
    with pytest.raises(ConfigError, match="ssh"):
        load(write_config(tmp_path, BASE.replace("starter: docker", "starter: docker-ssh\n  address: 10.0.0.2")))
    with pytest.raises(ConfigError, match="unraid_url"):
        load(write_config(tmp_path, BASE.replace("starter: docker", "starter: unraid\n  address: 10.0.0.2")))
    with pytest.raises(ConfigError, match="wake"):
        load(write_config(tmp_path, BASE.replace("starter: docker", "starter: docker\n  wake: {mac: 'aa:bb:cc:dd:ee:ff'}")))
    cfg = load(write_config(tmp_path, BASE.replace(
        "starter: docker", "starter: docker-ssh\n  address: 10.0.0.2\n  ssh: root@10.0.0.2\n"
        "  wake: {mac: 'aa:bb:cc:dd:ee:ff', wait_s: 100}")))
    assert generate.llama_swap(cfg)["healthCheckTimeout"] == 280


def test_cli_reports_config_errors(tmp_path, capsys):
    assert cli.main(["--config", str(tmp_path / "missing.yaml"), "generate", "--out", str(tmp_path)]) == 2
    assert "nem olvasható" in capsys.readouterr().err


@pytest.mark.skipif(not __import__("os").environ.get("LLAMA_SWAP_BIN"), reason="LLAMA_SWAP_BIN not set")
def test_llama_swap_accepts_the_generated_config(tmp_path):
    import os
    import subprocess
    cli.main(["--config", str(ROOT / "models.example.yaml"), "generate", "--out", str(tmp_path)])
    proc = subprocess.run([os.environ["LLAMA_SWAP_BIN"], "--config", str(tmp_path / "llama-swap.yaml"), "-validate"],
                          capture_output=True, text=True, timeout=30)
    assert proc.returncode == 0, proc.stdout + proc.stderr
