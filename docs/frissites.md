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
