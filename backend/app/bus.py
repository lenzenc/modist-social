import asyncio
import contextlib


class Bus:
    """In-process pub/sub. Each WebSocket client gets its own bounded queue."""

    def __init__(self) -> None:
        self._subs: set[asyncio.Queue] = set()

    @contextlib.contextmanager
    def subscribe(self):
        q: asyncio.Queue = asyncio.Queue(maxsize=1000)
        self._subs.add(q)
        try:
            yield q
        finally:
            self._subs.discard(q)

    def publish(self, event: dict) -> None:
        for q in list(self._subs):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                # A stalled client: drop it rather than block the simulation.
                self._subs.discard(q)


bus = Bus()
