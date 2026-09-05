from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.exc import SQLAlchemyError
from app.api.webhooks import router as webhook_router
from app.api.dashboard import router as dashboard_router
from app.api.optimization import router as optimization_router
from app.api.audit import router as audit_router
from app.api.copilot import router as copilot_router
from app.api.recovery_batches import router as recovery_batches_router
from app.api.evaluation import router as evaluation_router
from app.api.interventions import router as interventions_router
from app.api.batch_stream import router as batch_stream_router

from app.database import check_database_connection
from app.api.recovery import (
    router as recovery_router,
)

app = FastAPI(
    title="RecoverIQ API",
    version="0.1.0",
    description=(
        "AI-powered revenue recovery "
        "decision and optimization engine."
    ),
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_origin_regex=r"^http://(localhost|127\.0\.0\.1):517[3-9]$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(webhook_router)
app.include_router(dashboard_router)
app.include_router(optimization_router)
app.include_router(audit_router)
app.include_router(copilot_router)
app.include_router(recovery_batches_router)
app.include_router(evaluation_router)
app.include_router(interventions_router)
app.include_router(batch_stream_router)
@app.get("/")
def root():

    return {
        "service": "RecoverIQ",
        "status": "running",
    }


@app.get("/health")
def health():

    return {
        "status": "healthy",
    }


app.include_router(
    recovery_router
)


@app.get("/health/database")
def database_health():
    try:
        check_database_connection()
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=503,
            detail="Database connection failed",
        ) from exc

    return {
        "status": "ok",
        "database": "connected",
    }
