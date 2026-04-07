"""Database models - Pure Python approach for Python 3.13 compatibility."""

from datetime import datetime
from dataclasses import dataclass, field
from typing import Optional, List
from pydantic import BaseModel, Field


# ============== PYDANTIC MODELS (for API/validation) ==============

class UserModel(BaseModel):
    """User data model."""
    id: Optional[int] = None
    email: str
    password_hash: str
    full_name: Optional[str] = None
    is_active: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        from_attributes = True


class OrganizationModel(BaseModel):
    """Organization model."""
    id: Optional[int] = None
    name: str
    description: Optional[str] = None
    owner_id: int
    plan: str = "starter"
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        from_attributes = True


class LoginRequest(BaseModel):
    """Login request model."""
    email: str
    password: str


class TokenResponse(BaseModel):
    """Token response model."""
    access_token: str
    token_type: str = "bearer"
    user: UserModel
    organization: OrganizationModel


class CloudAccountModel(BaseModel):
    """Cloud account model."""
    id: Optional[int] = None
    organization_id: int
    provider: str  # aws, azure, gcp
    account_name: str
    account_id: str
    region: Optional[str] = None
    is_active: bool = True
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        from_attributes = True


class UsageDataModel(BaseModel):
    """Usage data model."""
    id: Optional[int] = None
    organization_id: int
    cloud_account_id: Optional[int] = None
    resource_type: str
    quantity: float
    unit: str
    region: str
    cost: Optional[float] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        from_attributes = True


class CarbonResultModel(BaseModel):
    """Carbon calculation result model."""
    id: Optional[int] = None
    organization_id: int
    energy_kwh: float
    carbon_kg_co2: float
    compute_energy: Optional[float] = None
    storage_energy: Optional[float] = None
    network_energy: Optional[float] = None
    region: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        from_attributes = True


class RecommendationModel(BaseModel):
    """Recommendation model."""
    id: Optional[int] = None
    organization_id: int
    suggestion: str
    carbon_saving_percent: Optional[float] = None
    cost_impact: Optional[float] = None
    priority: str = "medium"  # low, medium, high
    is_implemented: bool = False
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        from_attributes = True


class APIKeyModel(BaseModel):
    """API key model."""
    id: Optional[int] = None
    user_id: int
    key: str
    name: str
    is_active: bool = True
    last_used: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        from_attributes = True

