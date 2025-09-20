# collector.py
from __future__ import annotations

import datetime
import logging
from typing import TYPE_CHECKING, Optional,List,Dict

from pydantic import BaseModel, Field

from antminer.base import BaseClient
from rate_units import convert_from_ghs
if TYPE_CHECKING:
    from db import DB
    from rest_client import RestClient


class CollectorData(BaseModel):
    collected_at: datetime.datetime = Field(default_factory=datetime.datetime.utcnow)
    ip: str
    model: Optional[str] = Field(default=None, serialization_alias="brand")
    hashrate_5s: Optional[float] = None
    hashrate_avg: Optional[float] = Field(default=None, serialization_alias="hashrate")
    temperature: Optional[float] = Field(default=None, serialization_alias="temperature")
    worker_name: Optional[str] = Field(default=None, serialization_alias="worker_name")
    pool: Optional[str] = Field(default=None, serialization_alias="pool")
    owner_name: Optional[str] = Field(default=None, serialization_alias="owner_name")
    is_online: bool = Field(default=True, serialization_alias="online")
    total_rate_ideal: Optional[float] = None
    miner_count: Optional[int] = None
    frequency: Optional[int] = None
    fan_num: Optional[int] = None
    fans: Optional[List[int]] = None                # e.g. [3450, 3430, 3450, 3450]

    temps: Optional[Dict[str, int]] = None          # flexible mapping for temp2_1, temp_in_chip_1, temp_max, etc.
                                                    # e.g. {"temp2_1": 78, "temp_in_chip_1": 56, "temp_max": 78}

    chain_hw: Optional[List[int]] = None            # e.g. [4756, 2218, 7553]
    chain_avg_hashrate: Optional[List[str]] = None  # e.g. ["5463.34 MH/s", "5482.70 MH/s", "5432.49 MH/s"]
    card: Optional[Dict] = None 
    temp_max: Optional[int] = None

