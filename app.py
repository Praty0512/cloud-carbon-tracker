import streamlit as st
import pandas as pd
import plotly.express as px
import numpy as np

from engine.carbon_engine import calculate_carbon
from engine.recommendation_engine import get_recommendations
from engine.simulation_engine import simulate
from utils.fake_data_generator import generate_fake_usage
from analytics.multicloud import multicloud_emissions
from analytics.scorecard import sustainability_scorecard
from analytics.analytics import (
    carbon_by_region,
    energy_breakdown,
    emission_trend
)

st.set_page_config(layout="wide")

st.title("🌱 Cloud Carbon Footprint Analytics Platform")

menu = st.sidebar.radio(
    "Navigation",
    [
        "Carbon Calculator",
        "Generate Fake Dataset",
        "Upload Dataset Analytics",
        "Region Simulation",
        "Carbon Forecast",
        "Multi‑Cloud Comparison",
        "Sustainability Scorecard"
    ]
)

# --------------------------------------------------
# CARBON CALCULATOR
# --------------------------------------------------

if menu == "Carbon Calculator":

    st.header("Carbon Footprint Calculator")

    col1, col2 = st.columns(2)

    with col1:
        vm = st.number_input("VM Hours", 0.0)
        storage = st.number_input("Storage (GB)", 0.0)

    with col2:
        network = st.number_input("Network (GB)", 0.0)
        region = st.selectbox(
            "Region",
            ["india", "us", "europe"]
        )

    if st.button("Calculate Carbon"):

        energy, carbon, compute, storage_e, network_e = calculate_carbon(
            vm, storage, network, region
        )

        col1, col2, col3 = st.columns(3)

        col1.metric("Energy (kWh)", round(energy,2))
        col2.metric("Carbon (kg CO₂)", round(carbon,2))
        col3.metric("Sustainability Score", max(0,100-int(carbon/2)))

        st.subheader("Energy Breakdown")

        fig = energy_breakdown(compute, storage_e, network_e)
        st.plotly_chart(fig)

        recs = get_recommendations(vm, storage, region, carbon)

        st.subheader("Optimization Suggestions")

        for r in recs:
            st.write("•", r)

# --------------------------------------------------
# GENERATE DATASET
# --------------------------------------------------

elif menu == "Generate Fake Dataset":

    st.header("Generate Fake Cloud Usage Dataset")

    rows = st.slider("Dataset Size", 10, 500, 100)

    df = generate_fake_usage(rows)

    st.dataframe(df)

    st.download_button(
        "Download Dataset",
        df.to_csv(index=False),
        "cloud_usage.csv"
    )

# --------------------------------------------------
# DATASET ANALYTICS
# --------------------------------------------------

elif menu == "Upload Dataset Analytics":

    st.header("Upload Cloud Usage Dataset")

    file = st.file_uploader("Upload CSV")

    if file:

        df = pd.read_csv(file)

        # calculate carbon for dataset
        carbon_list = []

        for _, row in df.iterrows():

            energy, carbon, _, _, _ = calculate_carbon(
                row["vm_hours"],
                row["storage_gb"],
                row["network_gb"],
                row["region"]
            )

            carbon_list.append(carbon)

        df["carbon"] = carbon_list

        st.subheader("Dataset Preview")
        st.dataframe(df)

        # region comparison
        st.subheader("Carbon Emissions by Region")

        region_chart = df.groupby("region")["carbon"].sum().reset_index()

        fig = px.bar(
            region_chart,
            x="region",
            y="carbon",
            title="Total Carbon Emissions by Region"
        )

        st.plotly_chart(fig)

        # emission trend
        st.subheader("Carbon Emission Trend")

        if "timestamp" in df.columns:
            fig = px.line(
                df,
                x="timestamp",
                y="carbon",
                title="Emission Trend Over Time"
            )
            st.plotly_chart(fig)

# --------------------------------------------------
# REGION SIMULATION
# --------------------------------------------------

