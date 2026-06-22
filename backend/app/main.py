from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.routers import demo, health, projects, traces

settings = get_settings()

app = FastAPI(
    title="Helios API",
    description="AI systems observability backend",
    version=settings.app_version,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(projects.router, prefix="/v1")
app.include_router(traces.router, prefix="/v1")
app.include_router(demo.router, prefix="/v1")
