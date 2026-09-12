"""Court router: channels case-run requests into the court handler."""

from __future__ import annotations

import json

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from ..handlers import court as court_handler
from ..models.case import CaseRequest, CaseResponse

router = APIRouter(prefix="/api", tags=["court"])


@router.post("/court/run", response_model=CaseResponse)
async def court_run(case: CaseRequest) -> CaseResponse:
    return await court_handler.handle_run(case)


@router.post("/court/run/stream")
async def court_run_stream(case: CaseRequest) -> StreamingResponse:
    """Event-driven run: NDJSON stream, one court event per line."""
    court_handler.validate_overrides(case)

    async def event_lines():
        try:
            async for event in court_handler.run_case_events(
                case.title, case.context, case.query, case.model_overrides
            ):
                yield json.dumps(event) + "\n"
        except Exception as exc:  # surface mid-stream failures as a final event
            yield json.dumps({"event": "error", "detail": str(exc)}) + "\n"

    return StreamingResponse(event_lines(), media_type="application/x-ndjson")
