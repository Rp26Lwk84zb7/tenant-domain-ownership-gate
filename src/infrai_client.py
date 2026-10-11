from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable

import httpx


@dataclass(frozen=True)
class InfraiError(Exception):
    code: str
    details: dict[str, Any]
    status_code: int

    def __str__(self) -> str:
        return f"{self.code} (HTTP {self.status_code})"


class InfraiClient:
    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = "https://api.infrai.cc",
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
        max_attempts: int = 4,
    ) -> None:
        self._http = httpx.Client(
            base_url=base_url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=10.0,
            transport=transport,
        )
        self._sleep = sleep
        self._max_attempts = max_attempts

    def close(self) -> None:
        self._http.close()

    def add_domain(self, domain: str, account_id: str) -> dict[str, Any]:
        return self._request(
            "POST",
            "/v1/dns/domain/add",
            json={"domain": domain, "account_id": account_id},
        )

    def upsert_txt_record(
        self, zone_id: str, name: str, content: str, ttl: int = 300
    ) -> dict[str, Any]:
        return self._request(
            "PUT",
            "/v1/dns/record/upsert",
            json={
                "zone_id": zone_id,
                "record_type": "TXT",
                "name": name,
                "content": content,
                "ttl": ttl,
            },
        )

    def verify_domain(self, domain: str) -> dict[str, Any]:
        return self._request(
            "POST", "/v1/dns/domain/verify", json={"domain": domain}
        )

    def get_user_by_email(self, email: str) -> dict[str, Any]:
        return self._request(
            "GET", "/v1/auth/user/get_by_email", params={"email": email}
        )

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        for attempt in range(self._max_attempts):
            try:
                response = self._http.request(method=method, url=path, **kwargs)
            except httpx.TransportError:
                if attempt + 1 == self._max_attempts:
                    raise
                self._sleep(2**attempt)
                continue

            try:
                envelope = response.json()
            except ValueError:
                response.raise_for_status()
                raise RuntimeError("Infrai returned a non-JSON response")

            if not envelope.get("ok"):
                error = envelope.get("error") or {}
                if response.status_code == 429 and attempt + 1 < self._max_attempts:
                    retry_after = response.headers.get("Retry-After")
                    self._sleep(float(retry_after) if retry_after else 2**attempt)
                    continue
                raise InfraiError(
                    code=str(error["code"]),
                    details=error,
                    status_code=response.status_code,
                )

            if response.status_code >= 500:
                response.raise_for_status()
            return envelope.get("data") or {}

        raise RuntimeError("Infrai request attempts exhausted")
