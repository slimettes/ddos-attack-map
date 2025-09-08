"""
Health check and version endpoints for monitoring and diagnostics.
"""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
import redis.asyncio as redis
from datetime import datetime, timezone
import structlog

from app.settings import get_settings
from app.models.responses import HealthResponse, VersionResponse
from app.database import get_session

router = APIRouter()
limiter = Limiter(key_func=get_remote_address)
logger = structlog.get_logger(__name__)


@router.get("/health", response_model=HealthResponse)
@limiter.limit("10/minute")
async def health_check(request):
    """
    Comprehensive health check endpoint.
    Verifies database, Redis, and external service connectivity.
    """
    settings = get_settings()
    health_data = {
        "status": "healthy",
        "timestamp": datetime.now(timezone.utc),
        "version": "1.0.0",
        "services": {}
    }
    
    overall_healthy = True
    
    # Check database connectivity
    try:
        async with get_session() as session:
            await session.exec("SELECT 1")
        health_data["services"]["database"] = {
            "status": "healthy",
            "response_time_ms": None  # Could add timing if needed
        }
        logger.debug("Database health check passed")
    except Exception as e:
        health_data["services"]["database"] = {
            "status": "unhealthy",
            "error": str(e)
        }
        overall_healthy = False
        logger.error("Database health check failed", error=str(e))
    
    # Check Redis connectivity
    try:
        redis_client = redis.from_url(settings.redis_url, decode_responses=True)
        await redis_client.ping()
        await redis_client.close()
        health_data["services"]["redis"] = {
            "status": "healthy"
        }
        logger.debug("Redis health check passed")
    except Exception as e:
        health_data["services"]["redis"] = {
            "status": "unhealthy",
            "error": str(e)
        }
        overall_healthy = False
        logger.error("Redis health check failed", error=str(e))
    
    # Check external API availability (non-blocking)
    health_data["services"]["external_apis"] = {
        "abuseipdb": {
            "enabled": settings.enable_abuseipdb,
            "status": "configured" if settings.abuseipdb_key else "not_configured"
        },
        "cloudflare_radar": {
            "enabled": settings.enable_real_radar_data,
            "mode": settings.cloudflare_source
        }
    }
    
    # Set overall status
    if not overall_healthy:
        health_data["status"] = "degraded"
    
    status_code = 200 if overall_healthy else 503
    return JSONResponse(content=health_data, status_code=status_code)


@router.get("/health/ready")
@limiter.limit("20/minute")
async def readiness_probe(request):
    """
    Kubernetes-style readiness probe.
    Returns 200 if the service is ready to accept traffic.
    """
    settings = get_settings()
    
    try:
        # Quick database check
        async with get_session() as session:
            await session.exec("SELECT 1")
        
        # Quick Redis check
        redis_client = redis.from_url(settings.redis_url, decode_responses=True)
        await redis_client.ping()
        await redis_client.close()
        
        return {"status": "ready"}
    except Exception as e:
        logger.error("Readiness check failed", error=str(e))
        raise HTTPException(status_code=503, detail="Service not ready")


@router.get("/health/live")
@limiter.limit("30/minute")
async def liveness_probe(request):
    """
    Kubernetes-style liveness probe.
    Returns 200 if the application process is running.
    """
    return {
        "status": "alive",
        "timestamp": datetime.now(timezone.utc),
        "uptime_seconds": None  # Could add process uptime tracking
    }


@router.get("/version", response_model=VersionResponse)
@limiter.limit("30/minute")
async def get_version(request):
    """
    Get application version and build information.
    """
    settings = get_settings()
    
    return {
        "version": "1.0.0",
        "build_date": "2025-01-01T00:00:00Z",  # Would be injected at build time
        "commit_hash": "dev",  # Would be injected from git
        "environment": "development" if settings.debug else "production",
        "features": {
            "abuseipdb_enabled": settings.enable_abuseipdb,
            "real_data_enabled": settings.enable_real_radar_data,
            "mock_events": settings.mock_event_generation
        }
    }