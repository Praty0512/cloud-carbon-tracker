"""Main Streamlit application for Cloud Carbon Tracker."""

from __future__ import annotations
from datetime import datetime,UTC
import base64
from datetime import datetime
import hashlib
import hmac
import json
import os

import pandas as pd
import plotly.express as px
import plotly.io as pio
import streamlit as st

from config import METRIC_COPY, NAV_SECTIONS, PAGE_CONFIG, PRODUCT_GLOSSARY, get_region_label
from database.connection import init_db
from database.service import (
    ActivityService,
    AuditLogService,
    DashboardService,
    MembershipService,
    OrganizationService,
    ProjectService,
    RecommendationService,
    SavedReportService,
    UserService,
)
from views import (
    carbon_forecast,
    governance_center,
    integrations_hub,
    operations_center,
    portfolio_workspace,
    region_simulation,
    sustainability_scorecard,
    team_workspace,
    upload_analytics,
)

st.set_page_config(**PAGE_CONFIG)
init_db()
pio.templates.default = "plotly_dark"

SESSION_SECRET = os.getenv("STREAMLIT_SESSION_SECRET", "cloud-carbon-tracker-local-secret")
SESSION_MAX_AGE_SECONDS = 60 * 60 * 24 * 14


def _sign_session_payload(payload: dict[str, int | str]) -> str:
    """Create a signed session token for lightweight refresh persistence."""
    serialized = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    signature = hmac.new(SESSION_SECRET.encode("utf-8"), serialized, hashlib.sha256).hexdigest()
    encoded_payload = base64.urlsafe_b64encode(serialized).decode("utf-8").rstrip("=")
    return f"{encoded_payload}.{signature}"


