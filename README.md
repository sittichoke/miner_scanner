# ASIC Miner Monitor

A small, modular Python stack for discovering **Bitmain Antminers** on your local network, collecting telemetry (hash‑rate, temperature, pool, etc.), persisting it to a database **and** streaming it to an external REST endpoint.
An optional FastAPI service lets you query and control individual miners.

---

\## Features

| Module                  | Purpose                                                 |
| ----------------------- | ------------------------------------------------------- |
| **`antminer.base`**     | Thin CGMiner/BMMiner JSON‑RPC client (TCP 4028)         |
| **`antminer.discover`** | Parallel subnet scanner (`/24` TCP sweeps)              |
| **`collector`**         | Normalises raw stats → `CollectorData` model            |
| **`db`**                | Lightweight SQLite sink (swap for Postgres / TSDB)      |
| **`rest_client`**       | Optional fire‑and‑forget push to external API           |
| **`main_scanner.py`**   | Headless loop – discover → collect → persist/push       |
| **`antminer_api.py`**   | FastAPI micro‑service (summary / reset / reboot / pool) |

---

\## Quick Start

```bash
python -m venv .venv
source .venv/Scripts/activate
pip install -r requirements.txt     # see below

# Scan a single subnet & write to SQLite
export SUBNET="192.168.2.*"
python main_scanner.py

# Launch the REST control API
uvicorn antminer_api:app --host 0.0.0.0 --port 8000 --reload
```

\### Environment Variables

| Variable        | Default       | Description                                    |
| --------------- | ------------- | ---------------------------------------------- |
| `SUBNET`        | `192.168.0.*` | IPv4 subnet to sweep (`CIDR` or `192.168.2.*`) |
| `SCAN_INTERVAL` | `30`          | Seconds between scans (set in code)            |
| `ENABLE_DB`     | `true`        | Disable SQLite sink if set to `false`          |
| `API_URL`       | *empty*       | Remote endpoint that receives JSON records     |
| `API_KEY`       | *empty*       | Bearer token sent in `Authorization` header    |
| `API_TIMEOUT`   | `5`           | Seconds before remote push times out           |

\### Requirements

* Python 3.10+
* For the control API: `fastapi`, `uvicorn[standard]`, `pydantic`
  *(see `requirements.txt` or run `pip install -r requirements.txt`)*

---

\## Architecture & Data Flow

```text
+---------------------------+        +---------------------------+
|  main_scanner (per /24)   |        |   antminer_api (FastAPI)  |
|                           |        |  • GET /summary           |
| 1️⃣ discover subnet ───────┐        |  • POST /reset            |
| 2️⃣ collector.collect      |        |  • POST /reboot           |
|    ├─ SQLite sink (db)    |        |  • POST /pool             |
|    └─ REST push (optional)|        +---------------------------+
|                           |
+---------------------------+
```

* **High availability strategy** – run *one* scanner per subnet (systemd/Docker) and point them all at the same central REST receiver or time‑series database.
* **Scaling** – scanner uses a thread‑pool; adjust `MAX_WORKERS` for large /22 farms.

---

\## API Reference (FastAPI)

| Method | Path                            | Description                |
| ------ | ------------------------------- | -------------------------- |
| `GET`  | `/miners/{ip}/{worker}/summary` | Live hashrate, temp, pools |
| `POST` | `/miners/{ip}/{worker}/reset`   | Soft‑reset cgminer/bmminer |
| `POST` | `/miners/{ip}/{worker}/reboot`  | Full device reboot         |
| `POST` | `/miners/{ip}/{worker}/pool`    | Replace pool URL/user/pass |

Open `http://localhost:8000/docs` for interactive Swagger UI.

---

\## Docker Compose (example)

```yaml
version: "3.9"
services:
  scanner-192-168-2:
    build: .  # or image: YOUR_IMAGE
    command: python main_scanner.py --subnet 192.168.2.*
    environment:
      ENABLE_DB: "false"
      API_URL: "http://api:8000/miner-stats"
    restart: unless-stopped

  api:
    build: .
    command: uvicorn antminer_api:app --host 0.0.0.0 --port 8000
    ports: ["8000:8000"]
    restart: unless-stopped
```

