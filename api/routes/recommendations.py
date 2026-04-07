"""Recommendations API routes."""

from fastapi import APIRouter, Depends
from database.service import RecommendationService
from api.routes.auth import get_current_org

router = APIRouter()


@router.get("/")
def get_org_recommendations(implemented: bool = False, org_id: int = Depends(get_current_org)) -> dict:
    """Get recommendations for organization.
    
    Args:
        org_id: Organization ID
        implemented: Filter by implementation status
        
    Returns:
        List of recommendations
    """
    recommendations = RecommendationService.get_org_recommendations(org_id, implemented)
    
    return {
        "org_id": org_id,
        "count": len(recommendations),
        "recommendations": [
            {
                "id": r.id,
                "suggestion": r.suggestion,
                "carbon_saving_percent": r.carbon_saving_percent,
                "cost_impact": r.cost_impact,
                "priority": r.priority,
                "implemented": r.is_implemented,
                "created_at": r.created_at.isoformat() if r.created_at else None
            }
            for r in recommendations
        ]
    }


@router.post("/")
def create_recommendation(
    suggestion: str,
    carbon_saving_percent: float,
    cost_impact: float,
    priority: str = "medium",
    org_id: int = Depends(get_current_org)
) -> dict:
    """Create new recommendation.
    
    Args:
        org_id: Organization ID
        suggestion: Recommendation text
        carbon_saving_percent: Estimated carbon saved percentage
        cost_impact: Estimated cost impact
        priority: Priority level (low/medium/high)
        
    Returns:
        Created recommendation
    """
    recommendation = RecommendationService.create_recommendation(
        org_id=org_id,
        suggestion=suggestion,
        carbon_saving_percent=carbon_saving_percent,
        cost_impact=cost_impact,
        priority=priority,
        implemented=False
    )
    
    return {
        "id": recommendation.id,
        "org_id": recommendation.organization_id,
        "suggestion": recommendation.suggestion,
        "carbon_saving_percent": recommendation.carbon_saving_percent,
        "cost_impact": recommendation.cost_impact,
        "priority": recommendation.priority,
        "implemented": recommendation.is_implemented,
        "created_at": recommendation.created_at.isoformat() if recommendation.created_at else None
    }
