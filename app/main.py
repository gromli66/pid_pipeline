"""
P&ID Pipeline API - FastAPI Application.
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import structlog

from app.config import settings
from app.db import async_engine
from app.api import projects, diagrams, detection, cvat, segmentation, skeleton, junction, graph, validation

# Logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer()
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle events."""
    logger.info("Starting P&ID Pipeline API", version="1.0.0")
    yield
    logger.info("Shutting down P&ID Pipeline API")
    await async_engine.dispose()


app = FastAPI(
    title="P&ID Pipeline API",
    description="API для обработки P&ID диаграмм",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error("Unhandled exception", path=request.url.path, error=str(exc), exc_info=True)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


# Health
@app.get("/health", tags=["Health"])
async def health_check():
    return {"status": "healthy", "service": "pid-pipeline-api"}


# Routers
app.include_router(projects.router, prefix="/api/projects", tags=["Projects"])
app.include_router(diagrams.router, prefix="/api/diagrams", tags=["Diagrams"])
app.include_router(detection.router, prefix="/api/detection", tags=["Detection"])
app.include_router(cvat.router, prefix="/api/cvat", tags=["CVAT"])
app.include_router(segmentation.router, prefix="/api/segmentation", tags=["Segmentation"])
app.include_router(skeleton.router, prefix="/api/skeleton", tags=["Skeleton"])
app.include_router(junction.router, prefix="/api/junction", tags=["Junction"])
app.include_router(graph.router, prefix="/api/graph", tags=["Graph"])
app.include_router(validation.router, prefix="/api/validation", tags=["Validation"])


@app.get("/", tags=["Root"])
async def root():
    return {"name": "P&ID Pipeline API", "version": "1.0.0", "docs": "/docs"}
