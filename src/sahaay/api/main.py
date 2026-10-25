"""
Sahaay AI - FastAPI Application Server
Entrypoint for the Sahaay AI Backend API service.
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from sahaay import __version__
from sahaay.api.routes import router, get_inference_service

@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Preloading Sahaay Flood Vision AI model into memory...")
    try:
        service = get_inference_service()
        print(f"Sahaay AI model ready: {service.model_name} (v{service.model_version}) on {service.device}")
    except Exception as e:
        print(f"Warning: Model preloading failed: {e}")
    yield
    print("Sahaay AI API shutting down...")

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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("sahaay.api.main:app", host="0.0.0.0", port=8000, reload=True)
