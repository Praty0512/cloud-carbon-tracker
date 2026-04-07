"""Generate Fake Dataset page."""

import streamlit as st

from utils.fake_data_generator import generate_fake_usage


def show():
    """Display the Generate Fake Dataset page."""
    st.header("Generate Cloud Usage Dataset")

    rows = st.slider("Dataset Size", min_value=10, max_value=500, value=100)

    if st.button("Generate Dataset", use_container_width=True):
        try:
            df = generate_fake_usage(rows)
            st.subheader("Generated Data Preview")
            st.dataframe(df, use_container_width=True)

            csv_data = df.to_csv(index=False)
            st.download_button(
                label="Download Dataset as CSV",
                data=csv_data,
                file_name="cloud_usage.csv",
                mime="text/csv",
                use_container_width=True,
            )
        except Exception as exc:
            st.error(f"Error generating dataset: {exc}")
