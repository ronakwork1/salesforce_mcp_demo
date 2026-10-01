"""Thin read-only Salesforce REST client. Exposes GET only: writes are impossible by construction."""
import asyncio

import httpx

from . import soql
from .auth import SalesforceAuth


def _strip(value):
    """Recursively drop Salesforce 'attributes' metadata (internal record URLs) from records."""
    if isinstance(value, dict):
        return {k: _strip(v) for k, v in value.items() if k != "attributes"}
    return value


class SalesforceError(RuntimeError):
    pass


class SalesforceClient:
    def __init__(self, auth: SalesforceAuth, api_version: str = "v62.0", transport: httpx.AsyncBaseTransport | None = None):
        self._auth = auth
        self._base = f"{auth.instance_url}/services/data/{api_version}"
        self._transport = transport

    async def _get(self, path: str, params: dict | None = None) -> dict:
        refreshed = False
        for attempt in range(3):
            token = await self._auth.token(force_refresh=refreshed)
            async with httpx.AsyncClient(timeout=20, transport=self._transport) as http:
                r = await http.get(f"{self._base}{path}", params=params, headers={"Authorization": f"Bearer {token}"})
            if r.status_code == 401 and not refreshed:
                refreshed = True  # one token refresh, then give up
                continue
            if r.status_code in (429, 503) and attempt < 2:
                await asyncio.sleep(0.5 * 2**attempt)
                continue
            if r.status_code != 200:
                raise SalesforceError(f"Salesforce API error (HTTP {r.status_code}).")
            return r.json()
        raise SalesforceError("Salesforce API unavailable after retries.")

    async def query(self, query_text: str) -> dict:
        """Run a raw SOQL query. Returns {'records': [...], 'total_size': n}. total_size is the number of
        rows returned (or the COUNT() value), not the number of rows that exist beyond a LIMIT."""
        data = await self._get("/query", {"q": query_text})
        records = [_strip(rec) for rec in data.get("records", [])]
        return {"records": records, "total_size": data.get("totalSize", len(records))}

    async def query_limited(self, fields: tuple[str, ...], sobject: str, where: list[str], order: str | None,
                            limit: int) -> dict:
        """Fetch up to `limit` rows. Asks for limit+1 so we can tell whether more rows exist."""
        result = await self.query(soql.build(fields, sobject, where, order, limit + 1))
        records = result["records"]
        return {"records": records[:limit], "returned": min(len(records), limit), "truncated": len(records) > limit}