class Collector:
    """
    Normalises raw miner payloads and forwards them to:
        • an optional DB backend
        • an optional REST endpoint (batch format: {"results": [...]})
    """

    def __init__(
        self,
        db: Optional["DB"] = None,
        rest_client: Optional["RestClient"] = None,
        rest_path: str = "",
    ) -> None:
        self.db = db
        self.rest = rest_client
        self.rest_path = rest_path

    # ------------------------------------------------------------------ #
    # Public
    # ------------------------------------------------------------------ #

    def collect(self, miner: BaseClient) -> None:
        try:
            record = self._extract_data(
                miner.host, miner.stats(), miner.version()
            )
        except Exception as exc:
            record = CollectorData(ip=miner.host, is_online=False)
            logging.warning("[Collector] %s marked offline – %s", miner.host, exc)

        self._persist(record)

    def collect_all(self, miners: list[BaseClient]) -> None:
        records = []
        for miner in miners:
            if miner.host == '192.168.23.52':
                print(f'Collecting data from miner: {miner.host}')
            print(f'Collecting data from miner: {miner.host}')
            try:
                record = self._extract_data(
                    miner.host, miner.stats(), miner.version(),miner.pools()
                )
            except Exception as exc:
                record = CollectorData(ip=miner.host, is_online=False)
                logging.warning("[Collector] %s marked offline – %s", miner.host, exc)
      
            records.append(record)
    
        self._persist_all(records)

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    def _persist(self, record: CollectorData) -> None:
        if self.db:
            self.db.insert(record)
        if self.rest:
            self.rest.post(self.rest_path, _format_result(record, wrap=False))
        logging.info("[Collector] stored & pushed %s", record.ip)

    def _persist_all(self, records: list[CollectorData]) -> None:
        for record in records:
            if self.db:
                self.db.insert(record)

        if self.rest:
            payload = {"results": [_format_result(r, wrap=False) for r in records]}
            self.rest.post(self.rest_path, payload)

        logging.info("[Collector] stored & pushed batch (%d)", len(records))

    @staticmethod
    def _extract_data(ip: str, stats: dict, version: dict, pools: list[dict]) -> CollectorData:
        # Expect cgminer/bmminer-like payloads where stats["STATS"][1] holds summary
        summary = (stats or {}).get("STATS", [{}])
        summary = summary[1] if len(summary) > 1 else (summary[0] if summary else {})
        pool_stat = pools[0] if pools else {}
        # if version is not None:
        #     if version.get("model").lower().endswith("s21"):
        #         print(f'stats: {stats}')
            
        # ---- Normalize dynamic fields ----
        # Fans: fan1..fanN → fans: List[int]
        fan_num = _to_i(summary.get("fan_num")) or 0
        fans: list[int] = []
        for i in range(1, fan_num + 1):
            key = f"fan{i}"
            if key in summary:
                val = _to_i(summary.get(key))
                if val is not None:
                    fans.append(val)

        # Temps: only temp2_x, temp_in_chip_x, temp_out_chip_x → temps: Dict[str, int]
        card = {} # cards temperature list
        # temps = {}
        for k, v in summary.items():
            if not isinstance(k, str):
                continue
            if (
                k.startswith("temp2_")       # e.g. temp2_1, temp2_2, temp2_3
                or k.startswith("temp_in_chip_")   # e.g. temp_in_chip_1..3
                or k.startswith("temp_out_chip_")  # e.g. temp_out_chip_1..3
                or k.startswith("chain_rate")
                or k.startswith("chain_acn")
            ):
                # iv = _to_i(v)
                # if iv is not None:
                    # temps[k] = iv
                if card.get(k[-1]) is None:
                    card[k[-1]] = {
                        "temp":None,
                        "temp_in":None,
                        "temp_out":None,
                        "hashrate":None,
                        "chain_acn":None,
                    }
                if k.startswith("temp2_"):
                    iv = _to_i(v)
                    if iv is not None:
                        card[k[-1]]["temp"] =  iv
                elif k.startswith("temp_in_chip_"):
                    card[k[-1]]["temp_in"] = v    
                elif k.startswith("temp_out_chip_"):
                    card[k[-1]]["temp_out"] = v
                elif k.startswith("chain_rate"):
                    card[k[-1]]["hashrate"] = _to_f(v)
                elif k.startswith("chain_acn"):
                    card[k[-1]]["chain_acn"] = _to_i(v) 

        # Chains HW errors: chain_hw1..chain_hwN → chain_hw: List[int]
        chain_hw: list[int] = []
        for i in range(1, 128):  # safe upper bound
            key = f"chain_hw{i}"
            if key not in summary:
                if i > 1:
                    break
                continue
            iv = _to_i(summary.get(key))
            if iv is not None:
                chain_hw.append(iv)

        # Chains avg hashrate: support both "chain_avg_hashrate1" and "CHAIN AVG HASHRATE1"
        chain_avg_hashrate: list[str] = []
        for i in range(1, 128):
            val = summary.get(f"chain_avg_hashrate{i}")
            if val is None:
                val = summary.get(f"CHAIN AVG HASHRATE{i}")
            if val is None:
                if i > 1:
                    break
                continue
            chain_avg_hashrate.append(str(val))

        # Choose a representative temperature for the top-level "temperature" field
        primary_temp = (
            summary.get("temp_max")
            or summary.get("temp2")
            or summary.get("temp")
        )
        

        return CollectorData(
            ip=ip,
            model=version.get("model") if version and version.get("model") is not None else None,
            hashrate_avg=_to_f(summary.get("GHS av") or summary.get("GHS_av") or summary.get("rate_30m")) if summary else None,
            temperature=_to_f(primary_temp) if primary_temp is not None else None,
            worker_name=pool_stat.get("workername") if pool_stat and pool_stat.get("workername") is not None else None,
            pool=pool_stat.get("url") if pool_stat and pool_stat.get("url") is not None else None,
            miner_count=_to_i(summary.get("miner_count")) if summary and summary.get("miner_count") is not None else None,
            frequency=_to_i(summary.get("frequency")) if summary and summary.get("frequency") is not None else None,
            fan_num=fan_num if fan_num is not None else None,
            fans=fans if fans else None,
            card=card if card else None,
            chain_hw=chain_hw if chain_hw else None,
            chain_avg_hashrate=chain_avg_hashrate if chain_avg_hashrate else None,
            temp_max=_to_i(summary.get("temp_max")) if summary and summary.get("temp_max") is not None else None,
            total_rate_ideal=_to_f(summary.get("total_rateideal")) if summary and summary.get("total_rateideal") is not None else None,
        )


