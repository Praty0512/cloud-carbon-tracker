"""Carbon calculation API routes."""

from fastapi import APIRouter, HTTPException, Depends
from database.service import CarbonResultService, UsageDataService
from engine.carbon_engine import calculate_carbon
from api.routes.auth import get_current_org

router = APIRouter()


@router.post("/calculate")
def calculate_carbon_endpoint(
    vm_hours: float,
    storage_gb: float,
    network_gb: float,
    region: str,
    org_id: int = Depends(get_current_org)
) -> dict:
    """Calculate carbon emissions for given resources.
    
    Args:
        vm_hours: Virtual machine hours
        storage_gb: Storage in GB
        network_gb: Network transfer in GB
        region: Cloud region (india, us, europe)
        org_id: Organization ID
        
    Returns:
        Carbon calculation result
    """
    try:
        # Use existing carbon engine
        energy, carbon, compute, storage_e, network_e = calculate_carbon(
            vm_hours, storage_gb, network_gb, region
        )
        
        # Save to database
        result = CarbonResultService.create_carbon_result(
            org_id=org_id,
            energy_kwh=energy,
            carbon_kg_co2=carbon,
            compute_energy=compute,
            storage_energy=storage_e,
            network_energy=network_e,
            region=region
        )
        
        return {
            "id": result.id,
            "org_id": result.organization_id,
            "energy_kwh": result.energy_kwh,
            "carbon_kg_co2": result.carbon_kg_co2,
            "compute_energy": result.compute_energy,
            "storage_energy": result.storage_energy,
            "network_energy": result.network_energy,
            "region": result.region,
            "timestamp": result.timestamp.isoformat()
        }
        
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/usage")
def log_usage_data(
    resource_type: str,
    quantity: float,
    unit: str,
    region: str,
    cost: float = None,
    cloud_account_id: int = None,
    org_id: int = Depends(get_current_org)
) -> dict:
    """Log cloud usage data.
    
    Args:
        org_id: Organization ID
        resource_type: Type of resource (ec2, s3, etc.)
        quantity: Quantity of resource
        unit: Unit of measurement (hours, gb, etc.)
        region: Cloud region
        cost: Cost (optional)
        cloud_account_id: Cloud account ID (optional)
        
    Returns:
        Created usage data record
    """
    try:
        usage = UsageDataService.create_usage_data(
            org_id=org_id,
            resource_type=resource_type,
            quantity=quantity,
            unit=unit,
            region=region,
            cost=cost,
            cloud_account_id=cloud_account_id
        )
        
        return {
            "id": usage.id,
            "org_id": usage.organization_id,
            "resource_type": usage.resource_type,
            "quantity": usage.quantity,
            "unit": usage.unit,
            "region": usage.region,
            "cost": usage.cost,
            "timestamp": usage.timestamp.isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/history")
def get_history(days: int = 30, org_id: int = Depends(get_current_org)) -> dict:
    """Get carbon calculation history for organization.
    
    Args:
        org_id: Organization ID
        days: Number of days to retrieve (default 30)
        
    Returns:
        List of carbon results
    """
    results = CarbonResultService.get_org_carbon_history(org_id, days)
    return {
        "org_id": org_id,
        "days": days,
        "count": len(results),
        "results": [
            {
                "id": r.id,
                "carbon_kg_co2": r.carbon_kg_co2,
                "energy_kwh": r.energy_kwh,
                "region": r.region,
                "timestamp": r.timestamp.isoformat()
            }
            for r in results
        ]
    }


@router.get("/total")
def get_total_carbon(days: int = 30, org_id: int = Depends(get_current_org)) -> dict:
    """Get total carbon for organization.
    
    Args:
        org_id: Organization ID
        days: Number of days (default 30)
        
    Returns:
        Total carbon emissions
    """
    total = CarbonResultService.get_total_carbon(org_id, days)
    return {
        "org_id": org_id,
        "days": days,
        "total_carbon_kg_co2": total
    }

