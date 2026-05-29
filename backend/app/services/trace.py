from time import perf_counter
from collections.abc import Callable
from threading import Lock
from uuid import uuid4

from backend.app.schemas.trace import AgentName, TraceEvent, TraceStatus


class TraceBuilder:
    def __init__(self, on_event: Callable[[TraceEvent], None] | None = None) -> None:
        self.events: list[TraceEvent] = []
        self._started_at: dict[str, float] = {}
        self._on_event = on_event
        self._lock = Lock()

    def started(
        self,
        *,
        agent: AgentName,
        message: str,
        metadata: dict[str, object] | None = None,
    ) -> str:
        event_id = self._new_id()
        event = TraceEvent(
            id=event_id,
            agent=agent,
            status=TraceStatus.started,
            message=message,
            metadata=metadata or {},
        )
        with self._lock:
            self._started_at[event_id] = perf_counter()
            self.events.append(event)
        self._emit(event)
        return event_id

    def completed(
        self,
        *,
        started_event_id: str | None,
        agent: AgentName,
        message: str,
        metadata: dict[str, object] | None = None,
    ) -> str:
        return self._finish(
            started_event_id=started_event_id,
            agent=agent,
            status=TraceStatus.completed,
            message=message,
            metadata=metadata,
        )

    def failed(
        self,
        *,
        started_event_id: str | None,
        agent: AgentName,
        message: str,
        metadata: dict[str, object] | None = None,
    ) -> str:
        return self._finish(
            started_event_id=started_event_id,
            agent=agent,
            status=TraceStatus.failed,
            message=message,
            metadata=metadata,
        )

    def skipped(
        self,
        *,
        agent: AgentName,
        message: str,
        metadata: dict[str, object] | None = None,
    ) -> str:
        event_id = self._new_id()
        self._record(
            TraceEvent(
                id=event_id,
                agent=agent,
                status=TraceStatus.skipped,
                message=message,
                metadata=metadata or {},
            )
        )
        return event_id

    def retrying(
        self,
        *,
        agent: AgentName,
        message: str,
        metadata: dict[str, object] | None = None,
    ) -> str:
        event_id = self._new_id()
        self._record(
            TraceEvent(
                id=event_id,
                agent=agent,
                status=TraceStatus.retrying,
                message=message,
                metadata=metadata or {},
            )
        )
        return event_id

    def _finish(
        self,
        *,
        started_event_id: str | None,
        agent: AgentName,
        status: TraceStatus,
        message: str,
        metadata: dict[str, object] | None,
    ) -> str:
        elapsed_ms = None
        event_id = self._new_id()
        with self._lock:
            if started_event_id and started_event_id in self._started_at:
                elapsed_ms = int((perf_counter() - self._started_at[started_event_id]) * 1000)
            event = TraceEvent(
                id=event_id,
                agent=agent,
                status=status,
                message=message,
                elapsed_ms=elapsed_ms,
                metadata=metadata or {},
            )
            self.events.append(event)
        self._emit(event)
        return event_id

    def _record(self, event: TraceEvent) -> None:
        with self._lock:
            self.events.append(event)
        self._emit(event)

    def _emit(self, event: TraceEvent) -> None:
        if self._on_event:
            self._on_event(event)

    @staticmethod
    def _new_id() -> str:
        return f"trace_{uuid4().hex[:12]}"
