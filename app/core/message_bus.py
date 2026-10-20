from __future__ import annotations

from collections import defaultdict
from collections.abc import Awaitable, Callable

from app.core.tracing import TraceStore
from app.schemas import BaseMessage

MessageHandler = Callable[[BaseMessage], Awaitable[None]]


class MessageBus:
    def __init__(self, trace_store: TraceStore) -> None:
        self.trace_store = trace_store
        self._subscribers: dict[str, list[MessageHandler]] = defaultdict(list)

    def subscribe(self, kind: str, handler: MessageHandler) -> None:
        self._subscribers[kind].append(handler)

    async def publish(self, message: BaseMessage, task_id: str | None = None) -> None:
        self.trace_store.log_message(message, task_id=task_id)
        for handler in list(self._subscribers.get(message.kind, [])):
            await handler(message)
        for handler in list(self._subscribers.get("*", [])):
            await handler(message)

    def history(self, task_id: str) -> list[dict]:
        return self.trace_store.messages(task_id)
