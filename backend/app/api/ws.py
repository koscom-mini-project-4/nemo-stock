from __future__ import annotations

import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.dependencies import Container

router = APIRouter()


@router.websocket("/ws/runs/{run_id}")
async def run_events_ws(websocket: WebSocket, run_id: str) -> None:
    await websocket.accept()
    container: Container = websocket.app.state.container
    loop = asyncio.get_event_loop()

    def _consume() -> None:
        for event in container.event_bus.subscribe(run_id):
            asyncio.run_coroutine_threadsafe(websocket.send_json(event.to_dict()), loop)

    try:
        await loop.run_in_executor(None, _consume)
    except WebSocketDisconnect:
        return
