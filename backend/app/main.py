from __future__ import annotations

import asyncio

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.llm_service import assess_urgency
from app.models import PriorityRequest
from app.queue_service import queue_service
from app.ws_manager import ws_manager


def _bridge_queue_events(event_type: str, payload: dict) -> None:
    asyncio.create_task(ws_manager.broadcast(event_type, payload))


queue_service.subscribe(_bridge_queue_events)

app = FastAPI(title="医院智能叫号系统", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins.split(",") if settings.cors_origins != "*" else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def health():
    return {"status": "ok", "llm_mock": settings.llm_use_mock or not bool(settings.llm_api_key)}


@app.get("/api/queue")
async def get_queue():
    return queue_service.get_state()


@app.get("/api/patients/{patient_id}")
async def get_patient(patient_id: str):
    p = queue_service.get_patient(patient_id)
    if not p:
        raise HTTPException(404, "患者不存在")
    pos = queue_service.position_in_queue(patient_id)
    return {
        "patient": p,
        "position": pos,
        "ahead_count": max(pos, 0),
        "estimated_wait_minutes": queue_service.estimate_wait_minutes(patient_id),
        "state": queue_service.get_state(),
    }


@app.post("/api/queue/call-next")
async def call_next():
    return await queue_service.call_next()


@app.post("/api/queue/skip")
async def skip_current():
    return await queue_service.skip_current()


@app.post("/api/queue/pause")
async def pause_calling(paused: bool = True):
    return await queue_service.set_paused(paused)


@app.post("/api/queue/resume")
async def resume_calling():
    return await queue_service.set_paused(False)


@app.post("/api/priority/request")
async def priority_request(body: PriorityRequest):
    patient = queue_service.get_patient(body.patient_id)
    if not patient:
        raise HTTPException(404, "患者不存在")
    assessment = await assess_urgency(body.reason)
    result = await queue_service.apply_priority(body.patient_id, assessment)
    return result


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await ws_manager.connect(websocket)
    await websocket.send_json(
        {
            "type": "connected",
            "payload": queue_service.snapshot_for_sync(),
        }
    )
    try:
        while True:
            raw = await websocket.receive_text()
            if raw == "ping":
                await websocket.send_json({"type": "pong", "payload": {}})
    except WebSocketDisconnect:
        await ws_manager.disconnect(websocket)


def run() -> None:
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=True,
    )


if __name__ == "__main__":
    run()
