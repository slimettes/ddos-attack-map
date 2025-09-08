"""
Application configuration management using Pydantic Settings.
Loads configuration from environment variables with sensible defaults.
"""

from pydantic import Field
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # Database Configuration
    database_url: str = Field(
        default="postgresql://ddos_user:ddos_pass@localhost:5432/ddos_map_db",
        description="PostgreSQL connection URL"
    )
    redis_url: str = Field(
        default="redis://localhost:6379/0",
        description="Redis connection URL"
    )
    
    # External API Keys
    abuseipdb_key: Optional[str] = Field(default=None, description="AbuseIPDB API key")
    maxmind_license_key: Optional[str] = Field(default=None, description="MaxMind license key")
    cloudflare_api_token: Optional[str] = Field(default=None, description="Cloudflare API token")
    
    # Feature Flags
    enable_abuseipdb: bool = Field(default=False, description="Enable AbuseIPDB enrichment")
    enable_real_radar_data: bool = Field(default=False, description="Use real Cloudflare Radar data")
    cloudflare_source: str = Field(default="mock", description="Cloudflare data source: mock|live")
    
    # Security
    secret_key: str = Field(
        default="dev-secret-key-change-in-production",
        description="Secret key for JWT tokens"
    )
    jwt_algorithm: str = Field(default="HS256", description="JWT signing algorithm")
    jwt_expiration_hours: int = Field(default=24, description="JWT token expiration time")
    
    # Rate Limiting
    rate_limit_per_minute: int = Field(default=60, description="API rate limit per minute")
    websocket_rate_limit: int = Field(default=1, description="WebSocket messages per second")
    max_websocket_connections: int = Field(default=100, description="Maximum WebSocket connections")
    
    # ML Model Configuration
    ml_model_path: str = Field(default="./models/ddos_classifier.joblib", description="ML model file path")
    confidence_threshold: float = Field(default=0.7, description="Base confidence threshold")
    high_confidence_threshold: float = Field(default=0.85, description="High confidence threshold")
    
    # Background Tasks
    radar_fetch_interval_seconds: int = Field(default=30, description="Radar data fetch interval")
    abuseip_enrich_interval_seconds: int = Field(default=60, description="IP enrichment interval")
    event_cleanup_hours: int = Field(default=24, description="Event retention period")
    
    # Logging
    log_level: str = Field(default="INFO", description="Logging level")
    log_format: str = Field(default="json", description="Log format: json|text")
    
    # Development
    debug: bool = Field(default=False, description="Enable debug mode")
    reload: bool = Field(default=False, description="Enable auto-reload")
    
    # Data Generation
    mock_event_generation: bool = Field(default=True, description="Generate mock events for development")
    events_per_fetch: int = Field(default=10, description="Events generated per fetch cycle")
    max_events_cache_size: int = Field(default=1000, description="Maximum events in Redis cache")
    
    class Config:
        env_file = ".env"
        case_sensitive = False


# Global settings instance
settings = Settings()


def get_settings() -> Settings:
    """Get application settings instance."""
    return settings