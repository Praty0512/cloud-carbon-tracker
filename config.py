"""Configuration and constants for the Carbon Tracker application."""

from __future__ import annotations
from dotenv import load_dotenv
load_dotenv()  # Load environment variables from .env file if available
import os
DATABASE_URL=os.getenv("DATABASE_URL")
import json
import re
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
with open(DATA_DIR / "region_intensity.json", encoding="utf-8") as file_handle:
    REGION_INTENSITY = json.load(file_handle)

COMPUTE_FACTOR = 0.5
STORAGE_FACTOR = 0.0002
NETWORK_FACTOR = 0.0005

CLOUD_COST = {
    "india": 0.10,
    "us": 0.12,
    "europe": 0.14,
    "singapore": 0.16,
    "japan_tokyo": 0.17,
    "australia_sydney": 0.18,
    "uae_dubai": 0.19,
}

REGIONS = ["india", "us", "europe"]

SCENARIO_REGIONS = [
    "india_mumbai",
    "india_delhi",
    "us_east_virginia",
    "us_west_oregon",
    "uk_london",
    "germany_frankfurt",
    "france_paris",
    "poland_warsaw",
    "singapore",
    "japan_tokyo",
    "australia_sydney",
    "uae_dubai",
]

REGION_LABELS = {
    "india": "India",
    "us": "United States",
    "europe": "Europe",
    "india_mumbai": "India - Mumbai",
    "india_delhi": "India - Delhi",
    "india_hyderabad": "India - Hyderabad",
    "us_east_virginia": "US East - Virginia",
    "us_west_oregon": "US West - Oregon",
    "us_central_iowa": "US Central - Iowa",
    "us_south_dallas": "US South - Dallas",
    "us_west_los_angeles": "US West - Los Angeles",
    "uk_london": "UK - London",
    "germany_frankfurt": "Germany - Frankfurt",
    "france_paris": "France - Paris",
    "poland_warsaw": "Poland - Warsaw",
    "singapore": "Singapore",
    "japan_tokyo": "Japan - Tokyo",
    "australia_sydney": "Australia - Sydney",
    "uae_dubai": "UAE - Dubai",
}

REGION_ALIAS_MAP = {
    "asia_south1": "india_mumbai",
    "asia_south2": "india_delhi",
    "mumbai": "india_mumbai",
    "delhi": "india_delhi",
    "hyderabad": "india_hyderabad",
    "centralindia": "india_hyderabad",
    "us_east1": "us_east_virginia",
    "us_east_1": "us_east_virginia",
    "us_east_2": "us_east_virginia",
    "us_west1": "us_west_oregon",
    "us_west_1": "us_west_oregon",
    "us_west2": "us_west_oregon",
    "us_west_2": "us_west_oregon",
    "us_central1": "us_central_iowa",
    "europe_west2": "uk_london",
    "london": "uk_london",
    "europe_west3": "germany_frankfurt",
    "frankfurt": "germany_frankfurt",
    "europe_west4": "netherlands_amsterdam",
    "europe_west1": "netherlands_amsterdam",
    "paris": "france_paris",
    "europe_west9": "france_paris",
    "warsaw": "poland_warsaw",
    "europe_central2": "poland_warsaw",
    "singapore": "singapore",
    "asia_northeast1": "japan_tokyo",
    "tokyo": "japan_tokyo",
    "sydney": "australia_sydney",
    "australia_southeast1": "australia_sydney",
    "dubai": "uae_dubai",
    "me_central_1": "uae_dubai",
}

CLOUD_PROVIDERS = {
    "AWS": 0.45,
    "GCP": 0.40,
    "Azure": 0.42,
}

PAGE_CONFIG = {
    "layout": "wide",
    "page_title": "Cloud Carbon Tracker",
    "page_icon": "C",
}

NAV_SECTIONS = {
    "Overview": "Start here for workspace posture, recent activity, and top priorities",
    "Portfolio Workspace": "Monitor project budgets, emissions, and regional operating exposure",
    "Operations Center": "Handle alerts, action items, and audit-backed operational follow-through",
    "Governance Center": "Review control health, reporting evidence, and optimization backlog",
    "Integrations Hub": "Connect cloud estates, configure ingestion, and manage API access",
    "Team Workspace": "Manage members, roles, and workspace administration responsibilities",
    "Upload Analytics": "Inspect and normalize imported telemetry before persisting it",
    "Scenario Planner": "Compare region options for workload placement, cost, and carbon",
    "AI Forecast Studio": "Project future emissions from historical telemetry and planning assumptions",
    "Executive Scorecards": "Create stakeholder-ready summaries from normalized telemetry",
}

PRODUCT_GLOSSARY = {
    "workspace": "The organization environment where teams monitor carbon, manage workflows, and review reports.",
    "connected_scope": "A billing account, subscription, cloud account, or project scope that the workspace tracks.",
    "connector": "A reusable ingestion definition that explains how telemetry should be collected from a provider or export.",
    "telemetry": "Normalized usage, cost, energy, and carbon records used by analytics, forecasting, and governance workflows.",
    "operating_region": "The exact normalized cloud region used for operational analysis and carbon intensity lookup.",
    "reporting_region": "The higher-level rollup region used in executive summaries and portfolio reporting.",
    "coverage_score": "A simple readiness score based on connected scopes, assigned members, and reporting activity.",
}

METRIC_COPY = {
    "portfolio_carbon": "Tracked carbon across the current portfolio.",
    "monthly_spend": "Estimated spend based on registered project budgets and current portfolio scope.",
    "coverage_score": PRODUCT_GLOSSARY["coverage_score"],
    "latest_telemetry": "The freshness of the most recent carbon telemetry available in the workspace.",
}


def normalize_region_key(region: object) -> str:
    """Normalize region strings into lookup-friendly keys."""
    text = str(region or "").strip().lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_")


def resolve_region_key(region: object) -> str:
    """Resolve a raw region string to the best available intensity key."""
    normalized = normalize_region_key(region)
    if normalized in REGION_INTENSITY:
        return normalized
    if normalized in REGION_ALIAS_MAP:
        return REGION_ALIAS_MAP[normalized]
    if normalized.startswith(("asia_", "ap_")):
        return "india"
    if normalized.startswith(("us_", "northamerica_")):
        return "us"
    if normalized.startswith(("europe_", "eu_")):
        return "europe"
    return normalized if normalized in REGION_INTENSITY else "us"


def get_region_intensity(region: object) -> float:
    """Return carbon intensity for a region with coarse fallback."""
    key = resolve_region_key(region)
    return float(REGION_INTENSITY.get(key, REGION_INTENSITY["us"]))


def get_region_cost(region: object) -> float:
    """Return a regional cost factor with fallback to coarse geography."""
    key = resolve_region_key(region)
    if key in CLOUD_COST:
        return float(CLOUD_COST[key])
    if key.startswith("india"):
        return float(CLOUD_COST["india"])
    if key.startswith(("us", "canada", "mexico", "brazil")):
        return float(CLOUD_COST["us"])
    return float(CLOUD_COST["europe"])


def get_region_label(region: object) -> str:
    """Return a UI-friendly region label."""
    key = resolve_region_key(region)
    return REGION_LABELS.get(key, key.replace("_", " ").title())
