"""Sustainability scorecard and metrics."""

import pandas as pd


def sustainability_scorecard(df):
    """Generate sustainability metrics from dataset.
    
    Args:
        df: DataFrame with carbon column
        
    Returns:
        Dictionary with sustainability metrics
    """
    total_carbon = df["carbon"].sum()
    avg_carbon = df["carbon"].mean()
    region_counts = df["region"].value_counts().to_dict()
    
    # Score: 100 minus half the average carbon
    score = max(0, 100 - int(avg_carbon))

    return {
        "Total Carbon": round(total_carbon, 2),
        "Average Carbon": round(avg_carbon, 2),
        "Sustainability Score": score,
        "Region Distribution": region_counts
    }