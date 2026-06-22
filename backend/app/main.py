from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.routers import (
    dashboard,
    datasets,
    demo,
    evaluations,
    health,
    projects,
    prompts,
    rag,
    traces,
)

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
app.include_router(dashboard.router, prefix="/v1")
app.include_router(rag.router, prefix="/v1")
app.include_router(evaluations.router, prefix="/v1")
app.include_router(prompts.router, prefix="/v1")
app.include_router(datasets.router, prefix="/v1")
app.include_router(demo.router, prefix="/v1")
