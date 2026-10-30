from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


app = FastAPI(
    title="DigiPlus API",
    version="0.1.0",
    description="AI-powered knowledge and task management API.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health", tags=["system"])
def health_check() -> dict[str, str]:
    """Return a lightweight liveness response without requiring database setup."""
    return {"status": "ok", "service": "digiplus-api"}
