from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass

import aiohttp

DEVICE_CODE_URL: str = "https://github.com/login/device/code"
ACCESS_TOKEN_URL: str = "https://github.com/login/oauth/access_token"
USER_PROFILE_URL: str = "https://api.github.com/user"
VERIFICATION_URI: str = "https://github.com/login/device"
DEVICE_SCOPE: str = "repo"
TOKEN_CREATION_URL: str = (
    "https://github.com/settings/tokens/new?scopes=repo&description=Bot+Fleet+Orchestrator"
)
_REQUEST_TIMEOUT: aiohttp.ClientTimeout = aiohttp.ClientTimeout(total=15)


class GitHubOAuthError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class DeviceAuthorization:
    device_code: str
    user_code: str
    verification_uri: str
    expires_in: int
    interval: int


@dataclass(frozen=True, slots=True)
class GitHubIdentity:
    username: str
    token: str


async def request_device_authorization(client_id: str) -> DeviceAuthorization:
    async with (
        aiohttp.ClientSession() as session,
        session.post(
            DEVICE_CODE_URL,
            data={"client_id": client_id, "scope": DEVICE_SCOPE},
            headers={"Accept": "application/json"},
            timeout=_REQUEST_TIMEOUT,
        ) as response,
    ):
        payload = await response.json(content_type=None)

    if "device_code" not in payload:
        raise GitHubOAuthError(payload.get("error_description", "device authorization request failed"))

    return DeviceAuthorization(
        device_code=payload["device_code"],
        user_code=payload["user_code"],
        verification_uri=payload.get("verification_uri", VERIFICATION_URI),
        expires_in=int(payload.get("expires_in", 900)),
        interval=int(payload.get("interval", 5)),
    )


async def poll_for_access_token(client_id: str, authorization: DeviceAuthorization) -> str:
    deadline = time.monotonic() + authorization.expires_in
    interval = max(authorization.interval, 5)

    async with aiohttp.ClientSession() as session:
        while time.monotonic() < deadline:
            await asyncio.sleep(interval)
            async with session.post(
                ACCESS_TOKEN_URL,
                data={
                    "client_id": client_id,
                    "device_code": authorization.device_code,
                    "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                },
                headers={"Accept": "application/json"},
                timeout=_REQUEST_TIMEOUT,
            ) as response:
                payload = await response.json(content_type=None)

            if "access_token" in payload:
                return payload["access_token"]

            error = payload.get("error")
            if error == "authorization_pending":
                continue
            if error == "slow_down":
                interval += 5
                continue
            if error == "expired_token":
                raise GitHubOAuthError("expired")
            if error == "access_denied":
                raise GitHubOAuthError("denied")
            raise GitHubOAuthError(payload.get("error_description", error or "device flow failed"))

    raise GitHubOAuthError("expired")


async def fetch_identity(token: str) -> GitHubIdentity:
    async with (
        aiohttp.ClientSession() as session,
        session.get(
            USER_PROFILE_URL,
            headers={"Authorization": f"token {token}", "Accept": "application/vnd.github+json"},
            timeout=_REQUEST_TIMEOUT,
        ) as response,
    ):
        if response.status != 200:
            raise GitHubOAuthError(f"github returned {response.status}")
        payload = await response.json(content_type=None)

    username = payload.get("login")
    if not username:
        raise GitHubOAuthError("github did not return a username")
    return GitHubIdentity(username=username, token=token)
