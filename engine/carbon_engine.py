import json

with open("data/region_intensity.json") as f:
    REGION_INTENSITY = json.load(f)

COMPUTE_FACTOR = 0.5
STORAGE_FACTOR = 0.0002
NETWORK_FACTOR = 0.0005

def calculate_energy(vm,storage,network):

    compute = vm * COMPUTE_FACTOR
    storage_e = storage * STORAGE_FACTOR
    network_e = network * NETWORK_FACTOR

    total = compute + storage_e + network_e

    return total, compute, storage_e, network_e


def calculate_carbon(vm,storage,network,region):

    energy, compute, storage_e, network_e = calculate_energy(
        vm,storage,network
    )

    carbon = energy * REGION_INTENSITY[region]

    return energy, carbon, compute, storage_e, network_e