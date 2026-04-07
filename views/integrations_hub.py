"""Integrations and ingestion workspace page."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from config import PRODUCT_GLOSSARY
from database.service import (
    ActivityService,
    APIKeyService,
    AuditLogService,
    CloudAccountService,
    ConnectorJobService,
    ConnectorService,
    DashboardService,
    IngestionRunService,
    MembershipService,
)
from engine.connector_worker import assess_connector_health, build_execution_plan, execute_due_jobs, run_dry_sync, run_file_sync


PROVIDER_PLAYBOOKS = {
    "AWS": [
        "Enable AWS Cost and Usage Report with hourly granularity and resource IDs.",
        "Deliver CUR to a governed S3 bucket and expose the billing account scope you want tracked.",
        "Create a read-only IAM role for billing and account inventory queries.",
        "Register the connector here with the bucket name or payer account as the external reference.",
    ],
    "GCP": [
        "Turn on BigQuery billing export for the billing account or folder scope.",
        "Grant a service account read access to the export dataset and relevant projects.",
        "Capture the billing account ID or BigQuery dataset path as the external reference.",
        "Register the connector here so imported cost and carbon telemetry can be tied to the workspace.",
    ],
    "Azure": [
        "Enable Cost Management exports for the management group or subscription scope.",
        "Grant reader access to the subscription and the storage account receiving exports.",
        "Capture the subscription ID or export path as the external reference.",
        "Register the connector here to land Azure cost and carbon telemetry in the workspace.",
    ],
}


def _render_connector_form(provider: str, org_id: int, user_id: int | None, can_write: bool) -> None:
    """Render a provider-specific connector setup form."""
    st.markdown(f"**{provider} setup playbook**")
    for step in PROVIDER_PLAYBOOKS[provider]:
        st.write(f"- {step}")
    if provider == "AWS":
        st.caption("Execution supports local CUR CSV files now, and can also use `s3://bucket/key.csv` when boto3 and AWS credentials are available.")
    elif provider == "GCP":
        st.caption("Execution supports local billing export CSV files now, and can also use `gs://bucket/key.csv` when google-cloud-storage and Google credentials are available.")
    else:
        st.caption("Execution currently supports local export CSV files for this provider.")

    with st.form(f"{provider.lower()}_connector_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        connector_name = col1.text_input("Connector name", value=f"{provider} production connector")
        auth_mode = col2.selectbox(
            "Authentication model",
            options=(
                ["AssumeRole / CUR", "Access keys + CUR bucket"]
                if provider == "AWS"
                else ["Service account + BigQuery export", "Workload identity federation"]
                if provider == "GCP"
                else ["App registration + Cost export", "Managed identity + export storage"]
            ),
        )
        col3, col4 = st.columns(2)
        external_reference = col3.text_input("External reference", placeholder="payer-account, billing account, or subscription id")
        sync_frequency = col4.selectbox("Sync frequency", ["Hourly", "Daily", "Weekly"])
        col5, col6 = st.columns(2)
        account_name = col5.text_input("Workspace account name", value=f"{provider} production estate")
        scope_region = col6.text_input("Primary scope / region", value="global" if provider != "AWS" else "us-east-1")
        notes = st.text_area("Notes", placeholder="Optional implementation notes, owners, or export locations")
        submitted = st.form_submit_button(f"Register {provider} Connector", use_container_width=True, disabled=not can_write)
        if submitted:
            if not connector_name.strip() or not external_reference.strip():
                st.error("Connector name and external reference are required.")
            else:
                CloudAccountService.get_or_create_cloud_account(
                    org_id=org_id,
                    provider=provider,
                    account_name=account_name.strip() or f"{provider} estate",
                    account_id=external_reference.strip(),
                    region=scope_region.strip() or None,
                )
                ConnectorService.create_connector(
                    org_id=org_id,
                    provider=provider,
                    connector_name=connector_name.strip(),
                    auth_mode=auth_mode,
                    status="connected",
                    external_reference=external_reference.strip(),
                    scope_region=scope_region.strip() or None,
                    sync_frequency=sync_frequency,
                    notes=notes.strip() or None,
                    metadata_json={"playbook": provider, "account_name": account_name.strip() or f"{provider} estate"},
                )
                ActivityService.log_event(
                    org_id=org_id,
                    user_id=user_id,
                    event_type="integration",
                    title=f"{provider} connector registered",
                    description=f"{connector_name.strip()} was registered with {sync_frequency.lower()} sync cadence.",
                )
                AuditLogService.log(
                    org_id=org_id,
                    user_id=user_id,
                    action="connector.registered",
                    entity_type="connector",
                    entity_id=connector_name.strip(),
                    description=f"{provider} connector registered.",
                    metadata_json={"provider": provider, "reference": external_reference.strip()},
                )
                st.success(f"{provider} connector registered.")
                st.rerun()


def show() -> None:
    """Display integrations, cloud accounts, and API tooling."""
    org_id = st.session_state.get("current_org_id")
    user = st.session_state.get("current_user")
    if not org_id:
        st.warning("Select an organization to open integrations.")
        return

    snapshot = DashboardService.get_workspace_snapshot(org_id)
    accounts = snapshot["accounts"]
    connectors = snapshot["connectors"]
    runs = snapshot["ingestion_runs"]
    sync_jobs = ConnectorJobService.get_org_jobs(org_id, limit=12)
    can_write = MembershipService.has_permission(org_id, getattr(user, "id", 0), "integrations.write")

    st.header("Integrations Hub")
    st.caption("Connect AWS, GCP, Azure, and dataset imports so the workspace can run on real telemetry.")
    st.info(
        "This is the ingestion and connectivity layer for the workspace. "
        f"{PRODUCT_GLOSSARY['connected_scope']} {PRODUCT_GLOSSARY['connector']} {PRODUCT_GLOSSARY['telemetry']}"
    )

    if st.button("Register Demo Connector Pack", use_container_width=False, disabled=not can_write):
        for provider, connector_name, auth_mode, reference, region in [
            ("AWS", "AWS Demo Connector", "AssumeRole / CUR", "aws-demo-payer", "us-east-1"),
            ("GCP", "GCP Demo Connector", "Service account + BigQuery export", "gcp-demo-billing", "europe-west4"),
            ("Azure", "Azure Demo Connector", "App registration + Cost export", "azure-demo-subscription", "centralindia"),
        ]:
            CloudAccountService.get_or_create_cloud_account(
                org_id=org_id,
                provider=provider,
                account_name=f"{provider} demo estate",
                account_id=reference,
                region=region,
            )
            ConnectorService.create_connector(
                org_id=org_id,
                provider=provider,
                connector_name=connector_name,
                auth_mode=auth_mode,
                status="connected",
                external_reference=reference,
                scope_region=region,
                sync_frequency="Daily",
                notes="Demo connector pack",
                metadata_json={"demo": True},
            )
        ActivityService.log_event(
            org_id=org_id,
            user_id=getattr(user, "id", None),
            event_type="integration",
            title="Demo connector pack registered",
            description="Demo AWS, GCP, and Azure connectors were added for product walkthroughs.",
        )
        AuditLogService.log(
            org_id=org_id,
            user_id=getattr(user, "id", None),
            action="connectors.demo_pack_registered",
            entity_type="connector",
            description="Demo connector pack registered.",
        )
        st.rerun()

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Connected Estates", len(accounts))
    col2.metric("Connectors", len(connectors))
    col3.metric("Ingestion Runs", len(runs))
    col4.metric("Queued Sync Jobs", len([job for job in sync_jobs if job["status"] in {"pending", "running"}]))
    st.caption(
        "Connected scopes are the billing accounts, subscriptions, or cloud accounts tracked in the workspace. "
        "Connectors define how telemetry is pulled in. Ingestion runs are historical sync attempts and outcomes."
    )

    connector_status = pd.DataFrame(
        [
            {
                "Integration": "AWS CUR / Organizations",
                "Status": "Connected" if any(a["provider"] == "AWS" for a in accounts) else "Pending",
                "Purpose": "Billing, account inventory, workload tagging",
            },
            {
                "Integration": "GCP Billing Export",
                "Status": "Connected" if any(a["provider"] == "GCP" for a in accounts) else "Pending",
                "Purpose": "BigQuery billing and carbon telemetry",
            },
            {
                "Integration": "Azure Cost Management",
                "Status": "Connected" if any(a["provider"] == "Azure" for a in accounts) else "Pending",
                "Purpose": "Subscription spend and regional workload view",
            },
            {
                "Integration": "Dataset Uploads",
                "Status": "Operational",
                "Purpose": "CSV ingestion for historical emissions analytics",
            },
        ]
    )
    st.subheader("Connector Readiness")
    st.caption("Use this table to understand which enterprise data sources are already represented and which still need onboarding.")
    st.dataframe(connector_status, use_container_width=True)

    if connectors:
        st.subheader("Configured Connectors")
        st.caption("Configured connectors are reusable ingestion definitions for recurring sync jobs and governed cloud access.")
        connector_rows = []
        for connector in connectors:
            health = assess_connector_health(connector)
            connector_rows.append(
                {
                    "provider": connector["provider"],
                    "connector_name": connector["connector_name"],
                    "auth_mode": connector["auth_mode"],
                    "health": health["health"],
                    "source_mode": health["source_mode"],
                    "status": connector["status"],
                    "external_reference": connector["external_reference"],
                    "scope_region": connector["scope_region"],
                    "sync_frequency": connector["sync_frequency"],
                    "last_sync_at": connector["last_sync_at"],
                }
            )
        connector_df = pd.DataFrame(connector_rows)[
            ["provider", "connector_name", "auth_mode", "health", "source_mode", "status", "external_reference", "scope_region", "sync_frequency", "last_sync_at"]
        ]
        connector_df.columns = [
            "Provider",
            "Connector",
            "Auth Mode",
            "Health",
            "Source Mode",
            "Status",
            "External Reference",
            "Scope",
            "Sync",
            "Last Sync",
        ]
        st.dataframe(connector_df, use_container_width=True)

        selected_connector = st.selectbox(
            "Connector execution preview",
            options=[connector["connector_name"] for connector in connectors],
        )
        connector_lookup = {connector["connector_name"]: connector for connector in connectors}
        active_connector = connector_lookup[selected_connector]
        plan = build_execution_plan(active_connector)
        connector_health = assess_connector_health(active_connector)
        st.markdown(f"**Execution plan for {selected_connector}**")
        st.write(plan.summary)
        st.caption(
            f"Connector health: **{connector_health['health']}**. "
            f"Source mode: **{connector_health['source_mode']}**."
        )
        if connector_health["issues"]:
            for issue in connector_health["issues"]:
                st.warning(issue)
        st.caption(
            "The execution plan explains what the connector expects before a real sync can run successfully. "
            "Save the local export path if you want to test with CSV data before wiring live provider access."
        )
        st.write("Readiness checks:")
        for item in plan.checks:
            st.write(f"- {item}")
        current_metadata = active_connector.get("metadata_json") or {}
        local_dataset_path = st.text_input(
            "Local export file path",
            value=str(current_metadata.get("local_dataset_path", "")),
            placeholder=r"C:\path\to\aws-cur.csv",
            key=f"dataset_path_{active_connector['id']}",
        )
        scheduler_col1, scheduler_col2 = st.columns(2)
        queue_mode = scheduler_col1.selectbox(
            "Queue mode",
            options=["manual", "scheduled"],
            key=f"queue_mode_{active_connector['id']}",
        )
        if scheduler_col2.button("Queue Sync Job", use_container_width=True, disabled=not can_write):
            queued_job = ConnectorJobService.queue_sync_job(
                org_id=org_id,
                connector_id=int(active_connector["id"]),
                trigger_mode=queue_mode,
                requested_by=getattr(user, "id", None),
                payload={"connector_name": active_connector["connector_name"]},
            )
            AuditLogService.log(
                org_id=org_id,
                user_id=getattr(user, "id", None),
                action="connector.job_queued",
                entity_type="connector_sync_job",
                entity_id=str(queued_job["id"]),
                description=f"Queued {queue_mode} sync for {active_connector['connector_name']}.",
                metadata_json={"connector_id": active_connector["id"], "trigger_mode": queue_mode},
            )
            st.success(f"Queued sync job {queued_job['id']} for {active_connector['connector_name']}.")
            st.rerun()
        if st.button("Save Execution Settings", use_container_width=False, disabled=not can_write):
            updated_metadata = {
                **current_metadata,
                "local_dataset_path": local_dataset_path.strip(),
                "account_name": current_metadata.get("account_name") or active_connector["connector_name"],
            }
            ConnectorService.update_connector(
                active_connector["id"],
                metadata_json=updated_metadata,
            )
            AuditLogService.log(
                org_id=org_id,
                user_id=getattr(user, "id", None),
                action="connector.settings_updated",
                entity_type="connector",
                entity_id=str(active_connector["id"]),
                description="Connector execution settings updated.",
                metadata_json={"local_dataset_path": local_dataset_path.strip()},
            )
            st.success("Connector execution settings saved.")
            st.rerun()
        if st.button("Run Dry Sync", use_container_width=False, disabled=not can_write):
            result = run_dry_sync(active_connector)
            ConnectorService.mark_sync(active_connector["id"], status="connected", notes=result.summary)
            AuditLogService.log(
                org_id=org_id,
                user_id=getattr(user, "id", None),
                action="connector.dry_sync",
                entity_type="connector",
                entity_id=str(active_connector["id"]),
                description=result.summary,
                metadata_json=result.payload,
            )
            st.success(result.summary)
            st.rerun()
        if st.button("Run File Sync", use_container_width=False, disabled=not can_write):
            result = run_file_sync(
                active_connector,
                org_id=org_id,
                created_by=getattr(user, "id", None),
            )
            if result.status == "completed":
                ActivityService.log_event(
                    org_id=org_id,
                    user_id=getattr(user, "id", None),
                    event_type="integration",
                    title="Connector file sync completed",
                    description=result.summary,
                    metadata_json=result.payload,
                )
                AuditLogService.log(
                    org_id=org_id,
                    user_id=getattr(user, "id", None),
                    action="connector.file_sync",
                    entity_type="connector",
                    entity_id=str(active_connector["id"]),
                    description=result.summary,
                    metadata_json=result.payload,
                )
                st.success(result.summary)
            else:
                st.warning(result.summary)
        if st.button("Run Due Sync Jobs", use_container_width=False, disabled=not can_write):
            results = execute_due_jobs(limit=10)
            if results:
                ActivityService.log_event(
                    org_id=org_id,
                    user_id=getattr(user, "id", None),
                    event_type="integration",
                    title="Queued sync jobs processed",
                    description=f"Processed {len(results)} due connector jobs from the background queue.",
                    metadata_json={"results": [result.summary for result in results]},
                )
                st.success(f"Processed {len(results)} queued connector job(s).")
            else:
                st.info("No due sync jobs were waiting in the queue.")
            st.rerun()

    if runs:
        st.subheader("Recent Ingestion History")
        st.caption("This history shows what was ingested, how much telemetry landed, and whether each sync completed successfully.")
        runs_df = pd.DataFrame(runs)[["source_type", "source_name", "status", "records_ingested", "total_carbon_kg_co2", "completed_at"]]
        runs_df.columns = ["Source Type", "Source", "Status", "Records", "Carbon (kg CO2)", "Completed At"]
        st.dataframe(runs_df, use_container_width=True)

    st.subheader("Background Sync Queue")
    st.caption(
        "Queued sync jobs are the foundation for scheduled background ingestion. "
        "Use them to stage connector runs and process them from the UI today or from the scheduler script later."
    )
    st.code("python -m engine.sync_scheduler", language="powershell")
    if sync_jobs:
        jobs_df = pd.DataFrame(sync_jobs)[
            ["id", "provider", "connector_name", "trigger_mode", "status", "attempt_count", "queued_at", "started_at", "completed_at"]
        ]
        jobs_df.columns = ["Job ID", "Provider", "Connector", "Trigger", "Status", "Attempts", "Queued At", "Started At", "Completed At"]
        st.dataframe(jobs_df, use_container_width=True)
    else:
        st.info("No queued connector jobs yet.")

    st.subheader("Register Cloud Connector")
    st.caption("Choose a provider tab below to define a new ingestion pathway for a billing account, subscription, or export dataset.")
    aws_tab, gcp_tab, azure_tab = st.tabs(["AWS", "GCP", "Azure"])
    with aws_tab:
        _render_connector_form("AWS", org_id, getattr(user, "id", None), can_write)
    with gcp_tab:
        _render_connector_form("GCP", org_id, getattr(user, "id", None), can_write)
    with azure_tab:
        _render_connector_form("Azure", org_id, getattr(user, "id", None), can_write)

    st.subheader("Registered Cloud Accounts")
    st.caption("Registered cloud accounts represent the connected scopes that the workspace associates with imported telemetry and controls.")
    if accounts:
        account_df = pd.DataFrame(accounts)[["provider", "account_name", "account_id", "region", "is_active", "created_at"]]
        account_df.columns = ["Provider", "Account Name", "Account ID", "Region", "Active", "Created At"]
        st.dataframe(account_df, use_container_width=True)
    else:
        st.info("No cloud estates connected yet.")

    st.subheader("API Access")
    st.caption("API keys are intended for automation jobs, scheduled sync workers, or controlled external tooling.")
    if st.button("Generate Workspace API Key", use_container_width=False, disabled=not can_write):
        key_id, plaintext_key = APIKeyService.create_api_key(
            user_id=getattr(user, "id", 0),
            name="Workspace automation key",
        )
        st.success(f"API key created. Key ID: {key_id}")
        st.code(plaintext_key, language="text")
        ActivityService.log_event(
            org_id=org_id,
            user_id=getattr(user, "id", None),
            event_type="security",
            title="API key generated",
            description="A new workspace API key was issued for automation or ingestion jobs.",
        )
        AuditLogService.log(
            org_id=org_id,
            user_id=getattr(user, "id", None),
            action="api_key.created",
            entity_type="api_key",
            entity_id=str(key_id),
            description="Workspace automation API key generated.",
        )
