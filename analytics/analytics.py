"""Analytics module for visualizations."""

import plotly.express as px
import pandas as pd


def energy_breakdown(compute, storage, network):
    """Create pie chart showing energy consumption breakdown."""
    df = pd.DataFrame({
        "Type": ["Compute", "Storage", "Network"],
        "Energy": [compute, storage, network]
    })

    fig = px.pie(
        df,
        names="Type",
        values="Energy",
        title="Energy Consumption Breakdown"
    )
    return fig