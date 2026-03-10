def get_recommendations(vm,storage,region,carbon):

    rec=[]

    if vm < 50:
        rec.append("Use serverless compute")

    if storage > 500:
        rec.append("Move cold data to archival storage")

    if region == "india":
        rec.append("Deploy in Europe region to reduce carbon")

    if carbon > 100:
        rec.append("Optimize VM allocation")

    return rec