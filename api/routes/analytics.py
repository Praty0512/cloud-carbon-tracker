"""Analytics API routes."""

from fastapi import APIRouter, Depends
from database.service import CarbonResultService
from api.routes.auth import get_current_org

router = APIRouter()


@router.get("/trends")
def get_carbon_trends(days: int = 30, org_id: int = Depends(get_current_org)) -> dict:
    """Get carbon emission trends over time.
    
    Args:
        org_id: Organization ID
        days: Number of days to analyze
        
    Returns:
        Trend data with timestamps and values
    """
    results = CarbonResultService.get_org_carbon_history(org_id, days)
    
    return {
        "org_id": org_id,
        "days": days,
        "trend_data": [
            {
                "timestamp": r.timestamp.isoformat(),
                "carbon": r.carbon_kg_co2,
                "energy": r.energy_kwh,
                "region": r.region
            }
            for r in results
        ]
    }


@router.get("/summary")
def get_analytics_summary(days: int = 30, org_id: int = Depends(get_current_org)) -> dict:
    """Get analytics summary for organization.
    
    Args:
        org_id: Organization ID
        days: Period to analyze
        
    Returns:
        Summary metrics
    """
    results = CarbonResultService.get_org_carbon_history(org_id, days)
    
    if not results:
        return {
            "org_id": org_id,
            "days": days,
            "total_carbon": 0,
            "avg_carbon": 0,
            "total_energy": 0,
            "data_points": 0
        }
    
    total_carbon = sum(r.carbon_kg_co2 for r in results)
    total_energy = sum(r.energy_kwh for r in results)
    avg_carbon = total_carbon / len(results) if results else 0
    
    return {
        "org_id": org_id,
        "days": days,
        "total_carbon": total_carbon,
        "avg_carbon": avg_carbon,
        "total_energy": total_energy,
        "data_points": len(results)
    }

