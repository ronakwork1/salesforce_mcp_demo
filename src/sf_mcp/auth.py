"""Salesforce OAuth 2.0. Client Credentials for dev; JWT Bearer slots in behind the same interface."""
import os
from typing import Protocol

import httpx


class AuthError(RuntimeError):
    pass


class SalesforceAuth(Protocol):
    instance_url: str

    async def token(self, force_refresh: bool = False) -> str: ...


class ClientCredentialsAuth:
    def __init__(self, instance_url: str, client_id: str, client_secret: str):
        self.instance_url = instance_url.rstrip("/")
        self._id, self._secret = client_id, client_secret
        self._token: str | None = None

    @classmethod
    def from_env(cls) -> "ClientCredentialsAuth":
        missing = [k for k in ("SF_INSTANCE_URL", "SF_CLIENT_ID", "SF_CLIENT_SECRET") if not os.environ.get(k)]
        if missing:
            raise AuthError(f"Missing environment variables: {', '.join(missing)} (see .env.example)")
        return cls(os.environ["SF_INSTANCE_URL"], os.environ["SF_CLIENT_ID"], os.environ["SF_CLIENT_SECRET"])

    async def token(self, force_refresh: bool = False) -> str:
        if self._token and not force_refresh:
            return self._token
        async with httpx.AsyncClient(timeout=15) as http:
            r = await http.post(
                f"{self.instance_url}/services/oauth2/token",
                data={"grant_type": "client_credentials", "client_id": self._id, "client_secret": self._secret},
            )
        if r.status_code != 200:
            # Never echo the response body verbatim; it can contain org details.
            raise AuthError(f"Salesforce token request failed (HTTP {r.status_code}). Check the External Client App and its Run As user.")
        self._token = r.json()["access_token"]
        return self._token