def _read_session_payload(token: str | None) -> dict[str, int | str] | None:
    """Verify and decode a session token."""
    if not token or "." not in token:
        return None

    encoded_payload, signature = token.rsplit(".", 1)
    padding = "=" * (-len(encoded_payload) % 4)
    try:
        serialized = base64.urlsafe_b64decode(f"{encoded_payload}{padding}".encode("utf-8"))
    except Exception:
        return None

    expected_signature = hmac.new(
        SESSION_SECRET.encode("utf-8"),
        serialized,
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(signature, expected_signature):
        return None

    try:
        payload = json.loads(serialized.decode("utf-8"))
    except json.JSONDecodeError:
        return None

    expires_at = int(payload.get("exp", 0))
    if expires_at < int(datetime.utcnow().timestamp()):
        return None
    return payload


def persist_login(user_id: int, org_id: int | None, selected_page: str = "Overview") -> None:
    """Store session state in query params so refresh restores the workspace."""
    expires_at=int(datetime.now(UTC).timestamp())+SESSION_MAX_AGE_SECONDS
    token = _sign_session_payload({"uid": int(user_id), "org": int(org_id or 0), "exp": expires_at})
    st.query_params["session"] = token
    st.query_params["page"] = selected_page


def clear_persisted_login() -> None:
    """Remove persisted session values."""
    st.query_params.clear()


def hydrate_session_from_query_params() -> None:
    """Restore the signed-in user after a browser refresh."""
    if st.session_state.get("current_user"):
        return

    token = st.query_params.get("session")
    payload = _read_session_payload(token)
    if not payload:
        return

    user = UserService.get_user(int(payload["uid"]))
    if not user:
        clear_persisted_login()
        return

    organizations = OrganizationService.get_user_organizations(user.id)
    if not organizations:
        clear_persisted_login()
        return

    org_ids = {organization.id for organization in organizations}
    requested_org = int(payload.get("org", 0) or 0)
    resolved_org_id = requested_org if requested_org in org_ids else organizations[0].id

    st.session_state["current_user"] = user
    st.session_state["current_org_id"] = resolved_org_id
    st.session_state["selected_page"] = st.query_params.get("page", "Overview")


def inject_shell_styles() -> None:
    """Apply a richer SaaS visual layer."""
    st.markdown(
        """
        <style>
        .stApp {
            background:
                radial-gradient(circle at top left, rgba(71, 214, 179, 0.10), transparent 24%),
                radial-gradient(circle at 80% 0%, rgba(56, 189, 248, 0.12), transparent 18%),
                linear-gradient(180deg, #07111f 0%, #0b1525 48%, #0a1220 100%);
            color: #e8f1ff;
        }
        [data-testid="stAppViewContainer"] {
            color: #e8f1ff;
        }
        [data-testid="stHeader"] {
            background: rgba(7, 17, 31, 0.88);
            border-bottom: 1px solid rgba(148, 163, 184, 0.12);
        }
        [data-testid="stSidebar"] {
            background: linear-gradient(180deg, #081120 0%, #0d1728 100%);
            border-right: 1px solid rgba(148, 163, 184, 0.12);
        }
        [data-testid="stSidebar"] * {
            color: #e5eefc !important;
        }
        [data-testid="stSidebar"] [data-testid="stMetricValue"] {
            color: #ffffff !important;
        }
        [data-testid="stSidebar"] [data-baseweb="select"] > div {
            background: rgba(15, 23, 42, 0.92);
            border: 1px solid rgba(71, 85, 105, 0.78);
        }
        .hero-shell {
            padding: 1.5rem 1.6rem;
            border-radius: 24px;
            color: #f8fbff;
            background: linear-gradient(135deg, rgba(11, 30, 52, 0.96) 0%, rgba(16, 61, 86, 0.94) 58%, rgba(24, 121, 106, 0.92) 100%);
            box-shadow: 0 22px 44px rgba(2, 8, 23, 0.36);
            border: 1px solid rgba(125, 211, 252, 0.14);
            margin-bottom: 1rem;
        }
        .hero-shell h2 {
            margin: 0 0 0.35rem 0;
            font-size: 2rem;
        }
        .hero-shell p {
            margin: 0;
            max-width: 780px;
            opacity: 0.93;
        }
        .glass-card {
            background: linear-gradient(180deg, rgba(12, 22, 38, 0.94) 0%, rgba(10, 18, 32, 0.98) 100%);
            border: 1px solid rgba(71, 85, 105, 0.42);
            border-radius: 20px;
            padding: 1rem 1rem 0.75rem 1rem;
            box-shadow: 0 18px 30px rgba(2, 8, 23, 0.24);
            margin-bottom: 1rem;
        }
        .glass-card h3 {
            margin-top: 0;
            color: #f8fbff;
        }
        .metric-card {
            background: linear-gradient(180deg, rgba(17, 24, 39, 0.98) 0%, rgba(10, 18, 32, 1) 100%);
            border: 1px solid rgba(56, 189, 248, 0.18);
            border-radius: 18px;
            padding: 0.95rem 1rem;
            min-height: 116px;
            box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.02);
        }
        .metric-card .label {
            color: #7dd3fc;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            font-size: 0.78rem;
        }
        .metric-card .value {
            color: #f8fbff;
            font-size: 1.75rem;
            font-weight: 700;
            margin-top: 0.35rem;
        }
        .metric-card .meta {
            color: #a6b7d1;
            font-size: 0.92rem;
            margin-top: 0.3rem;
        }
        .tag-row {
            display: flex;
            flex-wrap: wrap;
            gap: 0.45rem;
            margin-top: 0.5rem;
        }
        .tag {
            display: inline-block;
            padding: 0.36rem 0.7rem;
            border-radius: 999px;
            background: rgba(20, 83, 116, 0.28);
            color: #c8f1ff;
            border: 1px solid rgba(125, 211, 252, 0.18);
            font-size: 0.83rem;
        }
        .auth-shell {
            max-width: 880px;
            margin: 0 auto;
            padding-top: 1rem;
        }
        .auth-panel {
            background: linear-gradient(180deg, rgba(10, 18, 32, 0.96) 0%, rgba(14, 24, 42, 0.96) 100%);
            border: 1px solid rgba(71, 85, 105, 0.44);
            border-radius: 22px;
            box-shadow: 0 16px 34px rgba(2, 8, 23, 0.28);
            padding: 1.2rem 1.2rem 0.6rem 1.2rem;
            margin-top: 1rem;
        }
        [data-testid="stTabs"] button {
            color: #9fb3c8 !important;
            font-weight: 600;
        }
        [data-testid="stTabs"] button[aria-selected="true"] {
            color: #f8fbff !important;
            border-bottom-color: #22c55e !important;
        }
        [data-testid="stForm"] {
            background: transparent;
            border: none;
            padding: 0;
        }
        [data-testid="stForm"] label,
        [data-testid="stTextInputRootElement"] label,
        [data-testid="stNumberInputRootElement"] label,
        [data-testid="stSelectbox"] label,
        [data-testid="stFileUploader"] label,
        .stMarkdown,
        .stCaption,
        .st-emotion-cache-10trblm,
        .st-emotion-cache-16idsys,
        p,
        li,
        h1, h2, h3, h4 {
            color: #e8f1ff !important;
        }
        [data-testid="stTextInputRootElement"] input,
        [data-testid="stNumberInputRootElement"] input,
        [data-baseweb="input"] input,
        [data-baseweb="base-input"] input,
        textarea {
            background: #0f172a !important;
            color: #f8fbff !important;
            border-radius: 14px !important;
        }
        [data-baseweb="input"],
        [data-baseweb="base-input"] {
            background: #0f172a !important;
            border: 1px solid rgba(71, 85, 105, 0.78) !important;
            border-radius: 14px !important;
            box-shadow: none !important;
        }
        [data-baseweb="input"]:focus-within,
        [data-baseweb="base-input"]:focus-within {
            border-color: rgba(56, 189, 248, 0.95) !important;
            box-shadow: 0 0 0 1px rgba(56, 189, 248, 0.45) !important;
        }
        [data-baseweb="tab-list"] {
            gap: 0.75rem;
        }
        [data-testid="stButton"] button,
        [data-testid="stFormSubmitButton"] button {
            background: linear-gradient(135deg, #0f5e9c 0%, #169976 100%);
            color: #ffffff !important;
            border: none;
            border-radius: 14px;
            font-weight: 700;
            box-shadow: 0 12px 24px rgba(2, 8, 23, 0.28);
        }
        [data-testid="stButton"] button:hover,
        [data-testid="stFormSubmitButton"] button:hover {
            background: linear-gradient(135deg, #0a4e83 0%, #137e63 100%);
        }
        [data-testid="stMetric"] {
            background: rgba(15, 23, 42, 0.92);
            border: 1px solid rgba(71, 85, 105, 0.42);
            padding: 0.75rem 0.9rem;
            border-radius: 16px;
        }
        [data-testid="stMetricLabel"],
        [data-testid="stMetricValue"],
        [data-testid="stMetricDelta"] {
            color: #f8fbff !important;
        }
        [data-testid="stDataFrame"] {
            background: #0b1323;
            border-radius: 16px;
            border: 1px solid rgba(71, 85, 105, 0.42);
            overflow: hidden;
        }
        [data-testid="stFileUploaderDropzone"] {
            background: rgba(15, 23, 42, 0.96);
            border: 1px dashed rgba(125, 211, 252, 0.36);
        }
        [data-testid="stFileUploaderDropzone"] * {
            color: #dce8fa !important;
        }
        [data-testid="stRadio"] label,
        [data-testid="stSelectbox"] div,
        [data-testid="stMarkdownContainer"] code {
            color: #e8f1ff !important;
        }
        .stAlert {
            background: rgba(15, 23, 42, 0.92) !important;
            border: 1px solid rgba(71, 85, 105, 0.42) !important;
            color: #e8f1ff !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_metric_card(label: str, value: str, meta: str) -> None:
    """Render a dashboard metric card."""
    st.markdown(
        f"""
        <div class="metric-card">
            <div class="label">{label}</div>
            <div class="value">{value}</div>
            <div class="meta">{meta}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def set_current_org(org_id: int) -> None:
    """Update the selected organization."""
    st.session_state["current_org_id"] = org_id
    user = st.session_state.get("current_user")
    if user:
        persist_login(user.id, org_id, st.session_state.get("selected_page", "Overview"))


def get_current_user():
    """Return the logged-in user from session."""
    return st.session_state.get("current_user")


def get_current_org():
    """Return the selected organization model."""
    user = get_current_user()
    if not user:
        return None
    organizations = OrganizationService.get_user_organizations(user.id)
    if not organizations:
        return None
    current_org_id = st.session_state.get("current_org_id")
    for organization in organizations:
        if organization.id == current_org_id:
            return organization
    st.session_state["current_org_id"] = organizations[0].id
    return organizations[0]


def jump_to(page_name: str) -> None:
    """Store the target page so the shell can switch views."""
    st.session_state["selected_page"] = page_name
    st.query_params["page"] = page_name


def show_auth_portal() -> None:
    """Render login and registration UI."""
    st.markdown('<div class="auth-shell">', unsafe_allow_html=True)
    st.markdown(
        """
        <div class="hero-shell">
            <h2>Cloud Carbon Tracker</h2>
            <p>
                A SaaS workspace for carbon-aware cloud operations. Sign in to access organization dashboards,
                project-level insights, optimization actions, and saved sustainability reports.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown('<div class="auth-panel">', unsafe_allow_html=True)
    st.caption("Use the sample admin account or create a new workspace.")

    login_tab, register_tab = st.tabs(["Sign In", "Create Workspace"])

    with login_tab:
        with st.form("login_form", clear_on_submit=False):
            email = st.text_input("Work email")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Sign In", use_container_width=True)
            if submitted:
                user = UserService.authenticate(email, password)
                if not user:
                    st.error("Invalid email or password.")
                else:
                    organizations = OrganizationService.get_user_organizations(user.id)
                    st.session_state["current_user"] = user
                    st.session_state["current_org_id"] = organizations[0].id if organizations else None
                    st.session_state["selected_page"] = "Overview"
                    if st.session_state["current_org_id"]:
                        AuditLogService.log(
                            org_id=st.session_state["current_org_id"],
                            user_id=user.id,
                            action="auth.login",
                            entity_type="session",
                            description="User signed into the workspace.",
                        )
                    persist_login(user.id, st.session_state["current_org_id"], "Overview")
                    st.rerun()

        st.caption("Sample login: admin@example.com / securepass123")

    with register_tab:
        with st.form("register_form", clear_on_submit=False):
            full_name = st.text_input("Full name")
            email = st.text_input("Email")
            password = st.text_input("Password", type="password")
            org_name = st.text_input("Organization name")
            submitted = st.form_submit_button("Create Workspace", use_container_width=True)
            if submitted:
                existing_user = UserService.get_user_by_email(email)
                if existing_user:
                    st.error("A user with that email already exists.")
                elif len(password) < 8:
                    st.error("Password must be at least 8 characters.")
                else:
                    user = UserService.create_user(email=email, password=password, full_name=full_name)
                    org = OrganizationService.create_organization(
                        name=org_name or f"{full_name}'s Workspace",
                        owner_id=user.id,
                        description="Primary workspace",
                        plan="growth",
                    )
                    ProjectService.create_project(
                        org_id=org.id,
                        name="Primary Cloud Estate",
                        cloud_provider="AWS",
                        region="us",
                        monthly_budget=2500,
                    )
                    ActivityService.log_event(
                        org_id=org.id,
                        user_id=user.id,
                        event_type="workspace",
                        title="Workspace created",
                        description="Workspace initialized from the Streamlit signup flow.",
                    )
                    st.session_state["current_user"] = user
                    st.session_state["current_org_id"] = org.id
                    st.session_state["selected_page"] = "Overview"
                    AuditLogService.log(
                        org_id=org.id,
                        user_id=user.id,
                        action="workspace.signup",
                        entity_type="organization",
                        entity_id=str(org.id),
                        description="Workspace created from the signup flow.",
                    )
                    persist_login(user.id, org.id, "Overview")
                    st.rerun()

        st.caption("A new organization, project, and activity feed will be created automatically.")

    st.markdown("</div>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)


def show_overview() -> None:
    """Render the enterprise command center."""
    user = get_current_user()
    organization = get_current_org()
    if not user or not organization:
        st.warning("Please sign in to view your dashboard.")
        return

    workspace = DashboardService.get_workspace_snapshot(organization.id)
    headline = workspace["headline"]
    reports = workspace["reports"]
    activity = workspace["activity"]
    project_list = workspace["portfolio"]
    recommendations = workspace["recommendations"][:4]

    activity_time = headline["latest_sync"]
    freshness = (
        activity_time.strftime("%d %b %Y %H:%M") if isinstance(activity_time, datetime) else "Awaiting telemetry sync"
    )

    st.markdown(
        f"""
        <div class="hero-shell">
            <h2>{organization.name} Command Center</h2>
            <p>
                Welcome back, {user.full_name or user.email}. Run cloud sustainability like an operating function:
                monitor portfolio exposure, coordinate teams, govern optimization work, and keep stakeholders aligned.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.info(
        "This overview is the workspace landing page for leadership and operators. "
        f"{PRODUCT_GLOSSARY['workspace']} Use it to understand current portfolio posture, see where the biggest risks "
        "and opportunities sit, and jump into the right operating workflow."
    )

    top_col1, top_col2, top_col3, top_col4 = st.columns(4)
    with top_col1:
        render_metric_card("Portfolio Carbon", f"{headline['total_carbon']:,.0f} kg", METRIC_COPY["portfolio_carbon"])
    with top_col2:
        render_metric_card("Monthly Spend", f"${headline['estimated_monthly_spend']:,.0f}", METRIC_COPY["monthly_spend"])
    with top_col3:
        render_metric_card("Coverage Score", f"{headline['coverage_score']}%", METRIC_COPY["coverage_score"])
    with top_col4:
        render_metric_card("Latest Telemetry", freshness, f"{METRIC_COPY['latest_telemetry']} {headline['open_alerts']} open alerts.")
    st.caption(
        f"Portfolio carbon is the total emissions currently tracked in the workspace. Monthly spend is an estimate based on registered budgets. "
        f"Coverage score means: {PRODUCT_GLOSSARY['coverage_score']} Latest telemetry reflects the freshness of ingested carbon records."
    )

    left_col, right_col = st.columns([1.45, 1.0])

    with left_col:
        st.markdown('<div class="glass-card"><h3>Executive Summary</h3>', unsafe_allow_html=True)
        st.write(
            "This workspace now behaves like an enterprise cloud sustainability command center. Finance, platform, and sustainability teams "
            "can work from the same portfolio model, monitor risk, and turn analytics into decisions with clear ownership."
        )
        st.caption(
            "This summary is meant for quick orientation. If you need to act on a problem, use the portfolio, operations, governance, or integrations sections below."
        )
        st.markdown(
            """
            <div class="tag-row">
                <span class="tag">Executive Command Center</span>
                <span class="tag">Portfolio Operations</span>
                <span class="tag">Governance Controls</span>
                <span class="tag">Integrations Hub</span>
                <span class="tag">Team Workspace</span>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.markdown("</div>", unsafe_allow_html=True)

        st.markdown('<div class="glass-card"><h3>Portfolio Exposure</h3>', unsafe_allow_html=True)
        if project_list:
            project_df = pd.DataFrame(project_list)
            st.caption(
                "This section identifies which projects currently contribute the most carbon so teams can focus optimization work where it matters most."
            )
            fig = px.bar(
                project_df,
                x="name",
                y="carbon_kg",
                color="cloud_provider",
                text_auto=".0f",
                title="Highest Carbon Projects",
                labels={"name": "Project", "carbon_kg": "Carbon (kg CO2)", "cloud_provider": "Provider"},
            )
            fig.update_layout(xaxis_tickangle=-20, margin=dict(l=10, r=10, t=48, b=10))
            st.plotly_chart(fig, use_container_width=True)

            compact_df = project_df[
                ["name", "cloud_provider", "region", "monthly_budget", "carbon_kg", "energy_kwh", "status"]
            ].rename(
                columns={
                    "name": "Project",
                    "cloud_provider": "Provider",
                    "region": "Region",
                    "monthly_budget": "Budget (USD)",
                    "carbon_kg": "Carbon (kg CO2)",
                    "energy_kwh": "Energy (kWh)",
                    "status": "Status",
                }
            )
            st.dataframe(compact_df, use_container_width=True)
        else:
            st.info("No projects yet. Create one from the portfolio workspace.")
        st.markdown("</div>", unsafe_allow_html=True)

    with right_col:
        st.markdown('<div class="glass-card"><h3>Regional Exposure</h3>', unsafe_allow_html=True)
        if workspace["regions"]:
            st.caption(
                f"Regional exposure shows where emissions are concentrated geographically. "
                f"{PRODUCT_GLOSSARY['operating_region']} {PRODUCT_GLOSSARY['reporting_region']}"
            )
            region_df = pd.DataFrame(
                [
                    {
                        "Region": get_region_label(key),
                        "Reporting Key": key,
                        "Carbon": value,
                    }
                    for key, value in workspace["regions"].items()
                ]
            )
            fig = px.pie(
                region_df,
                names="Region",
                values="Carbon",
                hole=0.58,
                title="Carbon Distribution By Region",
            )
            fig.update_layout(margin=dict(l=10, r=10, t=48, b=10))
            st.plotly_chart(fig, use_container_width=True)
            st.dataframe(
                region_df.sort_values("Carbon", ascending=False)
                .rename(columns={"Reporting Key": "Stored Region Key", "Carbon": "Carbon (kg CO2)"}),
                use_container_width=True,
            )
        else:
            st.info("Regional exposure will appear once carbon telemetry is recorded.")
        st.markdown("</div>", unsafe_allow_html=True)

        st.markdown('<div class="glass-card"><h3>Priority Actions</h3>', unsafe_allow_html=True)
        st.caption("These are the highest-value optimization ideas currently open in the workspace.")
        if recommendations:
            for item in recommendations:
                st.write(f"**{item['suggestion']}**")
                st.caption(
                    f"Priority: {item['priority']} | Carbon savings: {item['carbon_saving_percent']:.1f}% | Cost impact: ${item['cost_impact']:,.0f}"
                )
                st.markdown("---")
        else:
            st.info("No optimization recommendations yet.")
        st.markdown("</div>", unsafe_allow_html=True)

        st.markdown('<div class="glass-card"><h3>Workspace Readiness</h3>', unsafe_allow_html=True)
        st.caption(
            "Readiness is a simple operating checklist covering connected scopes, assigned people, reporting output, and monitored project scope."
        )
        readiness_lines = [
            f"Connected scopes: {headline['cloud_accounts']}",
            f"Assigned workspace members: {headline['team_members']}",
            f"Published reports: {headline['reports']}",
            f"Projects monitored: {headline['active_projects']}",
            f"Open actions: {headline['open_actions']}",
        ]
        for line in readiness_lines:
            st.write(line)
        st.markdown("</div>", unsafe_allow_html=True)

    lower_left, lower_right = st.columns([1.1, 0.9])

    with lower_left:
        st.markdown('<div class="glass-card"><h3>Operating Queue</h3>', unsafe_allow_html=True)
        st.caption("Use these shortcuts to move directly into the main operating workflows.")
        action_col1, action_col2, action_col3 = st.columns(3)
        with action_col1:
            if st.button("Open Portfolio Workspace", use_container_width=True):
                jump_to("Portfolio Workspace")
                st.rerun()
            if st.button("Upload Usage Dataset", use_container_width=True):
                jump_to("Upload Analytics")
                st.rerun()
        with action_col2:
            if st.button("Open Operations", use_container_width=True):
                jump_to("Operations Center")
                st.rerun()
            if st.button("Review Governance", use_container_width=True):
                jump_to("Governance Center")
                st.rerun()
        with action_col3:
            if st.button("Run AI Forecast", use_container_width=True):
                jump_to("AI Forecast Studio")
                st.rerun()
            if st.button("Manage Integrations", use_container_width=True):
                jump_to("Integrations Hub")
                st.rerun()
            if st.button("Open Team Workspace", use_container_width=True):
                jump_to("Team Workspace")
                st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

        st.markdown('<div class="glass-card"><h3>Recent Activity</h3>', unsafe_allow_html=True)
        st.caption("Recent activity provides a lightweight timeline of what changed in the workspace.")
        if activity:
            for event in activity[:6]:
                st.write(f"**{event['title']}**")
                st.caption(event["description"])
                st.caption(str(event["created_at"]))
                st.markdown("---")
        else:
            st.info("No recent activity yet.")
        st.markdown("</div>", unsafe_allow_html=True)

    with lower_right:
        st.markdown('<div class="glass-card"><h3>Saved Reports</h3>', unsafe_allow_html=True)
        st.caption("Saved reports are reusable outputs for management reviews, audits, and stakeholder updates.")
        if reports:
            for report in reports:
                st.write(f"**{report['title']}**")
                st.caption(f"{report['report_type']} report")
                st.write(report["summary"])
                st.markdown("---")
        else:
            st.info("No saved reports yet.")
        st.markdown("</div>", unsafe_allow_html=True)


PAGE_MAP = {
    "Overview": show_overview,
    "Portfolio Workspace": portfolio_workspace.show,
    "Operations Center": operations_center.show,
    "Governance Center": governance_center.show,
    "Integrations Hub": integrations_hub.show,
    "Team Workspace": team_workspace.show,
    "Upload Analytics": upload_analytics.show,
    "Scenario Planner": region_simulation.show,
    "AI Forecast Studio": carbon_forecast.show,
    "Executive Scorecards": sustainability_scorecard.show,
}

inject_shell_styles()
hydrate_session_from_query_params()

if "selected_page" not in st.session_state:
    st.session_state["selected_page"] = st.query_params.get("page", "Overview")

page_names = list(PAGE_MAP.keys())

if not get_current_user():
    show_auth_portal()
else:
    organization = get_current_org()
    user = get_current_user()
    current_page = st.session_state["selected_page"]
    if current_page not in PAGE_MAP:
        current_page = "Overview"
        st.session_state["selected_page"] = current_page

    st.title("Cloud Carbon Tracker")
    st.caption("Enterprise carbon intelligence workspace for cloud operations, FinOps, and sustainability teams")

    organizations = OrganizationService.get_user_organizations(user.id)
    organization_names = {org.name: org.id for org in organizations}
    role = MembershipService.get_member_role(organization.id, user.id) if organization else None

    st.sidebar.title("Cloud Carbon Tracker")
    st.sidebar.caption("Workspace navigation and operating status")
    st.sidebar.success(f"Signed in as {user.full_name or user.email}")
    if role:
        st.sidebar.caption(f"Role: {role}")

    if organizations:
        selected_org_name = st.sidebar.selectbox(
            "Organization",
            options=list(organization_names.keys()),
            index=list(organization_names.values()).index(organization.id),
        )
        set_current_org(organization_names[selected_org_name])
        organization = get_current_org()

    selected_page = st.sidebar.radio(
        "Workspace Sections",
        options=page_names,
        index=page_names.index(current_page),
        captions=[NAV_SECTIONS[item] for item in page_names],
    )
    st.session_state["selected_page"] = selected_page
    st.query_params["page"] = selected_page

    snapshot = DashboardService.get_dashboard_snapshot(organization.id) if organization else {}
    st.sidebar.markdown("---")
    st.sidebar.caption("Workspace Snapshot")
    st.sidebar.metric("Plan", getattr(organization, "plan", "growth").title() if organization else "Growth")
    st.sidebar.metric("Projects", snapshot.get("project_count", 0))
    st.sidebar.metric("Saved Reports", snapshot.get("report_count", 0))
    st.sidebar.metric("Open Recommendations", snapshot.get("open_recommendations", 0))
    workspace_snapshot = DashboardService.get_workspace_snapshot(organization.id) if organization else {}
    st.sidebar.metric("Open Alerts", workspace_snapshot.get("headline", {}).get("open_alerts", 0))
    st.sidebar.metric("Open Actions", workspace_snapshot.get("headline", {}).get("open_actions", 0))
    st.sidebar.caption(
        "Projects reflect registered portfolio scope. Recommendations are unresolved optimization ideas. "
        "Alerts and actions indicate active operational follow-up. Connected scopes are tracked in Integrations Hub."
    )

    if st.sidebar.button("Sign Out", use_container_width=True):
        if organization:
            AuditLogService.log(
                org_id=organization.id,
                user_id=user.id,
                action="auth.logout",
                entity_type="session",
                description="User signed out of the workspace.",
            )
        st.session_state.clear()
        clear_persisted_login()
        st.rerun()

    PAGE_MAP[selected_page]()
