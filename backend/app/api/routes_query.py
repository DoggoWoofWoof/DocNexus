import json
import queue
import threading
from collections.abc import Iterator

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlmodel import Session

from backend.app.clients.mistral import MistralClientError, MistralConfigurationError
from backend.app.core.config import Settings, get_settings
from backend.app.db.session import engine, get_session
from backend.app.schemas.query import QueryRequest, QueryResponse
from backend.app.schemas.trace import TraceEvent
from backend.app.services.query_workflow import run_query_workflow


router = APIRouter(tags=["query"])


@router.post("/query", response_model=QueryResponse)
def run_query(
    request: QueryRequest,
    settings: Settings = Depends(get_settings),
    session: Session = Depends(get_session),
) -> QueryResponse:
    try:
        return run_query_workflow(settings=settings, session=session, request=request)
    except MistralConfigurationError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        ) from exc
    except MistralClientError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc


@router.post("/query/stream")
def stream_query(
    request: QueryRequest,
    settings: Settings = Depends(get_settings),
) -> StreamingResponse:
    if not settings.mistral_api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="MISTRAL_API_KEY is not configured.",
        )

    return StreamingResponse(
        _query_stream(settings=settings, request=request),
        media_type="application/x-ndjson",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


def _query_stream(*, settings: Settings, request: QueryRequest) -> Iterator[str]:
    events: queue.Queue[dict[str, object] | None] = queue.Queue()

    def emit_trace(event: TraceEvent) -> None:
        if request.include_trace:
            events.put({"type": "trace", "data": event.model_dump(mode="json", by_alias=True)})

    def run_workflow() -> None:
        try:
            with Session(engine) as session:
                response = run_query_workflow(
                    settings=settings,
                    session=session,
                    request=request,
                    trace_sink=emit_trace,
                )
            events.put({"type": "result", "data": response.model_dump(mode="json", by_alias=True)})
        except (MistralConfigurationError, MistralClientError) as exc:
            events.put({"type": "error", "data": {"message": str(exc)}})
        except Exception as exc:
            events.put({"type": "error", "data": {"message": f"Query stream failed: {exc}"}})
        finally:
            events.put(None)

    thread = threading.Thread(target=run_workflow, daemon=True)
    thread.start()

    while True:
        event = events.get()
        if event is None:
            break
        yield json.dumps(event) + "\n"
