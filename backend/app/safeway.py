"""Safeway cart adapter. The cart is filled but never checked out: the household pays in Safeway's own app.

mode=mcp spawns the third-party @striderlabs/mcp-safeway server (Playwright against safeway.com) once and keeps it
alive, because its login lives in that process's memory. mode=mock returns plausible fake products for development.
"""
import asyncio
import json
from contextlib import AsyncExitStack

from . import config


class SafewayError(Exception):
    pass


class MockSafeway:
    async def search(self, query: str, limit: int = 4) -> list[dict]:
        return [
            {"id": f"mock-{abs(hash(query)) % 9999}-{i}", "name": f"{b} {query.title()}", "price": round(1.99 + i * 1.5, 2),
             "unit": "each", "in_stock": True}
            for i, b in enumerate(["Signature Select", "O Organics", "Lucerne", "Brand Name"][:limit])
        ]

    async def add_to_cart(self, product_id: str, quantity: int) -> None:
        return None


class McpSafeway:
    def __init__(self):
        self._stack: AsyncExitStack | None = None
        self._session = None
        self._lock = asyncio.Lock()

    async def _connect(self):
        if self._session:
            return self._session
        if not (config.SAFEWAY_EMAIL and config.SAFEWAY_PASSWORD):
            raise SafewayError("SAFEWAY_EMAIL / SAFEWAY_PASSWORD are not set")
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        stack = AsyncExitStack()
        try:
            read, write = await stack.enter_async_context(
                stdio_client(StdioServerParameters(command=config.SAFEWAY_MCP_COMMAND, args=[]))
            )
            session = await stack.enter_async_context(ClientSession(read, write))
            await session.initialize()
            self._session, self._stack = session, stack
            login = await self._call("safeway_login", {"email": config.SAFEWAY_EMAIL, "password": config.SAFEWAY_PASSWORD})
            if not login.get("success"):
                raise SafewayError(f"Safeway login failed: {login.get('message')}")
        except Exception:
            await stack.aclose()
            self._session = self._stack = None
            raise
        return session

    async def _call(self, tool: str, args: dict) -> dict:
        result = await self._session.call_tool(tool, args)
        text = "".join(c.text for c in result.content if getattr(c, "type", "") == "text")
        if result.isError or text.startswith("Error:"):
            raise SafewayError(text)
        return json.loads(text)

    async def _run(self, tool: str, args: dict) -> dict:
        async with self._lock:  # one browser page: serialize calls
            await self._connect()
            try:
                return await self._call(tool, args)
            except SafewayError:
                raise
            except Exception:  # dead subprocess: drop it so the next call reconnects
                if self._stack:
                    await self._stack.aclose()
                self._session = self._stack = None
                raise

    async def search(self, query: str, limit: int = 4) -> list[dict]:
        data = await self._run("safeway_search_products", {"query": query})
        return [
            {"id": p["id"], "name": p["name"], "brand": p.get("brand"), "price": p.get("salePrice") or p.get("price"),
             "unit": p.get("unit"), "in_stock": p.get("inStock", True)}
            for p in data.get("products", [])[:limit]
        ]

    async def add_to_cart(self, product_id: str, quantity: int) -> None:
        data = await self._run("safeway_add_to_cart", {"product_id": product_id, "quantity": quantity})
        if not data.get("success"):
            raise SafewayError(data.get("message", "add to cart failed"))


_client = None


def get_client():
    global _client
    if _client is None:
        _client = McpSafeway() if config.SAFEWAY_MODE == "mcp" else MockSafeway()
    return _client
