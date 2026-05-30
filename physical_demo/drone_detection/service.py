"""FastAPI detection service (port 5001).

Exposes the binary detection state at ``GET /status`` and a manual control
endpoint ``POST /sim`` (the Iteration 0 stub "detector"). A background task
re-publishes the detection event to multicast while detected, so the relay sees
a live stream rather than a single edge.
"""
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from pydantic import BaseModel

import config
from publisher import MulticastPublisher, build_event
from state import DetectionState

state = DetectionState()
publisher = MulticastPublisher()

# Optional hands-free demo toggling; set by main.py before launch (0 = off).
auto_toggle_s = 0.0


class SimRequest(BaseModel):
    detected: bool
    anomaly_score: float | None = None


def _toggle() -> None:
    """Flip detection state once; publish on the rising edge."""
    if state.detected:
        state.clear()
    elif state.set_detected(config.DEFAULT_ANOMALY_SCORE):
        publisher.send(build_event(state.snapshot()))


async def _heartbeat() -> None:
    while True:
        await asyncio.sleep(config.PUBLISH_INTERVAL_S)
        if state.detected:
            publisher.send(build_event(state.snapshot()))


async def _auto_toggle() -> None:
    while True:
        await asyncio.sleep(auto_toggle_s)
        _toggle()


@asynccontextmanager
async def lifespan(app: FastAPI):
    tasks = [asyncio.create_task(_heartbeat())]
    if auto_toggle_s > 0:
        tasks.append(asyncio.create_task(_auto_toggle()))
    try:
        yield
    finally:
        for task in tasks:
            task.cancel()
        publisher.close()


app = FastAPI(title="Drone Detection Service", lifespan=lifespan)


@app.get("/status")
async def status() -> dict:
    return state.snapshot()


@app.post("/sim")
async def sim(req: SimRequest) -> dict:
    """Stub detector control: flip the detection state by hand."""
    if req.detected:
        score = req.anomaly_score if req.anomaly_score is not None else config.DEFAULT_ANOMALY_SCORE
        rising = state.set_detected(score)
        if rising:  # publish immediately on the false->true edge
            publisher.send(build_event(state.snapshot()))
    else:
        state.clear()
    return state.snapshot()
