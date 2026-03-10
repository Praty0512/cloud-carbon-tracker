import pandas as pd

CLOUD_FACTORS = {
    "AWS": 0.45,
    "GCP": 0.40,
    "Azure": 0.42
}

def multicloud_emissions(vm_hours, storage_gb, network_gb):

    base_energy = (
        vm_hours * 0.5 +
        storage_gb * 0.0002 +
        network_gb * 0.0005
    )

    results = []

    for cloud, factor in CLOUD_FACTORS.items():

        carbon = base_energy * factor

        results.append({
            "Cloud Provider": cloud,
            "Carbon Emissions": round(carbon,2)
        })

    return pd.DataFrame(results)