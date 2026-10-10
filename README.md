# dwyt-airouter

A **dwyt** AI-routere: LiteLLM + llama-swap egy mindig bekapcsolt gépen. A llama-swap egyedül birtokolja a GPU-t, sorba állítja a kéréseket, és indítja vagy leállítja a GPU-gép ([dwyt-gpu](https://github.com/kzkz22/dwyt-gpu)) konténereit; a LiteLLM stabil modellneveket és felhős tartalékot ad a futtatónak és a felhasználó többi kliensének (OpenCode, Hermes, Open WebUI).

- Indítók: helyi Docker, Docker SSH-n át, Unraid API; opcionális ébresztés (Wake-on-LAN).
- Egyetlen `models.yaml`, amiből a LiteLLM és a llama-swap beállítása készül.
- Terv és döntések: [dwyt-docs/docs/terv.md](https://github.com/kzkz22/dwyt-docs/blob/main/docs/terv.md) (9. fejezet)

## Állapot

Terv; kód még nincs.

## Licenc

MIT, lásd [LICENSE](LICENSE).
