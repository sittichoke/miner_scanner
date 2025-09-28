# rest_client.py
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import json
from datetime import datetime


class RestClient:
    """
    Small wrapper around `requests` with:
      • JSON encoding
      • Optional Basic/Bearer auth (header already set by caller)
      • Retries (502/503/504)
      • Batch sending for payloads that include {"results": [...]}
    """

    def __init__(
        self,
        base_url: str,
        api_key: Optional[str] = None,
        timeout: int = 30,
        retries: int = 3,
        backoff: float = 0.3,
        batch_size: int = 1,          # NEW: how many items per POST
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.batch_size = max(1, int(batch_size))

        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        if api_key:
            # NOTE: this sends a Basic header as provided in api_key.
            # If you need real Basic auth (username:password -> base64),
            # set `self.session.auth = (user, pass_)` in __init__ instead.
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
        """
        If payload has a list under 'results', send in batches of self.batch_size.
        Otherwise, send payload as-is.
        """
        url = f"{self.base_url}/{path.lstrip('/')}" if path else self.base_url

        # If there's no 'results' list, single POST
        results = payload.get("results") if isinstance(payload, dict) else None
        if not isinstance(results, list):
            self._post_once(url, payload)
            return

        if len(results) == 0:
            return  # nothing to send

        # Batch the list
        for i in range(0, len(results), self.batch_size):
            chunk = results[i : i + self.batch_size]
            batched_payload = dict(payload)
            batched_payload["results"] = chunk
            self._post_once(url, batched_payload)
            # print status until done
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(f"[{now}] [RestClient] POST {url} - sent {min(i + self.batch_size, len(results))}/{len(results)} items")

    # ------------------------------------------------------------------ #
    # Internal helper
    # ------------------------------------------------------------------ #
    def _post_once(self, url: str, body: Dict[str, Any]) -> None:
        # print body ip for logging

        try:
            # payloadStr = json.dumps(body,indent=2)
            # print(f'payloadStr: {payloadStr}')
            r = self.session.post(url, json=body, timeout=self.timeout)
            r.raise_for_status()
        except requests.HTTPError as exc:
            logging.warning(
                "REST push failed for ip=%s → %s – %s",
                _safe_ip(body),
                url,
                exc,
            )
        except Exception as exc:
            logging.warning(
                "REST push error for ip=%s → %s – %s",
                _safe_ip(body),
                url,
                exc,
            )
    def post_device_online(self, path: str, payload: Dict[str, Any]) -> None:
        # ex. req body: {"results": [{"ip":"192.168.x.y","online": "true""]}]}"

        url = f"{self.base_url}/{path.lstrip('/')}" if path else self.base_url
        # reduce object fields in results to ip and online only
        # if isinstance(payload, dict) and isinstance(payload.get("results"), list):
        #     for item in payload["results"]:
        #         if isinstance(item, dict):
        #             item_keys = list(item.keys())
        #             for key in item_keys:
        #                 if key not in ["ip", "online"]:
        #                     del item[key]
        # create new payload with reduced fields
        new_payload = {"results": [{"ip": item.get("ip"), "online": item.get("online")} for item in payload["results"] if isinstance(item, dict)]}
        # payloadStr = json.dumps(new_payload,indent=2) 
        # print(f'payloadStr: {payloadStr}')
        # try:
        #     r = self.session.post(url, json=new_payload, timeout=self.timeout)
        #     r.raise_for_status()
        # except requests.HTTPError as exc:
        #     logging.warning(
        #         "REST push failed for ip=%s → %s – %s",
        #         _safe_ip(payload),
        #         url,
        #         exc,
        #     )
        # except Exception as exc:
        #     logging.warning(
        #         "REST push error for ip=%s → %s – %s",
        #         _safe_ip(payload),
        #         url,
        #         exc,
        #     )
        # Batch the list
        results = new_payload.get("results") if isinstance(new_payload, dict) else None
        if not isinstance(results, list):
            self._post_once(url, new_payload)
            return

        if len(results) == 0:
            return  # nothing to send
        for i in range(0, len(results), self.batch_size):
            chunk = results[i : i + self.batch_size]
            batched_payload = dict(new_payload)
            batched_payload["results"] = chunk
            print(json.dumps(batched_payload,indent=2) )
            self._post_once(url, batched_payload)
            # print status until done
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(f"[{now}] [RestClient] POST {url} - sent {min(i + self.batch_size, len(results))}/{len(results)} items")

def _safe_ip(body: Dict[str, Any]) -> str:
    # Try to pull an IP field for logging (supports both single record and results[])
    if isinstance(body, dict):
        if isinstance(body.get("ip"), str):
            return body["ip"]
        if isinstance(body.get("results"), list) and body["results"]:
            first = body["results"][0]
            if isinstance(first, dict) and isinstance(first.get("ip"), str):
                return first["ip"]
    return "?"
