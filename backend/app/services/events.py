from __future__ import annotations

import asyncio
from concurrent.futures import Future
from typing import Any

from fastapi import WebSocket


class EventBroker:
    def __init__(self) -> None:
        self._connections: set[WebSocket] = set()
        self._loop: asyncio.AbstractEventLoop | None = None

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        # Sockets belong to the loop that accepted them; remember it so worker
        # threads can hand their broadcasts back to it.
        self._loop = asyncio.get_running_loop()
        self._connections.add(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        self._connections.discard(websocket)

    async def broadcast(self, message: dict[str, Any]) -> None:
        stale: list[WebSocket] = []
        # Iterate over a copy: clients can connect or disconnect while a send is awaited.
        for websocket in list(self._connections):
            try:
                await websocket.send_json(message)
            except Exception:
                stale.append(websocket)
        for websocket in stale:
            self.disconnect(websocket)

    def broadcast_from_thread(self, message: dict[str, Any]) -> Future[None] | None:
        """Broadcast from a worker thread by scheduling it on the sockets' event loop.

        WebSocket sends are not thread-safe and must run on the loop that owns the
        connection, so a thread cannot simply asyncio.run() a broadcast. Returns
        None when no client has connected yet, as there is nobody to notify.
        """
        loop = self._loop
        if loop is None or loop.is_closed():
            return None
        return asyncio.run_coroutine_threadsafe(self.broadcast(message), loop)
