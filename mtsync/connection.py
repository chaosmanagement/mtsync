import json
from typing import Any, Callable, Dict

import aiohttp
from rich.console import Console

from mtsync.settings import Settings


class Connection:
    def __init__(self, console: Console, settings: Settings) -> None:
        self.console = console
        self.settings = settings

        self.session: aiohttp.ClientSession

    async def __aenter__(self):
        self.session = await aiohttp.ClientSession().__aenter__()
        return self

    async def __aexit__(self, *args):
        await self.session.__aexit__(*args)

    def _construct_url(
        self,
        endpoint: str,
    ) -> str:
        return f"https://{self.settings.hostname}/rest{endpoint}"

    async def call(
        self,
        method: Callable,
        endpoint: str,
        **kwargs: Dict[str, Any],
    ) -> None:
        async with method(
            self._construct_url(endpoint=endpoint),
            verify_ssl=not self.settings.ignore_certificate_errors,
            auth=aiohttp.BasicAuth(
                login=self.settings.username,
                password=self.settings.password,
            ),
            headers={"content-type": "application/json"},
            **kwargs,
        ) as response:
            try:
                return await response.json()
            except aiohttp.client_exceptions.ContentTypeError:
                text = await response.text()

                if text == "":
                    return None

                return json.loads(text)

    async def get(self, endpoint: str, params: Dict[str, str] = {}) -> Dict[str, str]:
        return await self.call(
            method=self.session.get,
            endpoint=endpoint,
            params=params,
        )

    async def post(self, endpoint: str, json: Dict[str, str] = {}) -> Dict[str, str]:
        return await self.call(
            method=self.session.post,
            endpoint=endpoint,
            json=json,
        )

    async def patch(self, endpoint: str, json: Dict[str, str] = {}) -> Dict[str, str]:
        return await self.call(
            method=self.session.patch,
            endpoint=endpoint,
            json=json,
        )

    async def put(self, endpoint: str, json: Dict[str, str] = {}) -> Dict[str, str]:
        return await self.call(
            method=self.session.put,
            endpoint=endpoint,
            json=json,
        )

    async def delete(self, endpoint: str) -> Dict[str, str]:
        return await self.call(
            method=self.session.delete,
            endpoint=endpoint,
        )
