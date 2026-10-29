"""
Sahaay AI - FastAPI Application Server
Entrypoint for the Sahaay AI Backend API service.
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from sahaay import __version__
from sahaay.api.routes import router, get_inference_service

from pathlib import Path
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse, RedirectResponse
from sahaay.security.logging_filter import attach_redacting_filter_to_root_logger

@asynccontextmanager
async def lifespan(app: FastAPI):
    attach_redacting_filter_to_root_logger()
    print("Preloading Sahaay Flood Vision AI model into memory...")
    try:
        service = get_inference_service()
        print(f"Sahaay AI model ready: {service.model_name} (v{service.model_version}) on {service.device}")
    except Exception as e:
        print(f"Warning: Model preloading failed: {e}")

    print("Starting automated background ingestion monitor...")
    try:
        from sahaay.ingestion.orchestrator import default_orchestrator
        default_orchestrator.start_background_scheduler(interval_seconds=300)
        print("Sahaay continuous ingestion monitor active.")
    except Exception as e:
        print(f"Warning: Failed to start background ingestion monitor: {e}")

    yield

    print("Sahaay AI API shutting down...")
    try:
        from sahaay.ingestion.orchestrator import default_orchestrator
        default_orchestrator.stop_background_scheduler()
    except Exception:
        pass

app = FastAPI(
    title="Sahaay AI — Flood Intelligence Platform API",
    description="Production-Ready AI Flood Intelligence & Early-Warning Platform for Hyderabad.",
    version=__version__,
    lifespan=lifespan
)

# Enable CORS for frontend integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)

static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

@app.get("/", include_in_schema=False)
async def root_redirect():
    return RedirectResponse(url="/dashboard")

@app.get("/dashboard", response_class=HTMLResponse, tags=["Dashboard"])
async def get_dashboard():
    index_file = static_dir / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return HTMLResponse("<h1>Dashboard index.html not found</h1>", status_code=404)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("sahaay.api.main:app", host="0.0.0.0", port=8000, reload=True)

