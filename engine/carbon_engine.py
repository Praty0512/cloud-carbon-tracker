"""Carbon emission calculation engine."""

from config import COMPUTE_FACTOR, NETWORK_FACTOR, STORAGE_FACTOR, get_region_intensity, resolve_region_key


def calculate_energy(vm, storage, network):
    """Calculate total energy consumption from cloud resources.
    
    Args:
        vm: Virtual machine hours
        storage: Storage in GB
        network: Network transfer in GB
        
    Returns:
        Tuple: (total_energy, compute_energy, storage_energy, network_energy) in kWh
    """
    compute = vm * COMPUTE_FACTOR
    storage_e = storage * STORAGE_FACTOR
    network_e = network * NETWORK_FACTOR
    total = compute + storage_e + network_e

    return total, compute, storage_e, network_e


def calculate_carbon(vm, storage, network, region):
    """Calculate carbon emissions from cloud usage.
    
    Args:
        vm: Virtual machine hours
        storage: Storage in GB
        network: Network transfer in GB
        region: Region or provider region string
        
    Returns:
        Tuple: (energy, carbon, compute, storage_energy, network_energy)
    """
    energy, compute, storage_e, network_e = calculate_energy(vm, storage, network)
    carbon = energy * get_region_intensity(region)

    return energy, carbon, compute, storage_e, network_e


def get_carbon_region_key(region):
    """Return the resolved lookup key used for carbon intensity."""
    return resolve_region_key(region)
