"""Execution scaffolding for enterprise cloud connectors."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from io import BytesIO
import os
from pathlib import Path
from typing import Any

import pandas as pd


@dataclass
class ConnectorExecutionResult:
    """Structured output for connector planning and dry runs."""

    provider: str
    status: str
    summary: str
    checks: list[str]
    next_steps: list[str]
    payload: dict[str, Any]


def _resolve_source_mode(dataset_path: object) -> str:
    """Return the source mode used by a connector path."""
    text = str(dataset_path or "").strip()
    if text.startswith("s3://"):
        return "aws_s3"
    if text.startswith("gs://"):
        return "gcp_gcs"
    if text.startswith("azure://"):
        return "azure_blob"
    if text:
        return "local_file"
    return "unset"


def _check_provider_credentials(provider: str) -> tuple[bool, list[str]]:
    """Check whether env-based provider credentials appear available."""
    provider = str(provider or "").upper()
    checks: list[str] = []

    if provider == "AWS":
        available = bool(
            os.getenv("AWS_PROFILE")
            or (
                os.getenv("AWS_ACCESS_KEY_ID")
                and os.getenv("AWS_SECRET_ACCESS_KEY")
            )
        )
        checks.append("AWS credentials found in environment." if available else "AWS credentials are not configured in environment variables.")
        return available, checks

    if provider == "GCP":
        available = bool(
            os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
            or os.getenv("GOOGLE_CLOUD_PROJECT")
        )
        checks.append("Google Cloud credentials found in environment." if available else "Google Cloud credentials are not configured in environment variables.")
        return available, checks

    if provider == "AZURE":
        available = bool(
            os.getenv("AZURE_STORAGE_CONNECTION_STRING")
            or (
                os.getenv("AZURE_CLIENT_ID")
                and os.getenv("AZURE_CLIENT_SECRET")
                and os.getenv("AZURE_TENANT_ID")
            )
        )
        checks.append("Azure credentials found in environment." if available else "Azure credentials are not configured in environment variables.")
        return available, checks

    return False, ["Provider credential checks are not configured."]


def assess_connector_health(connector: dict[str, Any]) -> dict[str, Any]:
    """Assess whether a connector is ready, degraded, or blocked."""
    metadata = connector.get("metadata_json") or {}
    dataset_path = metadata.get("local_dataset_path")
    provider = str(connector.get("provider", "unknown"))
    source_mode = _resolve_source_mode(dataset_path)
    has_credentials, credential_checks = _check_provider_credentials(provider)

    issues: list[str] = []
    if source_mode == "unset":
        issues.append("No export source path is configured.")
    elif source_mode == "local_file":
        resolved_path = Path(str(dataset_path))
        if not resolved_path.exists():
            issues.append("Configured local export file does not exist.")
    elif source_mode in {"aws_s3", "gcp_gcs", "azure_blob"} and not has_credentials:
        issues.append("Remote export path is configured but provider credentials are missing.")

    if source_mode == "unset":
        health = "blocked"
    elif issues:
        health = "degraded"
    else:
        health = "ready"

    return {
        "health": health,
        "source_mode": source_mode,
        "issues": issues,
        "credential_checks": credential_checks,
        "credentials_ready": has_credentials,
    }


def build_execution_plan(connector: dict[str, Any]) -> ConnectorExecutionResult:
    """Return a provider-specific sync plan for a configured connector."""
    provider = str(connector.get("provider", "unknown"))
    connector_name = connector.get("connector_name", "connector")
    reference = connector.get("external_reference", "not-set")
    sync_frequency = connector.get("sync_frequency", "Daily")
    health = assess_connector_health(connector)

    provider_plans = {
        "AWS": {
            "checks": [
                "Verify the CUR bucket path is reachable and contains hourly parquet or csv exports.",
                "Verify the IAM role grants billing read access and Organizations inventory visibility.",
                "Verify account mapping tags are available for project attribution.",
            ],
            "next_steps": [
                "Read the latest CUR partition from S3.",
                "Normalize line items into workspace usage and carbon rows.",
                "Write an ingestion run and refresh portfolio alerts.",
            ],
        },
        "GCP": {
            "checks": [
                "Verify BigQuery billing export dataset exists and contains recent partitions.",
                "Verify the service account can read billing tables and project metadata.",
                "Verify project labels are available for cost-center attribution.",
            ],
            "next_steps": [
                "Query the latest billing export partition.",
                "Normalize billing rows into workspace usage and carbon rows.",
                "Write an ingestion run and refresh portfolio alerts.",
            ],
        },
        "Azure": {
            "checks": [
                "Verify Cost Management export files are available in the storage account.",
                "Verify the app registration or managed identity has reader access to the subscription scope.",
                "Verify resource group and tag metadata are available for attribution.",
            ],
            "next_steps": [
                "Read the most recent export blob set.",
                "Normalize usage and reservation data into workspace telemetry.",
                "Write an ingestion run and refresh portfolio alerts.",
            ],
        },
    }
    plan = provider_plans.get(provider, {"checks": ["Provider playbook not configured."], "next_steps": []})
    return ConnectorExecutionResult(
        provider=provider,
        status=str(health["health"]),
        summary=(
            f"{connector_name} is registered for {sync_frequency.lower()} sync. "
            f"Current source mode is {health['source_mode']}. Export reference: {reference}."
        ),
        checks=health["credential_checks"] + plan["checks"],
        next_steps=plan["next_steps"],
        payload={
            "connector_name": connector_name,
            "provider": provider,
            "external_reference": reference,
            "sync_frequency": sync_frequency,
            "health": health["health"],
            "issues": health["issues"],
            "source_mode": health["source_mode"],
        },
    )


def run_dry_sync(connector: dict[str, Any]) -> ConnectorExecutionResult:
    """Simulate a sync execution so the workspace can demonstrate connector workflows."""
    plan = build_execution_plan(connector)
    return ConnectorExecutionResult(
        provider=plan.provider,
        status="dry_run_completed",
        summary=(
            f"Dry-run for {plan.payload['connector_name']} completed. "
            "Connector definition looks structurally valid; credentials and live export access are still required."
        ),
        checks=plan.checks,
        next_steps=plan.next_steps,
        payload=plan.payload | {"mode": "dry_run"},
    )


def _load_connector_dataframe(connector: dict[str, Any], dataset_path: object) -> tuple[pd.DataFrame, str] | ConnectorExecutionResult:
    """Load a connector source into a normalized dataframe."""
    from utils.dataset_adapter import read_connector_dataframe

    if str(dataset_path).startswith("s3://"):
        provider = str(connector.get("provider", "unknown"))
        if provider != "AWS":
            return ConnectorExecutionResult(
                provider=provider,
                status="unsupported_remote_scheme",
                summary="Only AWS connectors currently support s3:// execution paths.",
                checks=["Use a local CSV path or register an AWS connector."],
                next_steps=["Switch to a local file path for non-AWS connectors."],
                payload={"connector_id": connector.get("id"), "path": str(dataset_path)},
            )
        try:
            import boto3  # type: ignore
        except ModuleNotFoundError:
            return ConnectorExecutionResult(
                provider=provider,
                status="missing_dependency",
                summary="boto3 is not installed, so S3-backed AWS CUR sync is unavailable in this environment.",
                checks=["Install boto3 in the project environment before using s3:// paths."],
                next_steps=["Use a local CUR CSV path for now, or install boto3 and configure AWS credentials."],
                payload={"connector_id": connector.get("id"), "path": str(dataset_path)},
            )

        bucket_and_key = str(dataset_path).replace("s3://", "", 1)
        bucket_name, _, object_key = bucket_and_key.partition("/")
        if not bucket_name or not object_key:
            return ConnectorExecutionResult(
                provider=provider,
                status="invalid_s3_path",
                summary="S3 path must look like s3://bucket/key.csv",
                checks=["Verify the configured CUR path format."],
                next_steps=["Update the connector execution settings with a valid s3 URI."],
                payload={"connector_id": connector.get("id"), "path": str(dataset_path)},
            )
        try:
            client = boto3.client("s3")
            response = client.get_object(Bucket=bucket_name, Key=object_key)
            normalized_df = read_connector_dataframe(
                BytesIO(response["Body"].read()),
                provider=str(connector.get("provider", "")),
            )
            source_name = object_key.split("/")[-1]
        except Exception as exc:
            return ConnectorExecutionResult(
                provider=provider,
                status="s3_read_failed",
                summary=f"Failed to read AWS CUR object from S3: {exc}",
                checks=["Verify AWS credentials, bucket access, and object path."],
                next_steps=["Test the CUR object path and role permissions."],
                payload={"connector_id": connector.get("id"), "path": str(dataset_path)},
            )
        return normalized_df, source_name
    elif str(dataset_path).startswith("gs://"):
        provider = str(connector.get("provider", "unknown"))
        if provider != "GCP":
            return ConnectorExecutionResult(
                provider=provider,
                status="unsupported_remote_scheme",
                summary="Only GCP connectors currently support gs:// execution paths.",
                checks=["Use a local CSV path or register a GCP connector."],
                next_steps=["Switch to a local file path for non-GCP connectors."],
                payload={"connector_id": connector.get("id"), "path": str(dataset_path)},
            )
        try:
            from google.cloud import storage  # type: ignore
        except ModuleNotFoundError:
            return ConnectorExecutionResult(
                provider=provider,
                status="missing_dependency",
                summary="google-cloud-storage is not installed, so gs:// billing export sync is unavailable in this environment.",
                checks=["Install google-cloud-storage and configure Google credentials before using gs:// paths."],
                next_steps=["Use a local billing export CSV for now, or install the Google client library."],
                payload={"connector_id": connector.get("id"), "path": str(dataset_path)},
            )

        bucket_and_key = str(dataset_path).replace("gs://", "", 1)
        bucket_name, _, object_key = bucket_and_key.partition("/")
        if not bucket_name or not object_key:
            return ConnectorExecutionResult(
                provider=provider,
                status="invalid_gs_path",
                summary="GCS path must look like gs://bucket/key.csv",
                checks=["Verify the configured billing export path format."],
                next_steps=["Update the connector execution settings with a valid gs URI."],
                payload={"connector_id": connector.get("id"), "path": str(dataset_path)},
            )
        try:
            client = storage.Client()
            blob = client.bucket(bucket_name).blob(object_key)
            normalized_df = read_connector_dataframe(
                BytesIO(blob.download_as_bytes()),
                provider=str(connector.get("provider", "")),
            )
            source_name = object_key.split("/")[-1]
        except Exception as exc:
            return ConnectorExecutionResult(
                provider=provider,
                status="gcs_read_failed",
                summary=f"Failed to read GCP billing export from Cloud Storage: {exc}",
                checks=["Verify Google credentials, bucket access, and object path."],
                next_steps=["Test the billing export object path and service account permissions."],
                payload={"connector_id": connector.get("id"), "path": str(dataset_path)},
            )
        return normalized_df, source_name
    elif str(dataset_path).startswith("azure://"):
        provider = str(connector.get("provider", "unknown"))
        if provider != "Azure":
            return ConnectorExecutionResult(
                provider=provider,
                status="unsupported_remote_scheme",
                summary="Only Azure connectors currently support azure:// execution paths.",
                checks=["Use a local CSV path or register an Azure connector."],
                next_steps=["Switch to a local file path for non-Azure connectors."],
                payload={"connector_id": connector.get("id"), "path": str(dataset_path)},
            )
        try:
            from azure.storage.blob import BlobClient  # type: ignore
        except ModuleNotFoundError:
            return ConnectorExecutionResult(
                provider=provider,
                status="missing_dependency",
                summary="azure-storage-blob is not installed, so azure:// export sync is unavailable in this environment.",
                checks=["Install azure-storage-blob before using azure:// paths."],
                next_steps=["Use a local Azure export CSV for now, or install the Azure client library."],
                payload={"connector_id": connector.get("id"), "path": str(dataset_path)},
            )

        try:
            blob_uri = str(dataset_path).replace("azure://", "https://", 1)
            blob_client = BlobClient.from_blob_url(blob_uri)
            normalized_df = read_connector_dataframe(
                BytesIO(blob_client.download_blob().readall()),
                provider=str(connector.get("provider", "")),
            )
            source_name = blob_uri.rstrip("/").split("/")[-1]
        except Exception as exc:
            return ConnectorExecutionResult(
                provider=provider,
                status="azure_blob_read_failed",
                summary=f"Failed to read Azure export from Blob Storage: {exc}",
                checks=["Verify the blob URL, Azure credentials, and container access."],
                next_steps=["Test the Azure export location and access policy."],
                payload={"connector_id": connector.get("id"), "path": str(dataset_path)},
            )
        return normalized_df, source_name
    else:
        resolved_path = Path(dataset_path)
        if not resolved_path.exists() or not resolved_path.is_file():
            return ConnectorExecutionResult(
                provider=str(connector.get("provider", "unknown")),
                status="file_not_found",
                summary=f"Configured dataset path was not found: {resolved_path}",
                checks=["Verify the export file exists and the path is correct."],
                next_steps=["Point the connector at a reachable CSV export file."],
                payload={"connector_id": connector.get("id"), "path": str(resolved_path)},
            )
        normalized_df = read_connector_dataframe(
            resolved_path,
            provider=str(connector.get("provider", "")),
        )
        source_name = resolved_path.name
        return normalized_df, source_name


def execute_connector_sync(
    connector: dict[str, Any],
    *,
    org_id: int,
    created_by: int | None = None,
    trigger_mode: str = "manual",
    job_id: int | None = None,
) -> ConnectorExecutionResult:
    """Execute a connector sync using the configured export source."""
    from database.service import ConnectorJobService, ConnectorService, IngestionRunService

    metadata = connector.get("metadata_json") or {}
    dataset_path = metadata.get("local_dataset_path")
    if not dataset_path:
        result = ConnectorExecutionResult(
            provider=str(connector.get("provider", "unknown")),
            status="missing_dataset_path",
            summary="No local dataset path is configured for this connector.",
            checks=["Set a local export file path before running a sync."],
            next_steps=["Save a valid CSV path in connector execution settings."],
            payload={"connector_id": connector.get("id")},
        )
        if job_id is not None:
            ConnectorJobService.complete_job(job_id, status="failed", worker_notes=result.summary, payload=result.payload)
        return result

    loaded = _load_connector_dataframe(connector, dataset_path)
    if isinstance(loaded, ConnectorExecutionResult):
        if job_id is not None:
            ConnectorJobService.complete_job(job_id, status="failed", worker_notes=loaded.summary, payload=loaded.payload)
        ConnectorService.mark_sync(int(connector["id"]), status="failed", notes=loaded.summary)
        return loaded

    normalized_df, source_name = loaded

    result = IngestionRunService.persist_normalized_dataset(
        org_id=org_id,
        normalized_df=normalized_df,
        source_name=source_name,
        provider=str(connector.get("provider", "AWS")),
        account_name=str(metadata.get("account_name") or connector.get("connector_name") or "connector-account"),
        account_id=str(connector.get("external_reference") or source_name),
        created_by=created_by,
        connector_id=int(connector["id"]),
    )
    ConnectorService.mark_sync(
        int(connector["id"]),
        status="connected",
        notes=f"Last {trigger_mode} sync from {source_name} with {result['rows_persisted']} grouped records.",
    )
    execution_result = ConnectorExecutionResult(
        provider=str(connector.get("provider", "unknown")),
        status="completed",
        summary=(
            f"Connector sync completed from {source_name}. "
            f"{result['rows_persisted']} grouped records were persisted into the workspace."
        ),
        checks=[
            "Export file was found.",
            "Dataset was normalized successfully.",
            "Workspace tables were updated from connector sync.",
        ],
        next_steps=[
            "Review ingestion history in Integrations Hub.",
            "Check Operations Center for any new alerts or actions.",
        ],
        payload={
            "connector_id": connector.get("id"),
            "path": str(dataset_path),
            "rows_persisted": result["rows_persisted"],
            "projects": result["projects_created_or_matched"],
            "trigger_mode": trigger_mode,
            "job_id": job_id,
            "completed_at": datetime.utcnow().isoformat(),
        },
    )
    if job_id is not None:
        ConnectorJobService.complete_job(
            job_id,
            status="completed",
            worker_notes=execution_result.summary,
            payload=execution_result.payload,
        )
    return execution_result


def run_file_sync(connector: dict[str, Any], *, org_id: int, created_by: int | None = None) -> ConnectorExecutionResult:
    """Execute a local or remote export sync directly from the UI."""
    return execute_connector_sync(
        connector,
        org_id=org_id,
        created_by=created_by,
        trigger_mode="manual",
    )


def run_connector_job(job: dict[str, Any]) -> ConnectorExecutionResult:
    """Run one claimed connector job."""
    from database.service import ConnectorService

    connector = ConnectorService.get_connector(int(job["connector_id"]))
    if not connector:
        return ConnectorExecutionResult(
            provider="unknown",
            status="failed",
            summary=f"Connector {job['connector_id']} was not found for queued job {job['id']}.",
            checks=["Verify the connector still exists."],
            next_steps=["Re-register the connector or remove the invalid job."],
            payload={"job_id": job["id"], "connector_id": job["connector_id"]},
        )
    return execute_connector_sync(
        connector,
        org_id=int(job["organization_id"]),
        created_by=job.get("requested_by"),
        trigger_mode=str(job.get("trigger_mode") or "scheduled"),
        job_id=int(job["id"]),
    )


def execute_due_jobs(limit: int = 5) -> list[ConnectorExecutionResult]:
    """Claim and run a batch of due connector jobs."""
    from database.service import ConnectorJobService

    claimed_jobs = ConnectorJobService.claim_due_jobs(limit=limit)
    results: list[ConnectorExecutionResult] = []
    for job in claimed_jobs:
        results.append(run_connector_job(job))
    return results
