"""Geocode cache model for storing and retrieving geocoding results.

This module provides a database-backed cache for geocoding lookups to avoid
redundant external API calls and ensure consistency across geocoding results.
"""
from datetime import datetime, timezone
from sqlalchemy import Column, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import relationship

from app.db.session import Base


class GeocodeCache(Base):
    """Cached geocoding result for a location query."""
    __tablename__ = "geocode_cache"

    id = Column(Integer, primary_key=True)
    # The query string that was geocoded (normalized)
    query = Column(String(500), nullable=False, index=True)
    # Hash of the query for fast lookups
    query_hash = Column(String(64), nullable=False, unique=True, index=True)
    
    # Geocoding result
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    location_name = Column(String(255), nullable=True)
    formatted_address = Column(Text, nullable=True)
    
    # Result quality indicators
    status = Column(String(50), nullable=False, index=True)  # exact, approximate, ambiguous, failed, manual_required
    confidence = Column(Float, nullable=True)  # 0.0 to 1.0
    provider = Column(String(100), nullable=False)  # e.g., "nominatim", "arcgis", "manual"
    
    # Context
    country = Column(String(80), nullable=True)
    province = Column(String(80), nullable=True)
    jurisdiction = Column(String(80), nullable=True)
    
    # Metadata
    source_key = Column(String(255), nullable=True)  # Which source triggered this lookup
    metadata_json = Column("metadata", Text, nullable=True)  # JSON string for additional metadata
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    last_used_at = Column(DateTime(timezone=True), nullable=True)
