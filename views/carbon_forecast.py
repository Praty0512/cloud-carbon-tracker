"""AI forecasting workspace for carbon telemetry."""

from __future__ import annotations

from datetime import datetime
import math

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from database.service import (
    ActionItemService,
    ActivityService,
    AlertService,
    AuditLogService,
    CarbonResultService,
    ForecastModelService,
    MembershipService,
    SavedReportService,
)
from engine.carbon_engine import calculate_carbon
from utils.demo_workspace import build_demo_telemetry
from utils.dataset_adapter import normalize_cloud_carbon_dataframe, summarize_dataset_fit


def _prepare_daily_series(df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate normalized telemetry into a daily carbon time series."""
    daily = (
        df.assign(day=pd.to_datetime(df["timestamp"]).dt.floor("D"))
        .groupby("day", as_index=False)
        .agg(
            carbon=("carbon", "sum"),
            energy_kwh=("energy_kwh", "sum"),
            cost=("cost", "sum"),
        )
        .sort_values("day")
        .reset_index(drop=True)
    )
    return daily


def _build_feature_frame(series_df: pd.DataFrame) -> pd.DataFrame:
    """Create lag and calendar features for a lightweight autoregressive model."""
    frame = series_df.copy()
    frame["index"] = np.arange(len(frame), dtype=float)
    frame["lag_1"] = frame["carbon"].shift(1)
    frame["lag_3"] = frame["carbon"].shift(3)
    frame["lag_7"] = frame["carbon"].shift(7)
    frame["rolling_3"] = frame["carbon"].rolling(3).mean().shift(1)
    frame["rolling_7"] = frame["carbon"].rolling(7).mean().shift(1)
    frame["dow"] = frame["day"].dt.dayofweek.astype(float)
    frame["dow_sin"] = np.sin(2 * np.pi * frame["dow"] / 7.0)
    frame["dow_cos"] = np.cos(2 * np.pi * frame["dow"] / 7.0)
    return frame.dropna().reset_index(drop=True)


def _fit_regression_model(feature_df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray, float]:
    """Fit a simple autoregressive regression model with least squares."""
    feature_cols = ["index", "lag_1", "lag_3", "lag_7", "rolling_3", "rolling_7", "dow_sin", "dow_cos"]
    x_matrix = feature_df[feature_cols].to_numpy(dtype=float)
    x_matrix = np.hstack([np.ones((len(x_matrix), 1)), x_matrix])
    y_vector = feature_df["carbon"].to_numpy(dtype=float)
    coefficients, *_ = np.linalg.lstsq(x_matrix, y_vector, rcond=None)
    fitted = x_matrix @ coefficients
    residual_std = float(np.std(y_vector - fitted)) if len(y_vector) > 1 else 0.0
    return coefficients, fitted, residual_std


def _recursive_forecast(
    daily_df: pd.DataFrame,
    coefficients: np.ndarray,
    horizon: int,
    growth_pct: float,
    reduction_pct: float,
) -> pd.DataFrame:
    """Generate future forecasts recursively using lagged predicted values."""
    history = daily_df[["day", "carbon"]].copy()
    forecasts: list[dict[str, float | pd.Timestamp]] = []
    feature_cols = ["index", "lag_1", "lag_3", "lag_7", "rolling_3", "rolling_7", "dow_sin", "dow_cos"]

    for step in range(horizon):
        next_day = history["day"].max() + pd.Timedelta(days=1)
        carbon_values = history["carbon"].tolist()
        lag_1 = carbon_values[-1]
        lag_3 = carbon_values[-3] if len(carbon_values) >= 3 else carbon_values[-1]
        lag_7 = carbon_values[-7] if len(carbon_values) >= 7 else carbon_values[-1]
        rolling_3 = float(np.mean(carbon_values[-3:]))
        rolling_7 = float(np.mean(carbon_values[-7:]))
        dow = float(next_day.dayofweek)
        feature_row = np.array(
            [
                1.0,
                float(len(history)),
                float(lag_1),
                float(lag_3),
                float(lag_7),
                float(rolling_3),
                float(rolling_7),
                math.sin(2 * math.pi * dow / 7.0),
                math.cos(2 * math.pi * dow / 7.0),
            ]
        )
        predicted = float(feature_row @ coefficients)
        predicted = max(predicted, 0.0)
        predicted *= 1 + (growth_pct / 100.0)
        predicted *= 1 - (reduction_pct / 100.0)
        history.loc[len(history)] = {"day": next_day, "carbon": predicted}
        forecasts.append({"day": next_day, "carbon": predicted})

    return pd.DataFrame(forecasts)


def _workspace_history(org_id: int) -> pd.DataFrame:
    """Build a normalized dataframe from persisted workspace carbon history."""
    records = CarbonResultService.get_org_carbon_history(org_id, days=365)
    if not records:
        return pd.DataFrame()
    return pd.DataFrame(
        [
            {
                "timestamp": record.timestamp,
                "carbon": record.carbon_kg_co2,
                "energy_kwh": record.energy_kwh,
                "cost": 0.0,
            }
            for record in records
        ]
    )


def show() -> None:
    """Display the AI forecast studio."""
    st.header("AI Forecast Studio")
    st.caption("Train a lightweight learning model on persisted or uploaded telemetry to project emissions and planning scenarios.")
    st.info(
        "This page estimates where carbon is heading based on historical telemetry. "
        "It is useful for planning reviews, optimization prioritization, and budget-risk conversations. "
        "Use workspace telemetry for organization-level forecasting, or upload a dataset to test a separate scenario."
    )

    org_id = st.session_state.get("current_org_id")
    user = st.session_state.get("current_user")
    can_write = MembershipService.has_permission(org_id, getattr(user, "id", 0), "forecast.write") if org_id else False

    source = st.radio(
        "Forecast data source",
        options=["Workspace telemetry", "Upload dataset", "Demo telemetry"],
        horizontal=True,
    )
    st.caption(
        "Workspace telemetry uses previously persisted portfolio history. Upload dataset is useful for one-off analysis. "
        "Demo telemetry is best for walkthroughs."
    )

    normalized_df = pd.DataFrame()
    source_name = "workspace telemetry"

    if source == "Workspace telemetry":
        if not org_id:
            st.warning("Select an organization to forecast from workspace telemetry.")
            return
        normalized_df = _workspace_history(org_id)
        if normalized_df.empty:
            st.info("No persisted telemetry yet. Import a dataset into the workspace first, or use an uploaded file below.")
            return
    else:
        if source == "Demo telemetry":
            normalized_df = build_demo_telemetry(days=90)
            source_name = "demo_telemetry"
        else:
            file = st.file_uploader("Upload CSV for Forecasting", type=["csv"])
            if file is None:
                st.info("Upload a telemetry file to train the forecasting model.")
                return
            raw_df = pd.read_csv(file)
            fit = summarize_dataset_fit(raw_df)
            normalized_df = normalize_cloud_carbon_dataframe(raw_df)
            if not fit["has_carbon"]:
                normalized_df["carbon"] = normalized_df.apply(
                    lambda row: calculate_carbon(
                        row["vm_hours"],
                        row["storage_gb"],
                        row["network_gb"],
                        row["region"],
                    )[1],
                    axis=1,
                )
            source_name = getattr(file, "name", "uploaded.csv")

    if normalized_df.empty or "timestamp" not in normalized_df.columns:
        st.warning("A timestamped carbon series is required for forecasting.")
        return

    daily_df = _prepare_daily_series(normalized_df)
    if len(daily_df) < 10:
        st.warning("At least 10 daily points are needed to train the forecasting model.")
        return

    feature_df = _build_feature_frame(daily_df)
    if len(feature_df) < 5:
        st.warning("Not enough lagged history was found after feature engineering.")
        return

    scenario_col1, scenario_col2, scenario_col3 = st.columns(3)
    horizon = scenario_col1.slider("Forecast horizon (days)", min_value=7, max_value=90, value=30, step=1)
    growth_pct = scenario_col2.slider("Expected workload growth %", min_value=-10, max_value=30, value=5, step=1)
    reduction_pct = scenario_col3.slider("Planned optimization reduction %", min_value=0, max_value=30, value=8, step=1)
    st.caption(
        "Expected workload growth increases forecasted demand. Planned optimization reduction reflects actions such as rightsizing, scheduling, or regional rebalancing."
    )

    coefficients, fitted_values, residual_std = _fit_regression_model(feature_df)
    forecast_df = _recursive_forecast(
        daily_df=daily_df,
        coefficients=coefficients,
        horizon=horizon,
        growth_pct=float(growth_pct),
        reduction_pct=float(reduction_pct),
    )

    evaluation_actual = feature_df["carbon"].to_numpy(dtype=float)
    mae = float(np.mean(np.abs(evaluation_actual - fitted_values)))
    mape = float(
        np.mean(
            np.where(
                evaluation_actual == 0,
                0.0,
                np.abs((evaluation_actual - fitted_values) / evaluation_actual),
            )
        )
        * 100
    )

    forecast_df["lower_bound"] = np.maximum(forecast_df["carbon"] - residual_std * 1.28, 0.0)
    forecast_df["upper_bound"] = forecast_df["carbon"] + residual_std * 1.28

    st.subheader("Model Performance")
    st.caption("These metrics describe how well the current model fits the available training history.")
    perf_col1, perf_col2, perf_col3, perf_col4 = st.columns(4)
    perf_col1.metric("Training Days", len(daily_df))
    perf_col2.metric("MAE", f"{mae:.2f} kg CO2")
    perf_col3.metric("MAPE", f"{mape:.1f}%")
    perf_col4.metric("Projected Horizon Total", f"{forecast_df['carbon'].sum():.0f} kg CO2")

    st.subheader("Historical vs Forecast")
    st.caption("The chart shows historical emissions, forecasted emissions, and a simple confidence band around the forecast.")
    figure = go.Figure()
    figure.add_trace(
        go.Scatter(
            x=daily_df["day"],
            y=daily_df["carbon"],
            mode="lines+markers",
            name="Historical carbon",
            line=dict(color="#38bdf8", width=2),
        )
    )
    figure.add_trace(
        go.Scatter(
            x=forecast_df["day"],
            y=forecast_df["carbon"],
            mode="lines+markers",
            name="AI forecast",
            line=dict(color="#22c55e", width=3),
        )
    )
    figure.add_trace(
        go.Scatter(
            x=forecast_df["day"],
            y=forecast_df["upper_bound"],
            mode="lines",
            line=dict(width=0),
            showlegend=False,
            hoverinfo="skip",
        )
    )
    figure.add_trace(
        go.Scatter(
            x=forecast_df["day"],
            y=forecast_df["lower_bound"],
            mode="lines",
            fill="tonexty",
            fillcolor="rgba(34, 197, 94, 0.18)",
            line=dict(width=0),
            name="Confidence band",
            hoverinfo="skip",
        )
    )
    figure.update_layout(
        title="Forecasted Portfolio Carbon",
        xaxis_title="Date",
        yaxis_title="Carbon (kg CO2)",
        margin=dict(l=20, r=20, t=55, b=20),
    )
    st.plotly_chart(figure, use_container_width=True)

    st.subheader("Scenario Summary")
    st.caption("Use this summary to compare the latest actual performance with the projected future trajectory.")
    summary_col1, summary_col2, summary_col3 = st.columns(3)
    summary_col1.metric("Last Actual Day", f"{daily_df['carbon'].iloc[-1]:.1f} kg CO2")
    summary_col2.metric("Forecast Day 30" if horizon >= 30 else f"Forecast Day {horizon}", f"{forecast_df['carbon'].iloc[-1]:.1f} kg CO2")
    summary_col3.metric("Residual Volatility", f"{residual_std:.2f} kg CO2")

    forecast_table = forecast_df.copy()
    forecast_table["day"] = forecast_table["day"].dt.strftime("%Y-%m-%d")
    st.dataframe(
        forecast_table.rename(
            columns={
                "day": "Date",
                "carbon": "Forecast Carbon (kg CO2)",
                "lower_bound": "Lower Bound",
                "upper_bound": "Upper Bound",
            }
        ),
        use_container_width=True,
    )

    if org_id:
        report_summary = (
            f"Forecasted {forecast_df['carbon'].sum():.0f} kg CO2 over the next {horizon} days "
            f"using {len(daily_df)} days of history from {source_name}."
        )
        if st.button("Save Forecast To Workspace", use_container_width=True, disabled=not can_write):
            model_run = ForecastModelService.create_model_run(
                org_id=org_id,
                name=f"AI Forecast {datetime.utcnow().strftime('%Y-%m-%d %H:%M')}",
                source_type=source_name,
                training_rows=len(daily_df),
                horizon_days=horizon,
                mae=mae,
                mape=mape,
                residual_std=residual_std,
                metadata_json={
                    "growth_pct": growth_pct,
                    "reduction_pct": reduction_pct,
                    "projected_total_carbon": float(forecast_df["carbon"].sum()),
                },
                created_by=getattr(user, "id", None),
            )
            SavedReportService.create_report(
                org_id=org_id,
                title="AI Forecast Outlook",
                report_type="forecast",
                summary=report_summary,
                payload={
                    "source": source_name,
                    "horizon_days": horizon,
                    "mae": mae,
                    "mape": mape,
                    "growth_pct": growth_pct,
                    "reduction_pct": reduction_pct,
                    "projected_total_carbon": float(forecast_df["carbon"].sum()),
                },
                created_by=getattr(user, "id", None),
            )
            ActivityService.log_event(
                org_id=org_id,
                user_id=getattr(user, "id", None),
                event_type="forecast",
                title="AI forecast generated",
                description=report_summary,
                metadata_json={"horizon_days": horizon, "mae": round(mae, 2), "mape": round(mape, 2)},
            )
            AuditLogService.log(
                org_id=org_id,
                user_id=getattr(user, "id", None),
                action="forecast.model_saved",
                entity_type="forecast_model",
                entity_id=str(model_run["id"]),
                description=report_summary,
                metadata_json={"mae": mae, "mape": mape, "horizon_days": horizon},
            )
            if forecast_df["carbon"].sum() > daily_df["carbon"].sum() * 0.35:
                alert = AlertService.create_alert(
                    org_id=org_id,
                    title="Forecast indicates elevated carbon trajectory",
                    description="Projected horizon total suggests sustained emissions pressure over the selected planning window.",
                    category="forecast",
                    severity="medium",
                    metric_value=float(forecast_df["carbon"].sum()),
                    threshold_value=float(daily_df["carbon"].sum() * 0.35),
                    metadata_json={"source": source_name, "horizon_days": horizon},
                )
                ActionItemService.create_action_item(
                    org_id=org_id,
                    alert_id=alert["id"],
                    title="Review forecast-driven optimization plan",
                    description="Validate whether forecasted carbon growth should trigger portfolio changes.",
                    owner_user_id=getattr(user, "id", None),
                    priority="medium",
                )
            st.success("Forecast saved to the workspace reports library.")
