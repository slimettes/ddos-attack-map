"""
FastAPI application entry point.
Configures the main application instance with middleware, routers, and lifecycle events.
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import structlog
import redis.asyncio as redis
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.settings import get_settings
from app.database import init_db
from app.routers import health, events, admin
from app.utils.logging import setup_logging
from app.services.websocket import WebSocketManager

# Configure structured logging
setup_logging()
logger = structlog.get_logger(__name__)

# Initialize settings
settings = get_settings()

# Rate limiter
limiter = Limiter(key_func=get_remote_address)

# Global instances
redis_client = None
scheduler = None
websocket_manager = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan context manager."""
    global redis_client, scheduler, websocket_manager
    
    logger.info("Starting DDoS Attack Map application")
    
    try:
        # Initialize Redis connection
        redis_client = redis.from_url(settings.redis_url, decode_responses=True)
        await redis_client.ping()
        logger.info("Redis connection established")
        
        # Initialize database
        await init_db()
        logger.info("Database initialized")
        
        # Initialize WebSocket manager
        websocket_manager = WebSocketManager(redis_client)
        app.state.websocket_manager = websocket_manager
        
        # Initialize and start scheduler
        scheduler = AsyncIOScheduler()
        await setup_background_tasks(scheduler, redis_client)
        scheduler.start()
        logger.info("Background scheduler started")
        
        yield
        
    except Exception as e:
        logger.error("Failed to initialize application", error=str(e))
        raise
    finally:
        # Cleanup
        if scheduler and scheduler.running:
            scheduler.shutdown()
            logger.info("Scheduler stopped")
        
        if redis_client:
            await redis_client.close()
            logger.info("Redis connection closed")
        
        logger.info("Application shutdown complete")


# Create FastAPI app
app = FastAPI(
    title="DDoS Attack Map API",
    description="Real-time visualization of global DDoS attack patterns",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None,
)

# Add rate limiting
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Handle unexpected exceptions."""
    logger.error(
        "Unhandled exception",
        path=request.url.path,
        method=request.method,
        error=str(exc),
        exc_info=True
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"}
    )


# Include routers
app.include_router(health.router, prefix="/api/v1", tags=["health"])
app.include_router(events.router, prefix="/api/v1", tags=["events"])
app.include_router(admin.router, prefix="/api/v1/admin", tags=["admin"])


async def setup_background_tasks(scheduler: AsyncIOScheduler, redis_client):
    """Configure background tasks for data ingestion and processing."""
    from app.services.radar_client import RadarDataFetcher
    from app.services.abuse_client import AbuseIPEnricher
    from app.services.ml_service import MLService
    
    # Initialize services
    radar_fetcher = RadarDataFetcher(redis_client)
    abuse_enricher = AbuseIPEnricher(redis_client)
    ml_service = MLService()
    
    # Add radar data fetching job
    scheduler.add_job(
        radar_fetcher.fetch_latest_data,
        'interval',
        seconds=settings.radar_fetch_interval_seconds,
        id='fetch_radar_data',
        replace_existing=True
    )
    
    # Add abuse IP enrichment job (if enabled)
    if settings.enable_abuseipdb:
        scheduler.add_job(
            abuse_enricher.enrich_recent_ips,
            'interval',
            seconds=settings.abuseip_enrich_interval_seconds,
            id='enrich_abuse_ips',
            replace_existing=True
        )
    
    # Add event cleanup job
    scheduler.add_job(
        cleanup_old_events,
        'interval',
        hours=1,
        id='cleanup_events',
        replace_existing=True
    )
    
    logger.info("Background tasks configured")


async def cleanup_old_events():
    """Clean up old events from the database."""
    from app.database import get_session
    from app.models.events import DDoSEvent
    from datetime import datetime, timedelta
    from sqlmodel import delete
    
    cutoff_time = datetime.utcnow() - timedelta(hours=settings.event_cleanup_hours)
    
    async with get_session() as session:
        stmt = delete(DDoSEvent).where(DDoSEvent.created_at < cutoff_time)
        result = await session.exec(stmt)
        await session.commit()
        
        logger.info("Cleaned up old events", deleted_count=result.rowcount)


# Health check endpoint at root
@app.get("/")
async def root():
    """Root endpoint providing basic service information."""
    return {
        "service": "DDoS Attack Map",
        "status": "operational",
        "version": "1.0.0",
        "endpoints": {
            "health": "/api/v1/health",
            "events": "/api/v1/events",
            "docs": "/docs" if settings.debug else "disabled",
        }
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.reload,
        log_level=settings.log_level.lower()
    )