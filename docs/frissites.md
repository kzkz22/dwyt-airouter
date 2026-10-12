# Az AI-router frissítése

## A program

```bash
/opt/dwyt-airouter/venv/bin/pip install --force-reinstall --no-deps git+https://github.com/kzkz22/dwyt-airouter
dwyt-airouter --version        # az új változat száma
dwyt-airouter generate         # új változat új beállításokat írhat
systemctl restart dwyt-litellm # ha a generate szerint a litellm.yaml változott
```

A llama-swap a `--watch-config` miatt magától újratölti a `llama-swap.yaml`-t. Futó munka közben ne frissíts: a konténert leállíthatja.

## Modellek módosítása

1. `nano /etc/dwyt-airouter/models.yaml`, majd `dwyt-airouter generate`.
2. Ha a `models.ini` vagy a `downloads.json` változott: másold át a GPU-gépre, és ott futtasd a `dwyt-gpu download`-ot (dwyt-gpu, frissites.md).
3. Ha a `litellm.yaml` változott: `systemctl restart dwyt-litellm`.

## Frissítés a 0.2-re (modellfájlok repónként külön mappában)

Két Hugging Face-repóban gyakran ugyanolyan nevű fájl van (például `mmproj-F16.gguf`), és a régi elrendezésben a második felülírta volna az elsőt. A 0.2-től minden fájl a GPU-gépen a `gguf/<szervezet>/<repó>/` mappába kerül, a `models.ini` is oda mutat, a `downloads.json` pedig 2-es változatú.

1. **Előbb a GPU-gépen** frissítsd a `dwyt-gpu`-t (a régi letöltő a 2-es listát nem fogadja el): dwyt-gpu, frissites.md.
2. Itt a program frissítése (fent), majd `dwyt-airouter generate`.
3. A `models.ini`-t és a `downloads.json`-t másold a GPU-gépre, és ott `dwyt-gpu download`. A már letöltött fájlokat a régi helyükről nem veszi át: vagy újra letölti őket, vagy előtte kézzel áthelyezed őket az új mappába (`gguf/unsloth/<repó>/`).

A `chat-template-kwargs` értéke egy JSON-objektum szövegként, egyszeres idézőjelben:

```yaml
chat-template-kwargs: '{"preserve_thinking": true, "reasoning_effort": "medium"}'
```

Ha egy stabil név (LiteLLM nélkül) kikapcsolja a gondolkodást, az `enable_thinking` ehhez adódik hozzá, a modell saját kapcsolói megmaradnak.

## A `kerdes` név (dwyt 6. kör)

A dwyt központjában feltett kérdésekhez a futtató a `kerdes` nevet használja (gondolkodással, felhős tartalékkal). Ha a `models.yaml`-od régebbi, a `names:` alá vedd fel:

```yaml
  - name: kerdes
    model: Qwen3.6-35B-A3B-Gnrl
    thinking: true
    fallback: cloud/qwen3.8-flash
```

Utána `dwyt-airouter generate`, `systemctl restart dwyt-litellm`, a futtatón `dwyt-runner config set llm_ask_model kerdes`.

## Modell-leírás a dwyt-nek (0.3)

A 0.3-tól a `generate` a `litellm.yaml` minden nevéhez leírást ír (`model_info.dwyt`): mire való, melyik modell fut mögötte, helyben vagy felhőben, gondolkodással vagy anélkül, és mi válaszol, ha a GPU-gép ki van kapcsolva. A dwyt-futtató (0.7-től) ezt küldi a központnak, a Futtatók oldal ebből mutatja a modelleket.

1. A program frissítése (fent), majd `dwyt-airouter generate` és `systemctl restart dwyt-litellm`.
2. Ha egy név leírását magad akarod megadni, a `models.yaml`-ban a névhez írd: `description: "Kérdések a videókról, alapos válasz."`, majd újra `generate` és újraindítás.

Ellenőrzés:

```bash
KEY=$(sed -n 's/^LITELLM_MASTER_KEY=//p' /etc/dwyt-airouter/litellm.env)
curl -s -H "Authorization: Bearer $KEY" http://127.0.0.1:4000/v1/model/info | python3 -m json.tool | grep -A4 '"dwyt"'
```

## llama-swap

A kipróbált változat a v262. Újabbra váltás:

```bash
V=263   # az új változat száma
curl -sSfL https://github.com/mostlygeek/llama-swap/releases/download/v$V/llama-swap_${V}_linux_amd64.tar.gz \
  | tar xz -C /tmp llama-swap
/tmp/llama-swap -config /etc/dwyt-airouter/generated/llama-swap.yaml -validate
install -m 755 /tmp/llama-swap /opt/dwyt-airouter/bin/llama-swap && systemctl restart dwyt-llama-swap
```

Visszaállás: ugyanígy a v262-vel.

## LiteLLM

A rögzített változat az 1.104.2. Újabbra váltás:

```bash
/opt/dwyt-airouter/litellm/bin/pip install 'litellm[proxy]==ÚJ-VÁLTOZAT'
systemctl restart dwyt-litellm
journalctl -u dwyt-litellm -n 50     # indult-e hiba nélkül
```

Visszaállás: `pip install 'litellm[proxy]==1.104.2'` és újraindítás.
