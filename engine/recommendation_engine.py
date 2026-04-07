"""Recommendation engine for carbon optimization suggestions."""


def get_recommendations(vm, storage, region, carbon):
    """Generate carbon optimization recommendations.
    
    Args:
        vm: Virtual machine hours
        storage: Storage in GB
        region: AWS region
        carbon: Total carbon emissions in kg CO2
        
    Returns:
        List of recommendation strings
    """
    recommendations = []

    if vm < 50:
        recommendations.append("💡 Use serverless compute for lower resource needs")

    if storage > 500:
        recommendations.append("💾 Move cold data to archival storage for cost savings")

    if region == "india":
        recommendations.append("🌍 Consider deploying in Europe region to reduce carbon emissions")

    if carbon > 100:
        recommendations.append("⚙️ Optimize VM allocation and resource utilization")

    return recommendations