# dwyt-airouter

A **dwyt** AI-routere egy mindig bekapcsolt gépre. Két program fut rajta:

- **llama-swap:** egyedül birtokolja a GPU-t, sorba állítja a kéréseket, és indítja vagy leállítja a GPU-gép ([dwyt-gpu](https://github.com/kzkz22/dwyt-gpu)) konténereit.
- **LiteLLM:** stabil modellneveket és felhős tartalékot ad a futtatónak és a többi kliensnek (OpenCode, Hermes, Open WebUI).

Egy Whisper-munka egyetlen hosszú kérés a llama-swapon át. Amíg tart, a GPU a Whisperé, az LLM-kérések várnak.

- **Egyetlen `models.yaml`:** a GPU-gép, a konténerek, a helyi és felhős modellek, a stabil nevek. A `dwyt-airouter generate` ebből írja a llama-swap és a LiteLLM beállítását, a llama-server presetjeit (`models.ini`) és a GPU-gép letöltési listáját (`downloads.json`). Minta: [models.example.yaml](models.example.yaml).
- **Indítók:** helyi Docker, Docker SSH-n át, Unraid API. Opcionális ébresztés (Wake-on-LAN): ha a GPU-gép nem válaszol, felkelti, és megvárja.
- **llama.cpp router módban:** egy llama-server konténer, a presetek közötti váltás nem indítja újra.

Telepítés: [docs/telepites.md](docs/telepites.md) · frissítés: [docs/frissites.md](docs/frissites.md) · terv: [dwyt-docs, 9. fejezet](https://github.com/kzkz22/dwyt-docs/blob/main/docs/terv.md)

## Parancsok

| Parancs | Mire |
| --- | --- |
| `dwyt-airouter generate` | beállítások készítése a `models.yaml`-ból (`/etc/dwyt-airouter/generated/`) |
| `dwyt-airouter check` | a `models.yaml`, a GPU-gép és a konténerek ellenőrzése |
| `dwyt-airouter wake` | a GPU-gép felébresztése, és várakozás rá |
| `dwyt-airouter container run\|stop NÉV` | a llama-swap indító- és leállítóparancsa (kézzel ritkán kell) |

## Fejlesztés

```bash
uv venv && uv pip install -e ".[test]"
uv run pytest -q
```

A tesztek a `docker` parancsot és az Unraid API-t utánozzák. Ha a `LLAMA_SWAP_BIN` egy llama-swap programra mutat, a generált beállítást azzal is ellenőrzik (a CI a v262-vel).

## Licenc

MIT, lásd [LICENSE](LICENSE).
