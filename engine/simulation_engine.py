import json
from engine.carbon_engine import calculate_energy

with open("data/region_intensity.json") as f:
    REGION_INTENSITY=json.load(f)

CLOUD_COST={
"india":0.10,
"us":0.12,
"europe":0.14
}

def simulate(vm,storage,network):

    energy,_,_,_=calculate_energy(vm,storage,network)

    results=[]

    for region in REGION_INTENSITY:

        carbon=energy*REGION_INTENSITY[region]
        cost=vm*CLOUD_COST[region]

        results.append({
            "Region":region,
            "Carbon":round(carbon,2),
            "Cost":cost
        })

    return results