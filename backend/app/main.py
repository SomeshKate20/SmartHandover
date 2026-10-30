from contextlib import asynccontextmanager
import os

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

from .database import Base, engine, ensure_task_assignee_column
from .routes import ai, knowledge, meetings, tasks


LOCAL_CORS_ORIGINS = {"http://localhost:5173", "http://127.0.0.1:5173"}
DEPLOYED_CORS_ORIGINS = {
    "https://smart-handover.vercel.app",
    "https://smart-handover-3a40vay71-someshs-projects-93b80e84.vercel.app",
    "https://smart-handover-c6rb91ol3-someshs-projects-93b80e84.vercel.app",
    "https://smart-handover-dgder7wvt-someshs-projects-93b80e84.vercel.app",
}
ALLOWED_CORS_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]
ALLOWED_CORS_HEADERS = ["Content-Type", "Authorization"]


def cors_origins() -> list[str]:
    configured_origins = os.getenv("CORS_ORIGINS", "")
    deployed_origins = {origin.strip().rstrip("/") for origin in configured_origins.split(",") if origin.strip()}
    return sorted(LOCAL_CORS_ORIGINS | DEPLOYED_CORS_ORIGINS | deployed_origins)


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    ensure_task_assignee_column()
    yield


app = FastAPI(
    title="DigiPlus API",
    version="0.1.0",
    description="AI-powered knowledge and task management API.",
    lifespan=lifespan,
)

app.include_router(meetings.router)
app.include_router(tasks.router)
app.include_router(ai.router)
app.include_router(knowledge.router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins(),
    allow_credentials=False,
    allow_methods=ALLOWED_CORS_METHODS,
    allow_headers=ALLOWED_CORS_HEADERS,
)


@app.get("/health", tags=["system"])
@app.get("/api/health", tags=["system"])
def health_check() -> dict[str, str]:
    """Return a lightweight liveness response without requiring database setup."""
    return {"status": "ok", "service": "digiplus-api"}
