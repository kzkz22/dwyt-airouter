# dwyt-airouter

The **dwyt** AI router for an always-on machine: LiteLLM (stable names, cloud fallback; optional) in front of
llama-swap, which alone owns the GPU queue and starts/stops the GPU host's containers. Starters: local Docker,
Docker over SSH, Unraid API (port of the old `unraid-container.sh`); optional Wake-on-LAN step. One `models.yaml`
generates the LiteLLM and llama-swap configs and the GPU host's download list.

Lessons to keep from the old setup: a Whisper job is ONE long streamed request through llama-swap (so the GPU
is not swapped away mid-job); llama-swap selectors never retry, which is why LiteLLM stays for fallback.

Status: planning only. Source of truth: `dwyt-docs`. License: MIT.

## Conventions

- The owner writes in Hungarian. User-facing docs (`README.md`, `docs/`) and any UI are Hungarian;
  code, comments and this file are English.
- The plan and the decision log live in `dwyt-docs` (`docs/terv.md`, section 20). Read the relevant
  sections before changing anything; when a decision changes, update it there in the same piece of work.
- The central–runner protocol is specified in `dwyt-docs/docs/protokoll.md`; both sides follow it.
- Never commit tokens or keys (API keys, OAuth secrets, runner/MCP tokens). Secrets live in env files or
  the runner's local store, never in the repo.
- Add a test for every behaviour change.
- The old system (`yt-transcribe`, `yt-transcribe-webui`) stays separate and unchanged; code may be
  ported from it, but nothing here may depend on it at runtime.
