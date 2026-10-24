from __future__ import annotations

import asyncio
import threading

from app.services.events import EventBroker


class _RecordingWebSocket:
    def __init__(self) -> None:
        self.sent: list[tuple[asyncio.AbstractEventLoop, int, dict]] = []

    async def accept(self) -> None:
        return None

    async def send_json(self, message: dict) -> None:
        self.sent.append((asyncio.get_running_loop(), threading.get_ident(), message))


def test_broadcast_from_thread_sends_on_the_loop_that_owns_the_socket():
    broker = EventBroker()
    websocket = _RecordingWebSocket()

    async def scenario():
        await broker.connect(websocket)
        future = await asyncio.to_thread(broker.broadcast_from_thread, {"type": "ping"})
        await asyncio.wrap_future(future)
        return asyncio.get_running_loop(), threading.get_ident()

    loop, loop_thread = asyncio.run(scenario())

    assert websocket.sent == [(loop, loop_thread, {"type": "ping"})]


def test_broadcast_from_thread_is_a_no_op_before_any_client_connects():
    assert EventBroker().broadcast_from_thread({"type": "ping"}) is None


def test_broadcast_tolerates_clients_connecting_mid_broadcast():
    broker = EventBroker()
    late_client = _RecordingWebSocket()

    class ConnectsAnotherClient(_RecordingWebSocket):
        async def send_json(self, message: dict) -> None:
            await broker.connect(late_client)
            await super().send_json(message)

    first_client = ConnectsAnotherClient()

    async def scenario():
        await broker.connect(first_client)
        await broker.broadcast({"type": "ping"})

    asyncio.run(scenario())

    assert [message for *_, message in first_client.sent] == [{"type": "ping"}]
    assert broker._connections == {first_client, late_client}
