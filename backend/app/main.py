from contextlib import asynccontextmanager
import os

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

from .database import Base, engine
from .routes import meetings, tasks


LOCAL_CORS_ORIGINS = {"http://localhost:5173", "http://127.0.0.1:5173"}


def cors_origins() -> list[str]:
    configured_origins = os.getenv("CORS_ORIGINS", "")
    deployed_origins = {origin.strip().rstrip("/") for origin in configured_origins.split(",") if origin.strip()}
    return sorted(LOCAL_CORS_ORIGINS | deployed_origins)


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="DigiPlus API",
    version="0.1.0",
    description="AI-powered knowledge and task management API.",
    lifespan=lifespan,
)

app.include_router(meetings.router)
app.include_router(tasks.router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["system"])
@app.get("/api/health", tags=["system"])
def health_check() -> dict[str, str]:
    """Return a lightweight liveness response without requiring database setup."""
    return {"status": "ok", "service": "digiplus-api"}
