"""Pydantic schemas for API validation and serialization."""

from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List
from datetime import datetime


# User Schemas
class UserBase(BaseModel):
    """Base user schema."""
    email: EmailStr
    full_name: Optional[str] = None


class UserCreate(UserBase):
    """Schema for creating a user."""
    password: str = Field(..., min_length=8)


class UserResponse(UserBase):
    """Schema for user response."""
    id: int
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


# Organization Schemas
class OrganizationBase(BaseModel):
    """Base organization schema."""
    name: str
    description: Optional[str] = None


class OrganizationCreate(OrganizationBase):
    """Schema for creating organization."""
    pass


class OrganizationResponse(OrganizationBase):
    """Schema for organization response."""
    id: int
    owner_id: int
    created_at: datetime

    class Config:
        from_attributes = True


# Usage Data Schemas
class UsageDataBase(BaseModel):
    """Base usage data schema."""
    resource_type: str
    quantity: float
    unit: str
    region: str
    cost: Optional[float] = None


class UsageDataCreate(UsageDataBase):
    """Schema for creating usage data."""
    cloud_account_id: Optional[int] = None


class UsageDataResponse(UsageDataBase):
    """Schema for usage data response."""
    id: int
    organization_id: int
    timestamp: datetime
    created_at: datetime

    class Config:
        from_attributes = True


# Carbon Result Schemas
class CarbonResultBase(BaseModel):
    """Base carbon result schema."""
    energy_kwh: float
    carbon_kg_co2: float
    compute_energy: Optional[float] = None
    storage_energy: Optional[float] = None
    network_energy: Optional[float] = None
    region: Optional[str] = None


class CarbonResultCreate(CarbonResultBase):
    """Schema for creating carbon result."""
    pass


class CarbonResultResponse(CarbonResultBase):
    """Schema for carbon result response."""
    id: int
    organization_id: int
    timestamp: datetime
    created_at: datetime

    class Config:
        from_attributes = True


# Recommendation Schemas
class RecommendationBase(BaseModel):
    """Base recommendation schema."""
    suggestion: str
    carbon_saving_percent: Optional[float] = None
    cost_impact: Optional[float] = None
    priority: str = "medium"


class RecommendationCreate(RecommendationBase):
    """Schema for creating recommendation."""
    pass


class RecommendationResponse(RecommendationBase):
    """Schema for recommendation response."""
    id: int
    organization_id: int
    is_implemented: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# Cloud Account Schemas
class CloudAccountBase(BaseModel):
    """Base cloud account schema."""
    provider: str
    account_name: str
    account_id: str
    region: Optional[str] = None


class CloudAccountCreate(CloudAccountBase):
    """Schema for creating cloud account."""
    pass


class CloudAccountResponse(CloudAccountBase):
    """Schema for cloud account response."""
    id: int
    organization_id: int
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True
