"""FastAPI application server."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from database.connection import init_db
from api.routes import carbon, analytics, recommendations, auth
import os

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:  # pragma: no cover - optional in minimal local setup
    load_dotenv = None

if load_dotenv:
    load_dotenv()

from utils.logging_config import configure_logging, get_logger  # noqa: E402 -- must load .env first

configure_logging()
logger = get_logger(__name__)

# Initialize database
init_db()
logger.info("startup.db_initialized")

# Create FastAPI app
app = FastAPI(
    title="Cloud Carbon Tracker API",
    description="SaaS platform for multi-cloud carbon tracking and optimization",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:8501").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router, prefix="/api/auth", tags=["Authentication"])
app.include_router(carbon.router, prefix="/api/carbon", tags=["Carbon"])
app.include_router(analytics.router, prefix="/api/analytics", tags=["Analytics"])
app.include_router(recommendations.router, prefix="/api/recommendations", tags=["Recommendations"])


@app.get("/")
def root():
    """Root endpoint."""
    return {
        "message": "Cloud Carbon Tracker API",
        "version": "1.0.0",
        "docs": "/docs"
    }


@app.get("/health")
def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn
    logger.info("startup.server_starting", extra={"host": "0.0.0.0", "port": 8000})
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )

