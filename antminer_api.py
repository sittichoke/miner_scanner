# antminer_api.py – FastAPI service for controlling & monitoring Antminers
"""A tiny FastAPI wrapper around the Antminer CGMiner/BMMiner JSON‑RPC API.

Endpoints
---------
GET  /miners/{ip}/{worker}/summary   – Current stats (hashrate, temp, pools …)
POST /miners/{ip}/{worker}/reset     – Soft reset (clear faults, restart cgminer)
POST /miners/{ip}/{worker}/reboot    – Hardware reboot (power‑cycle)
POST /miners/{ip}/{worker}/pool      – Replace pool credentials (URL, user, pw)

Run with:
    pip install fastapi uvicorn[standard] pydantic requests
    uvicorn antminer_api:app --host 0.0.0.0 --port 8000 --reload

Notes
-----
* Uses blocking I/O – fine for a handful of local miners. For hundreds, wrap
  calls in `run_in_threadpool()` or migrate to `anyio`/`asyncio` sockets.
* Antminer API commands are vendor‑specific. "reset", "restart", "addpool"
  work on most CGMiner/BMMiner builds shipped in the last ~7 years.
* Worker‑name filtering is *best‑effort*; some firmwares omit it from stats.
"""

from __future__ import annotations

import socket
from typing import Optional

from fastapi import Body, FastAPI, HTTPException, status
from pydantic import BaseModel, Field, IPvAnyAddress

from antminer.base import BaseClient

app = FastAPI(title="Antminer Control API", version="0.1.0")


# ──────────────────────────────────────────────────────────────────────────────
# Models
# ──────────────────────────────────────────────────────────────────────────────
class PoolSettings(BaseModel):
    url: str = Field(..., example="stratum+tcp://pool.example.com:3333")
    username: str = Field(..., example="myuser.worker1")
    password: str = Field(..., example="x")


class MinerSummary(BaseModel):
    ip: IPvAnyAddress
    worker: str
    model: Optional[str] = None
    firmware: Optional[str] = None
    hashrate_5s: Optional[float] = None  # GH/s
    hashrate_avg: Optional[float] = None  # GH/s (15m)
    temperature: Optional[float] = None   # °C
    pools: list[str] = []


# ──────────────────────────────────────────────────────────────────────────────
# Helper layer – minimal defensive parsing around the raw JSON‑RPC output
# ──────────────────────────────────────────────────────────────────────────────

def build_client(ip: str) -> BaseClient:
    """Validate the IP string and return a BaseClient bound to it."""
    try:
        socket.inet_aton(ip)
    except OSError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid IP address")
    return BaseClient(ip)


def parse_summary(stats: list[dict], version: dict, worker: str, ip: str) -> MinerSummary:
    summary_block = next((s for s in stats if s.get("TYPE", "").lower() in {"summary", "stats"}), {})
    pool_blocks = [s for s in stats if s.get("TYPE") == "pool"]

    # If a worker name was supplied, filter pools by Worker field (best‑effort)
    if worker:
        pool_blocks = [p for p in pool_blocks if p.get("Worker") == worker]
        if not pool_blocks:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Worker not found in miner stats")

    pools = [p.get("URL", "?") for p in pool_blocks]

    return MinerSummary(
        ip=ip,
        worker=worker,
        model=version.get("model"),
        firmware=version.get("miner", {}).get("version"),
        hashrate_5s=_to_f(summary_block.get("GHS 5s")),
        hashrate_avg=_to_f(summary_block.get("GHS av")),
        temperature=_to_f(summary_block.get("temp2") or summary_block.get("temp")),
        pools=pools,
    )


def _to_f(v) -> Optional[float]:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


# ──────────────────────────────────────────────────────────────────────────────
# Routes
# ──────────────────────────────────────────────────────────────────────────────

@app.get("/miners/{ip}/{worker}/summary", response_model=MinerSummary)
async def get_summary(ip: str, worker: str):
    """Return current performance/temperature metrics for a given worker."""
    client = build_client(ip)
    try:
        stats = client.stats()      # list of dicts
        version = client.version()  # dict
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))

    return parse_summary(stats, version, worker, ip)


@app.post("/miners/{ip}/{worker}/reset", status_code=status.HTTP_202_ACCEPTED)
async def reset_miner(ip: str, worker: str):
    """Soft reset the cgminer/bmminer process."""
    client = build_client(ip)
    try:
        resp = client.command("reset")
        return {"status": "reset issued", "response": resp}
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))


@app.post("/miners/{ip}/{worker}/reboot", status_code=status.HTTP_202_ACCEPTED)
async def reboot_miner(ip: str, worker: str):
    """Reboot the whole device (same as pressing the physical reset button)."""
    client = build_client(ip)
    try:
        resp = client.command("restart")  # older firmwares use "reboot"
        return {"status": "reboot issued", "response": resp}
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))


@app.post("/miners/{ip}/{worker}/pool", status_code=status.HTTP_202_ACCEPTED)
async def set_pool(ip: str, worker: str, settings: PoolSettings = Body(...)):
    """Replace the current pool credentials with a new (url, user, pass) tuple.

    On most miners you *cannot* change just one field; you must provide the full
    trio. The command below deletes the existing pool #0 then adds a new one.
    """
    client = build_client(ip)
    try:
        # 1) Remove current pool 0 ("removepool,0")
        client.command("removepool", "0")
        # 2) Add replacement ("addpool,url,user,pass")
        client.command("addpool", f"{settings.url},{settings.username},{settings.password}")
        return {"status": "pool updated", "new_pool": settings.dict()}
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))


# ──────────────────────────────────────────────────────────────────────────────
# Development entry‑point – `python antminer_api.py`
# ──────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn

    uvicorn.run("antminer_api:app", host="0.0.0.0", port=8000, reload=True)