elif menu == "Region Simulation":

    st.header("Cost vs Carbon Simulation")

    vm = st.number_input("VM Hours")
    storage = st.number_input("Storage GB")
    network = st.number_input("Network GB")

    if st.button("Run Simulation"):

        results = simulate(vm, storage, network)

        df = pd.DataFrame(results)

        st.dataframe(df)

        fig = px.bar(
            df,
            x="Region",
            y=["Carbon","Cost"],
            barmode="group",
            title="Cost vs Carbon Comparison"
        )

        st.plotly_chart(fig)

# --------------------------------------------------
# CARBON FORECAST (ML)
# --------------------------------------------------

elif menu == "Carbon Forecast":

    st.header("Carbon Emission Forecast (Next 6 Months)")

    file = st.file_uploader("Upload Dataset for Forecast")

    if file:

        df = pd.read_csv(file)

        # compute carbon if not present
        if "carbon" not in df.columns:

            carbon_values = []

            for _, row in df.iterrows():

                energy, carbon, _, _, _ = calculate_carbon(
                    row["vm_hours"],
                    row["storage_gb"],
                    row["network_gb"],
                    row["region"]
                )

                carbon_values.append(carbon)

            df["carbon"] = carbon_values

        df = df.sort_values("timestamp")

        df["time_index"] = range(len(df))

        # simple regression
        x = df["time_index"]
        y = df["carbon"]

        coef = np.polyfit(x, y, 1)
        poly = np.poly1d(coef)

        future_index = np.arange(len(df), len(df)+6)

        future_carbon = poly(future_index)

        forecast_df = pd.DataFrame({
            "time_index": future_index,
            "carbon": future_carbon
        })

        st.subheader("Forecast Graph")

        fig = px.line()

        fig.add_scatter(
            x=df["time_index"],
            y=df["carbon"],
            mode="lines",
            name="Historical"
        )

        fig.add_scatter(
            x=forecast_df["time_index"],
            y=forecast_df["carbon"],
            mode="lines",
            name="Forecast"
        )

        st.plotly_chart(fig)

# --------------------------------------------------
# MULTI‑CLOUD COMPARISON
# --------------------------------------------------

elif menu == "Multi‑Cloud Comparison":

    st.header("Multi‑Cloud Carbon Comparison")

    vm = st.number_input("VM Hours")
    storage = st.number_input("Storage (GB)")
    network = st.number_input("Network (GB)")

    if st.button("Compare Clouds"):

        df = multicloud_emissions(vm, storage, network)

        st.dataframe(df)

        fig = px.bar(
            df,
            x="Cloud Provider",
            y="Carbon Emissions",
            color="Cloud Provider",
            title="Carbon Emissions by Cloud Provider"
        )

        st.plotly_chart(fig)

# --------------------------------------------------
# SUSTAINABILITY SCORECARD
# --------------------------------------------------

elif menu == "Sustainability Scorecard":

    st.header("Sustainability Scorecard Dashboard")

    file = st.file_uploader("Upload Dataset")

    if file:

        df = pd.read_csv(file)

        carbon_values = []

        for _, row in df.iterrows():

            energy, carbon, _, _, _ = calculate_carbon(
                row["vm_hours"],
                row["storage_gb"],
                row["network_gb"],
                row["region"]
            )

            carbon_values.append(carbon)

        df["carbon"] = carbon_values

        scorecard = sustainability_scorecard(df)

        col1, col2, col3 = st.columns(3)

        col1.metric("Total Carbon", scorecard["Total Carbon"])
        col2.metric("Average Carbon", scorecard["Average Carbon"])
        col3.metric("Sustainability Score", scorecard["Sustainability Score"])

        st.subheader("Region Distribution")

        region_df = pd.DataFrame(
            scorecard["Region Distribution"].items(),
            columns=["Region","Count"]
        )

        st.plotly_chart(
            px.pie(region_df, names="Region", values="Count")
        )