def _to_f(v) -> Optional[float]:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None
def _to_i(v):
    try:
        if v is None:
            return None
        if isinstance(v, str):
            v = v.strip()
        return int(float(v))
    except Exception:
        return None

def _format_result(r: CollectorData, wrap=True) -> dict:
    result = {
        "ip": r.ip,
        "brand": r.model or "AntminerHttpCgi",  # or dynamically detect brand
        "online": r.is_online,
        # "hashrate": (
        #     f"{r.hashrate_avg:.2f} TH/s" if r.hashrate_avg and r.hashrate_avg > 1000
        #     else f"{r.hashrate_avg:.2f} MH/s" if r.hashrate_avg
        #     else None
        # ),
        # "temperature": f"{int(r.temperature)} °C" if r.temperature is not None else None,
        # "card": r.card if r.card else None,
        "worker_name": r.worker_name,
        "pool": r.pool,
    }

    # ─── Extra fields from extended CollectorData ───────────────────
    if r.card is not None:
        # result["card"] = r.card
        # convert all hashrate values in card from GH/s to preferred unit
        
        # for card_id, card_info in r.card.items():
        #     if card_info.get("hashrate") is not None:
        #         val, unit = convert_from_ghs(card_info["hashrate"], r.model)
        #         card_info["hashrate"] = f"{val:.2f} {unit}"
        # result["card"] = r.card
        new_card = {}
        for card_id, card_info in r.card.items():
            new_card[card_id] = card_info.copy()
            if card_info.get("hashrate") is not None:
                val, unit = convert_from_ghs(card_info["hashrate"], r.model)
                new_card[card_id]["hashrate"] = f"{val:.2f} {unit}"
        result["card"] = new_card
        

    if r.hashrate_avg is not None:
        # val, unit = convert_from_ghs(r.hashrate_avg, r.model)
        # result["hashrate"] = f"{val:.2f} {unit}"
        # use summary from r.card if available
        if r.card:
            hashrates = [c.get("hashrate") for c in r.card.values() if c.get("hashrate") is not None]
            if hashrates:
                total_ghs = sum(hashrates)
                val, unit = convert_from_ghs(total_ghs, r.model)
                result["hashrate"] = f"{val:.2f} {unit}"
            else:
                result["hashrate"] = None

    if r.total_rate_ideal is not None:
        val, unit = convert_from_ghs(r.total_rate_ideal, r.model)
        result["total_rate_ideal"] = f"{val:.2f} {unit}"

    if r.miner_count is not None:
        result["miner_count"] = r.miner_count

    if r.frequency is not None:
        result["frequency"] = f"{r.frequency}"

    if r.fan_num is not None:
        result["fan_num"] = r.fan_num

    if r.fans:
        # e.g. {"fan1": 3450, "fan2": 3430, ...}
        result["fans"] = {f"fan{i+1}": speed for i, speed in enumerate(r.fans)}

    # if r.temps:
    #     # already dict of all temp values (temp2_1, temp_in_chip_1, temp_max, etc.)
    #     result["temps"] = {k: f"{v} °C" for k, v in r.temps.items()}

    if r.chain_hw:
        result["chain_hw"] = r.chain_hw  # list of ints

    if r.chain_avg_hashrate:
        result["chain_avg_hashrate"] = r.chain_avg_hashrate  # list of strings, already formatted
    if r.temp_max is not None:
        result["temp_max"] = r.temp_max

    return {"results": [result]} if wrap else result
