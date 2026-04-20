"""
Garage Attendance System — FastAPI entry point.
"""

import os
os.environ["TF_USE_LEGACY_KERAS"] = "1"

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.database import connect_db, close_db
from utils.firebase_helper import init_firebase
from routers import auth, owner, kiosk


# ──── Lifespan: startup / shutdown ────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await connect_db()
    init_firebase()
    yield
    # Shutdown
    await close_db()


# ──── App ─────────────────────────────────────────────────────────
app = FastAPI(
    title="Garage Attendance System",
    version="1.0.0",
    description="Face-recognition attendance tracking for garage employees.",
    lifespan=lifespan,
)

# CORS — allow all origins for kiosk / mobile clients
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ──── Routers ─────────────────────────────────────────────────────
app.include_router(auth.router)
app.include_router(owner.router)
app.include_router(kiosk.router)


# ──── Health check ────────────────────────────────────────────────
@app.get("/", tags=["Health"])
async def root():
    return {"status": "ok", "service": "Garage Attendance API"}


@app.get("/health", tags=["Health"])
async def health():
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn
    # Increased limits to handle large base64 photo uploads
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        limit_max_requests=None,
        h11_max_incomplete_event_size=52428800  # 50MB
    )

