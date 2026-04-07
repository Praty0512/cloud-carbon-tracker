"""Multi-Cloud Comparison page."""

import plotly.express as px
import streamlit as st

from analytics.multicloud import multicloud_emissions


def show():
    """Display the Multi-Cloud Comparison page."""
    st.header("Multi-Cloud Carbon Comparison")

    col1, col2, col3 = st.columns(3)
    with col1:
        vm = st.number_input("VM Hours", value=0.0, min_value=0.0, key="mc_vm")
    with col2:
        storage = st.number_input("Storage (GB)", value=0.0, min_value=0.0, key="mc_storage")
    with col3:
        network = st.number_input("Network (GB)", value=0.0, min_value=0.0, key="mc_network")

    if st.button("Compare Clouds", use_container_width=True):
        try:
            df = multicloud_emissions(vm, storage, network)

            st.subheader("Comparison Results")
            st.dataframe(df, use_container_width=True)

            fig = px.bar(
                df,
                x="Cloud Provider",
                y="Carbon Emissions",
                color="Cloud Provider",
                title="Carbon Emissions by Cloud Provider",
                labels={"Carbon Emissions": "Carbon (kg CO2)"},
            )
            st.plotly_chart(fig, use_container_width=True)

            best_idx = df["Carbon Emissions"].idxmin()
            best_provider = df.loc[best_idx, "Cloud Provider"]
            best_carbon = df.loc[best_idx, "Carbon Emissions"]
            st.success(f"Best provider: {best_provider} ({best_carbon} kg CO2)")
        except Exception as exc:
            st.error(f"Error comparing clouds: {exc}")
