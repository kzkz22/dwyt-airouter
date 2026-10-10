# dwyt-airouter

The **dwyt** AI router for an always-on machine: LiteLLM (stable names, cloud fallback; optional) in front of
llama-swap, which alone owns the GPU queue and starts/stops the GPU host's containers. Starters: local Docker,
Docker over SSH, Unraid API (port of the old `unraid-container.sh`); optional Wake-on-LAN step. One `models.yaml`
generates the LiteLLM and llama-swap configs and the GPU host's download list.

Lessons to keep from the old setup: a Whisper job is ONE long streamed request through llama-swap (so the GPU
is not swapped away mid-job); llama-swap selectors never retry, which is why LiteLLM stays for fallback.

Status: round 2 implemented; verified locally with the real llama-swap v262 binary, a fake `docker` and the
real (faked-ML) Whisper worker; not yet run against a real GPU host. Source of truth: `dwyt-docs`. License: MIT.

## Layout

| Path | Role |
| --- | --- |
| `dwyt_airouter/config.py` | `models.yaml` reader with strict validation (Hungarian errors naming the key) |
| `dwyt_airouter/generate.py` | llama-swap.yaml, litellm.yaml, models.ini (llama-server router presets), downloads.json, ports.env |
| `dwyt_airouter/starters.py` | Docker (local / `-H ssh://`) and Unraid GraphQL: state/start/stop of existing containers |
| `dwyt_airouter/container.py` | llama-swap `cmd`/`cmdStop`: wake, stop other GPU containers, start, stay alive while running |
| `dwyt_airouter/wake.py` | Wake-on-LAN magic packet, wait until reachable |
| `deploy/` | systemd units (`dwyt-llama-swap`, `dwyt-litellm`, user `airouter`), env examples |

Pinned: llama-swap v262 (docs, CI `-validate`), LiteLLM 1.104.2. `llama-swap.yaml` keeps `${PID}` literal for
llama-swap's macro. Without LiteLLM, stable names become llama-server presets (no fallback).

## Conventions

- The owner writes in Hungarian. User-facing docs (`README.md`, `docs/`) and any UI are Hungarian;
  code, comments and this file are English.
- The plan and the decision log live in `dwyt-docs` (`docs/terv.md`, section 21). Read the relevant
  sections before changing anything; when a decision changes, update it there in the same piece of work.
- The central–runner protocol is specified in `dwyt-docs/docs/protokoll.md`; both sides follow it.
- Never commit tokens or keys (API keys, OAuth secrets, runner/MCP tokens). Secrets live in env files or
  the runner's local store, never in the repo.
- Add a test for every behaviour change.
- The old system (`yt-transcribe`, `yt-transcribe-webui`) stays separate and unchanged; code may be
  ported from it, but nothing here may depend on it at runtime.
