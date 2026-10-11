# Az AI-router telepítése

Ez a leírás a dwyt AI-router első telepítését írja le egy mindig bekapcsolt Linux-gépre (Debian 12, például Proxmox LXC). Az AI-routeren két szolgáltatás fut:

- **llama-swap:** egyedül ő birtokolja a GPU-t. Sorba állítja a kéréseket, és a GPU-gép ([dwyt-gpu](https://github.com/kzkz22/dwyt-gpu)) konténereit egyenként indítja és állítja le.
- **LiteLLM:** ajánlott, de elhagyható. Stabil modellneveket és felhős tartalékot ad.

A futtató ([dwyt-runner](https://github.com/kzkz22/dwyt-runner)) és a többi kliens (OpenCode, Hermes, Open WebUI) ide kapcsolódik. A frissítés: [frissites.md](frissites.md). A terv: [dwyt-docs, 9. fejezet](https://github.com/kzkz22/dwyt-docs/blob/main/docs/terv.md).

| Elem | Hol | Port |
| --- | --- | --- |
| `dwyt-airouter` program (beállításkészítő, indítók) | `/opt/dwyt-airouter/venv` | – |
| llama-swap (v262) | `/opt/dwyt-airouter/bin/llama-swap`, szolgáltatás: `dwyt-llama-swap` | 8080 |
| LiteLLM (1.104.2) | `/opt/dwyt-airouter/litellm`, szolgáltatás: `dwyt-litellm` | 4000 |
| beállítások | `/etc/dwyt-airouter/models.yaml`, `airouter.env`, `litellm.env`, `generated/` | – |

A portok a `models.yaml` végén átírhatók. Ez akkor kell, ha a gépen már fut egy másik llama-swap vagy LiteLLM, például a régi rendszeré. A nagybetűs részeket (`AI-ROUTER-IP`, `GPU-IP`) cseréld a saját értékeidre.

## 1. Csomagok, felhasználó, program

```bash
apt update && apt install -y git curl ca-certificates python3-venv openssl
useradd --system --home-dir /var/lib/dwyt-airouter --create-home --shell /usr/sbin/nologin airouter
install -d -m 755 /opt/dwyt-airouter/bin /etc/dwyt-airouter /etc/dwyt-airouter/generated

python3 -m venv /opt/dwyt-airouter/venv
/opt/dwyt-airouter/venv/bin/pip install git+https://github.com/kzkz22/dwyt-airouter
ln -sf /opt/dwyt-airouter/venv/bin/dwyt-airouter /usr/local/bin/dwyt-airouter
dwyt-airouter --version
```

## 2. llama-swap

```bash
curl -sSfL https://github.com/mostlygeek/llama-swap/releases/download/v262/llama-swap_262_linux_amd64.tar.gz \
  | tar xz -C /opt/dwyt-airouter/bin llama-swap
/opt/dwyt-airouter/bin/llama-swap -version
```

## 3. LiteLLM (ajánlott)

```bash
python3 -m venv /opt/dwyt-airouter/litellm
/opt/dwyt-airouter/litellm/bin/pip install 'litellm[proxy]==1.104.2'
```

Ha nem kell, a `models.yaml`-ban legyen `litellm: {enabled: false}`. Ekkor felhős modell és tartalék nincs, a stabil nevekből (például `osszefoglalo-helyi`) presetek lesznek.

## 4. A `models.yaml`

```bash
curl -sSfL -o /etc/dwyt-airouter/models.yaml \
  https://raw.githubusercontent.com/kzkz22/dwyt-airouter/main/models.example.yaml
nano /etc/dwyt-airouter/models.yaml
```

A fájl magyarázó megjegyzésekkel indul. A lényeg:

- **`gpu_host`:** hogyan indulnak a GPU-gép konténerei. A `starter` értéke:
  - `docker`: ugyanez a gép;
  - `docker-ssh`: Linux-gép SSH-n;
  - `unraid`: Unraid API.

  Az `address` az a cím, ahol a konténerek portjai elérhetők. A `wake` rész a Wake-on-LAN, ha a GPU-gép magától nem fut.
- **`local_models`:** név, Hugging Face-fájl (`szervezet/repó/fájl.gguf`), a llama-server kapcsolói (`ctx-size`, `temp` …) és a kontextus mérete.
- **`cloud`, `names`:** felhős modellek és a stabil nevek. A saját felvételekhez (`osszefoglalo-helyi`) ne adj felhős tartalékot.

```bash
dwyt-airouter generate
```

Ez az `/etc/dwyt-airouter/generated/` mappába írja a `llama-swap.yaml`-t, a `litellm.yaml`-t, a `models.ini`-t, a `downloads.json`-t és a `ports.env`-et. Hibás `models.yaml` esetén megmondja, melyik sor a rossz, és nem ír semmit. A `models.ini`-t és a `downloads.json`-t vidd át a GPU-gépre (dwyt-gpu leírása, „A modellek”).

## 5. Az indító beállítása

**Unraid:** az Unraid felületén **Settings → Management Access → API Keys**. Itt készíts kulcsot csak **Docker: read + update** joggal.

```bash
install -m 600 -o airouter /dev/null /etc/dwyt-airouter/airouter.env
nano /etc/dwyt-airouter/airouter.env
```

A fájlba egyetlen sor kerül, a névvel együtt (nem csak a kulcs, és nem JSON):

```
UNRAID_API_KEY=a-kulcs-amit-az-unraid-adott
```

Szerkesztővel írd be, ne `echo`-val: így a kulcs nem kerül a parancssori előzményekbe.

**Docker SSH-n át:** az `airouter` felhasználó kulccsal lép be a GPU-gépre. A GPU-gépen a belépő felhasználónak a `docker` csoportban kell lennie.

```bash
install -d -m 700 -o airouter -g airouter /var/lib/dwyt-airouter/.ssh
runuser -u airouter -- ssh-keygen -t ed25519 -N '' -f /var/lib/dwyt-airouter/.ssh/id_ed25519
cat /var/lib/dwyt-airouter/.ssh/id_ed25519.pub     # ezt a GPU-gépen a ~/.ssh/authorized_keys-be
apt install -y docker.io      # csak a docker parancs kell ezen a gépen:
systemctl disable --now docker.service docker.socket
runuser -u airouter -- ssh -o StrictHostKeyChecking=accept-new FELHASZNÁLÓ@GPU-IP docker ps   # kérdés nélkül listáz
```

**Helyi Docker:** `usermod -aG docker airouter`.

**Ébresztés:** a `wake` részben a GPU-gép hálókártyájának MAC-címe és a hálózat broadcast-címe (például `192.168.1.255`). A GPU-gép BIOS-ában és operációs rendszerében a Wake-on-LAN legyen bekapcsolva. Próba kikapcsolt GPU-géppel: `runuser -u airouter -- dwyt-airouter wake`.

**Ellenőrzés:**

```bash
runuser -u airouter -- dwyt-airouter check
```

A GPU-gép elérhető, és mindkét konténer (`dwyt-llama`, `dwyt-whisper`) „leállítva” állapotú. A program az Unraid-kulcsot a `models.yaml` melletti `airouter.env`-ből veszi, ha a környezetben nincs.

## 6. A kulcsok és a szolgáltatások

```bash
install -m 600 -o airouter /dev/null /etc/dwyt-airouter/litellm.env
cat > /etc/dwyt-airouter/litellm.env <<EOF
OPENROUTER_API_KEY=sk-or-...
LITELLM_MASTER_KEY=sk-$(openssl rand -hex 24)
EOF
grep LITELLM_MASTER_KEY /etc/dwyt-airouter/litellm.env     # a klienseknek ez kell

for f in dwyt-llama-swap dwyt-litellm; do
  curl -sSfL -o /etc/systemd/system/$f.service https://raw.githubusercontent.com/kzkz22/dwyt-airouter/main/deploy/$f.service
done
/opt/dwyt-airouter/bin/llama-swap -config /etc/dwyt-airouter/generated/llama-swap.yaml -validate
systemctl daemon-reload
systemctl enable --now dwyt-llama-swap dwyt-litellm      # LiteLLM nélkül: csak dwyt-llama-swap
```

Az OpenRouter Privacy beállításaiban érdemes kizárni azokat a szolgáltatókat, amelyek tanítanak a beküldött adatokon.

## 7. Ellenőrzés: a teljes út

```bash
# llama-swap: elindítja a dwyt-llama konténert, a router betölti a presetet (első alkalommal percekig tarthat)
curl http://localhost:8080/v1/chat/completions -H 'content-type: application/json' \
  -d '{"model":"Qwen3.6-35B-A3B-Gnrl","messages":[{"role":"user","content":"Szia!"}]}'
# LiteLLM, stabil névvel
curl http://localhost:4000/v1/chat/completions -H "authorization: Bearer $(grep -oP '(?<=LITELLM_MASTER_KEY=).*' /etc/dwyt-airouter/litellm.env)" \
  -H 'content-type: application/json' -d '{"model":"osszefoglalo","messages":[{"role":"user","content":"Szia!"}]}'
```

A csere naplója: `journalctl -u dwyt-llama-swap -f`. A webes felület: `http://AI-ROUTER-IP:8080/ui`. A Whisper-workert a futtató első helyi munkája indítja. Közben a naplóban látszik, hogy a `dwyt-llama` leáll, és a `dwyt-whisper` elindul.

## 8. A futtató bekötése

A futtató gépén:

```bash
dwyt-runner config set whisper_url http://AI-ROUTER-IP:8080/upstream/whisper
dwyt-runner config set llm_url http://AI-ROUTER-IP:4000/v1
dwyt-runner config set llm_key A-LITELLM_MASTER_KEY-ÉRTÉKE
dwyt-runner config set llm_public_model osszefoglalo
dwyt-runner config set llm_private_model osszefoglalo-helyi
systemctl restart dwyt-runner      # a képességeket induláskor jelenti be
```

A webes felület Futtatók oldalán megjelenik a „Helyi Whisper”, és a beküldésnél választható.

## A régi rendszer mellett

Ha ugyanazon a GPU-n a régi rendszer is fut, két llama-swap osztozna a GPU-n. Két megoldás van:

- **A régi worker a dwyt llama-swapjába kerül.** Ez az egyszerűbb. A `models.yaml`-ban:

  ```yaml
  extra_containers:
    - entry: yt-transcribe-gpu
      container: yt-transcribe-gpu
      port: 8766
      ttl: 600
  ```

  A régi API `WORKER_URL`-je: `http://127.0.0.1:DWYT-SWAP-PORT/upstream/yt-transcribe-gpu`. A régi `llama.cpp` konténer az `other_gpu_containers` közé kerül, a régi llama-swap pedig leállítható.
- **Két llama-swap egymás mellett.** A dwyt `other_gpu_containers` listájába kerülnek a régi konténerek (`llama.cpp`, `yt-transcribe-gpu`), a régi `unraid.env` `GPU_CONTAINERS` listájába pedig a dwyt konténerei (`dwyt-llama`, `dwyt-whisper`). Így mindkét oldal leállítja a másikét, mielőtt indít. A két sor viszont nem tud egymásról: egyidejű kéréseknél a GPU oda-vissza válthat.

## Hibakeresés

| Jel | Ok és teendő |
| --- | --- |
| „Beállítási hiba: …” | A hiba helye a hibaüzenetben van (például `local_models[1].args`, vagy az `airouter.env` hibás sora). |
| A kérés 502-vel tér vissza, a naplóban „upstream command exited” | Az indító nem tudta elindítani a konténert. Futtasd a `dwyt-airouter check`-et az `airouter` felhasználóval (5. lépés). |
| „Az Unraid API HTTP 401/403” | Rossz a kulcs, vagy nincs Docker update joga. |
| A GPU-gép nem ébred fel | A MAC-cím, a broadcast-cím és a Wake-on-LAN a BIOS-ban. A `wait_s` lehet kevés: lassú gépnél 300 s. |
| A modell betöltése túllépi az időt | A `start_timeout_s` a `models.yaml`-ban (alapból 180 s; ébresztésnél a `wait_s` hozzáadódik). |
| A LiteLLM nem látja az új modellt | A `generate` után `systemctl restart dwyt-litellm`. A llama-swap magától újratölt. |
| LiteLLM nélkül a kliens nem látja a presetneveket | A llama-swap a `/v1/models` listában csak a `llama-server` bejegyzést mutatja; a presetnevet kézzel add meg a kliensben. |
