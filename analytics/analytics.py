import plotly.express as px

def carbon_by_region(df):

    fig=px.bar(
        df,
        x="region",
        y="carbon",
        title="Carbon Emissions by Region"
    )

    return fig


def energy_breakdown(compute,storage,network):

    import pandas as pd

    df=pd.DataFrame({
        "Type":["Compute","Storage","Network"],
        "Energy":[compute,storage,network]
    })

    fig=px.pie(
        df,
        names="Type",
        values="Energy",
        title="Energy Consumption Breakdown"
    )

    return fig


def emission_trend(df):

    fig=px.line(
        df,
        x="timestamp",
        y="carbon",
        title="Carbon Emission Trend"
    )

    return fig