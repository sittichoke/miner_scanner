# rest_client.py
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import json


class RestClient:
    """
    Very small wrapper around `requests` with:
        • automatic JSON encoding
        • Bearer-token auth
        • retry   : 3 × on 502/503/504 with back-off
        • timeout : 5 s (change via ctor)
    """

    def __init__(
        self,
        base_url: str,
        api_key: Optional[str] = None,
        timeout: int = 5,
        retries: int = 3,
        backoff: float = 0.3,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        if api_key:
            self.session.headers.update({"Authorization": f"Basic {api_key}"})

        retry_cfg = Retry(
            total=retries,
            backoff_factor=backoff,
            status_forcelist=[502, 503, 504],
            allowed_methods=["POST"],
        )
        adapter = HTTPAdapter(max_retries=retry_cfg)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    def post(self, path: str, payload: Dict[str, Any]) -> None:
        url = self.base_url
        payloadStr = json.dumps(payload,indent=2)
        # print(f'payloadStr: {payloadStr}')
        if path != "":
            url = f"{self.base_url}/{path.lstrip('/')}"
            
        r = self.session.post(url, json=payload, timeout=self.timeout)
        try:
            r.raise_for_status()
        except requests.HTTPError as exc:
            # Log – but do **not** raise further so the scanner keeps running
            logging.warning("REST push failed %s → %s – %s", payload.get("ip"), url, exc)
