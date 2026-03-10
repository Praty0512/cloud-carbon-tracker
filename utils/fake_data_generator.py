import pandas as pd
import random
from faker import Faker

fake = Faker()

regions = ["india","us","europe"]

def generate_fake_usage(rows=50):

    data = []

    for _ in range(rows):

        vm = random.randint(50,200)
        storage = random.randint(100,1000)
        network = random.randint(50,500)

        region = random.choice(regions)

        data.append({
            "timestamp":fake.date_this_year(),
            "vm_hours":vm,
            "storage_gb":storage,
            "network_gb":network,
            "region":region
        })

    return pd.DataFrame(data)