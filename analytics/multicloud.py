"""Multi-cloud carbon emission analysis."""

import pandas as pd
from config import CLOUD_PROVIDERS


def multicloud_emissions(vm_hours, storage_gb, network_gb):
    """Calculate carbon emissions across different cloud providers.
    
    Args:
        vm_hours: Virtual machine hours
        storage_gb: Storage in GB
        network_gb: Network transfer in GB
        
    Returns:
        DataFrame with cloud provider and carbon emissions
    """
    # Calculate base energy consumption
    base_energy = (
        vm_hours * 0.5 +
        storage_gb * 0.0002 +
        network_gb * 0.0005
    )

    results = []

    for cloud, factor in CLOUD_PROVIDERS.items():
        carbon = base_energy * factor
        results.append({
            "Cloud Provider": cloud,
            "Carbon Emissions": round(carbon, 2)
        })

    return pd.DataFrame(results)