"""Database service layer for SaaS workflows."""

from __future__ import annotations

from datetime import datetime, timedelta
import hashlib
import secrets
from typing import Any

from sqlalchemy import desc, func, insert, select, update

from database.connection import (
    activity_events,
    action_items,
    alerts,
    api_keys,
    audit_logs,
    carbon_results,
    cloud_accounts,
    connector_sync_jobs,
    data_connectors,
    forecast_models,
    get_connection,
    ingestion_runs,
    memberships,
    organizations,
    projects,
    recommendations,
    saved_reports,
    usage_data,
    users,
)
from database.models import (
    CarbonResultModel,
    CloudAccountModel,
    OrganizationModel,
    RecommendationModel,
    UsageDataModel,
    UserModel,
)


def _row_to_dict(row: Any) -> dict[str, Any]:
    """Convert a SQLAlchemy row into a plain dict."""
    return dict(row._mapping)


ROLE_PERMISSIONS = {
    "owner": {"workspace.admin", "reports.write", "integrations.write", "forecast.write", "actions.write"},
    "admin": {"reports.write", "integrations.write", "forecast.write", "actions.write"},
    "finops": {"reports.write", "forecast.write", "actions.write"},
    "sustainability": {"reports.write", "forecast.write", "actions.write"},
    "member": set(),
}


class UserService:
    """Service for user operations."""

    @staticmethod
    def create_user(email: str, password: str, full_name: str | None = None) -> UserModel:
        """Create a new user."""
        password_hash = hashlib.sha256(password.encode()).hexdigest()
        with get_connection() as connection:
            user_id = connection.execute(
                insert(users).values(
                    email=email,
                    password_hash=password_hash,
                    full_name=full_name,
                )
            ).inserted_primary_key[0]
        return UserService.get_user(user_id)

    @staticmethod
    def get_user(user_id: int) -> UserModel | None:
        """Get user by ID."""
        with get_connection() as connection:
            row = connection.execute(select(users).where(users.c.id == user_id)).fetchone()
        return UserModel(**_row_to_dict(row)) if row else None

    @staticmethod
    def get_user_by_email(email: str) -> UserModel | None:
        """Get user by email."""
        with get_connection() as connection:
            row = connection.execute(select(users).where(users.c.email == email)).fetchone()
        return UserModel(**_row_to_dict(row)) if row else None

    @staticmethod
    def authenticate(email: str, password: str) -> UserModel | None:
        """Authenticate a user by email and password."""
        user = UserService.get_user_by_email(email)
        if not user:
            return None
        password_hash = hashlib.sha256(password.encode()).hexdigest()
        return user if password_hash == user.password_hash else None


class OrganizationService:
    """Service for organization operations."""

    @staticmethod
    def create_organization(
        name: str,
        owner_id: int,
        description: str | None = None,
        plan: str = "starter",
    ) -> OrganizationModel:
        """Create a new organization and owner membership."""
        with get_connection() as connection:
            org_id = connection.execute(
                insert(organizations).values(
                    name=name,
                    owner_id=owner_id,
                    description=description,
                    plan=plan,
                )
            ).inserted_primary_key[0]
            connection.execute(
                insert(memberships).values(
                    user_id=owner_id,
                    organization_id=org_id,
                    role="owner",
                )
            )
        return OrganizationService.get_organization(org_id)

    @staticmethod
    def get_organization(org_id: int) -> OrganizationModel | None:
        """Get organization by ID."""
        with get_connection() as connection:
            row = connection.execute(
                select(organizations).where(organizations.c.id == org_id)
            ).fetchone()
        return OrganizationModel(**_row_to_dict(row)) if row else None

    @staticmethod
    def get_user_organizations(user_id: int) -> list[OrganizationModel]:
        """Get all organizations for a user."""
        statement = (
            select(organizations)
            .join(memberships, memberships.c.organization_id == organizations.c.id)
            .where(memberships.c.user_id == user_id)
            .order_by(organizations.c.created_at.asc())
        )
        with get_connection() as connection:
            rows = connection.execute(statement).fetchall()
        return [OrganizationModel(**_row_to_dict(row)) for row in rows]

    @staticmethod
    def update_organization(
        org_id: int,
        *,
        name: str | None = None,
        description: str | None = None,
        plan: str | None = None,
    ) -> OrganizationModel | None:
        """Update editable organization fields."""
        values: dict[str, Any] = {}
        if name is not None:
            values["name"] = name
        if description is not None:
            values["description"] = description
        if plan is not None:
            values["plan"] = plan
        if not values:
            return OrganizationService.get_organization(org_id)
        with get_connection() as connection:
            connection.execute(
                update(organizations)
                .where(organizations.c.id == org_id)
                .values(**values)
            )
        return OrganizationService.get_organization(org_id)


class MembershipService:
    """Service for organization membership operations."""

    @staticmethod
    def add_member(
        org_id: int,
        user_id: int,
        role: str = "member",
    ) -> None:
        """Add a membership if it does not already exist."""
        with get_connection() as connection:
            existing = connection.execute(
                select(memberships.c.id).where(
                    memberships.c.organization_id == org_id,
                    memberships.c.user_id == user_id,
                )
            ).fetchone()
            if existing:
                connection.execute(
                    update(memberships)
                    .where(memberships.c.id == existing._mapping["id"])
                    .values(role=role)
                )
                return
            connection.execute(
                insert(memberships).values(
                    organization_id=org_id,
                    user_id=user_id,
                    role=role,
                )
            )

    @staticmethod
    def get_org_members(org_id: int) -> list[dict[str, Any]]:
        """Return members for an organization with user details."""
        statement = (
            select(
                memberships.c.id,
                memberships.c.role,
                memberships.c.created_at,
                users.c.id.label("user_id"),
                users.c.email,
                users.c.full_name,
                users.c.is_active,
            )
            .join(users, users.c.id == memberships.c.user_id)
            .where(memberships.c.organization_id == org_id)
            .order_by(memberships.c.created_at.asc())
        )
        with get_connection() as connection:
            rows = connection.execute(statement).fetchall()
        return [_row_to_dict(row) for row in rows]

    @staticmethod
    def get_member_role(org_id: int, user_id: int) -> str | None:
        """Return the organization role for a user."""
        with get_connection() as connection:
            row = connection.execute(
                select(memberships.c.role).where(
                    memberships.c.organization_id == org_id,
                    memberships.c.user_id == user_id,
                )
            ).fetchone()
        return str(row._mapping["role"]) if row else None

    @staticmethod
    def has_permission(org_id: int, user_id: int, permission: str) -> bool:
        """Return whether a user has a named permission in the org."""
        role = MembershipService.get_member_role(org_id, user_id)
        if not role:
            return False
        if role == "owner":
            return True
        return permission in ROLE_PERMISSIONS.get(role, set())


class ProjectService:
    """Service for project operations."""

    @staticmethod
    def create_project(
        org_id: int,
        name: str,
        cloud_provider: str,
        region: str,
        monthly_budget: float | None = None,
    ) -> dict[str, Any]:
        """Create a project."""
        with get_connection() as connection:
            project_id = connection.execute(
                insert(projects).values(
                    organization_id=org_id,
                    name=name,
                    cloud_provider=cloud_provider,
                    region=region,
                    monthly_budget=monthly_budget,
                )
            ).inserted_primary_key[0]
            row = connection.execute(select(projects).where(projects.c.id == project_id)).fetchone()
        return _row_to_dict(row)

    @staticmethod
    def get_org_projects(org_id: int) -> list[dict[str, Any]]:
        """Get projects for an organization."""
        with get_connection() as connection:
            rows = connection.execute(
                select(projects)
                .where(projects.c.organization_id == org_id)
                .order_by(projects.c.created_at.desc())
            ).fetchall()
        return [_row_to_dict(row) for row in rows]

    @staticmethod
    def get_or_create_project(
        org_id: int,
        name: str,
        cloud_provider: str,
        region: str,
        monthly_budget: float | None = None,
    ) -> dict[str, Any]:
        """Return an existing project by name or create it."""
        with get_connection() as connection:
            row = connection.execute(
                select(projects).where(
                    projects.c.organization_id == org_id,
                    projects.c.name == name,
                )
            ).fetchone()
        if row:
            return _row_to_dict(row)
        return ProjectService.create_project(
            org_id=org_id,
            name=name,
            cloud_provider=cloud_provider,
            region=region,
            monthly_budget=monthly_budget,
        )


class UsageDataService:
    """Service for usage data operations."""

    @staticmethod
    def create_usage_data(
        org_id: int,
        resource_type: str,
        quantity: float,
        unit: str,
        region: str,
        cost: float | None = None,
        cloud_account_id: int | None = None,
        project_id: int | None = None,
        timestamp: datetime | None = None,
    ) -> UsageDataModel:
        """Create usage data record."""
        with get_connection() as connection:
            record_id = connection.execute(
                insert(usage_data).values(
                    organization_id=org_id,
                    project_id=project_id,
                    cloud_account_id=cloud_account_id,
                    resource_type=resource_type,
                    quantity=quantity,
                    unit=unit,
                    region=region,
                    cost=cost,
                    timestamp=timestamp or datetime.utcnow(),
                )
            ).inserted_primary_key[0]
            row = connection.execute(select(usage_data).where(usage_data.c.id == record_id)).fetchone()
        return UsageDataModel(**_row_to_dict(row))

    @staticmethod
    def get_org_usage_data(org_id: int, days: int = 30) -> list[UsageDataModel]:
        """Get usage data for organization in last N days."""
        since = datetime.utcnow() - timedelta(days=days)
        with get_connection() as connection:
            rows = connection.execute(
                select(usage_data)
                .where(usage_data.c.organization_id == org_id)
                .where(usage_data.c.timestamp >= since)
                .order_by(usage_data.c.timestamp.desc())
            ).fetchall()
        return [UsageDataModel(**_row_to_dict(row)) for row in rows]


class CarbonResultService:
    """Service for carbon result operations."""

    @staticmethod
    def create_carbon_result(
        org_id: int,
        energy_kwh: float,
        carbon_kg_co2: float,
        compute_energy: float | None = None,
        storage_energy: float | None = None,
        network_energy: float | None = None,
        region: str | None = None,
        project_id: int | None = None,
        timestamp: datetime | None = None,
    ) -> CarbonResultModel:
        """Create carbon result record."""
        with get_connection() as connection:
            record_id = connection.execute(
                insert(carbon_results).values(
                    organization_id=org_id,
                    project_id=project_id,
                    energy_kwh=energy_kwh,
                    carbon_kg_co2=carbon_kg_co2,
                    compute_energy=compute_energy,
                    storage_energy=storage_energy,
                    network_energy=network_energy,
                    region=region,
                    timestamp=timestamp or datetime.utcnow(),
                )
            ).inserted_primary_key[0]
            row = connection.execute(
                select(carbon_results).where(carbon_results.c.id == record_id)
            ).fetchone()
        return CarbonResultModel(**_row_to_dict(row))

    @staticmethod
    def get_org_carbon_history(org_id: int, days: int = 30) -> list[CarbonResultModel]:
        """Get carbon results for organization in last N days."""
        since = datetime.utcnow() - timedelta(days=days)
        with get_connection() as connection:
            rows = connection.execute(
                select(carbon_results)
                .where(carbon_results.c.organization_id == org_id)
                .where(carbon_results.c.timestamp >= since)
                .order_by(carbon_results.c.timestamp.asc())
            ).fetchall()
        return [CarbonResultModel(**_row_to_dict(row)) for row in rows]

    @staticmethod
    def get_total_carbon(org_id: int, days: int = 30) -> float:
        """Get total carbon for organization in last N days."""
        since = datetime.utcnow() - timedelta(days=days)
        statement = select(func.sum(carbon_results.c.carbon_kg_co2)).where(
            carbon_results.c.organization_id == org_id,
            carbon_results.c.timestamp >= since,
        )
        with get_connection() as connection:
            total = connection.execute(statement).scalar()
        return float(total or 0.0)


class RecommendationService:
    """Service for recommendation operations."""

    @staticmethod
    def create_recommendation(
        org_id: int,
        suggestion: str,
        carbon_saving_percent: float | None = None,
        cost_impact: float | None = None,
        priority: str = "medium",
        implemented: bool = False,
    ) -> RecommendationModel:
        """Create recommendation record."""
        with get_connection() as connection:
            rec_id = connection.execute(
                insert(recommendations).values(
                    organization_id=org_id,
                    suggestion=suggestion,
                    carbon_saving_percent=carbon_saving_percent,
                    cost_impact=cost_impact,
                    priority=priority,
                    is_implemented=implemented,
                )
            ).inserted_primary_key[0]
            row = connection.execute(
                select(recommendations).where(recommendations.c.id == rec_id)
            ).fetchone()
        return RecommendationModel(**_row_to_dict(row))

    @staticmethod
    def get_org_recommendations(org_id: int, implemented: bool | None = None) -> list[RecommendationModel]:
        """Get recommendations for organization."""
        statement = select(recommendations).where(recommendations.c.organization_id == org_id)
        if implemented is not None:
            statement = statement.where(recommendations.c.is_implemented == implemented)
        statement = statement.order_by(desc(recommendations.c.created_at))
        with get_connection() as connection:
            rows = connection.execute(statement).fetchall()
        return [RecommendationModel(**_row_to_dict(row)) for row in rows]


class CloudAccountService:
    """Service for cloud account operations."""

    @staticmethod
    def create_cloud_account(
        org_id: int,
        provider: str,
        account_name: str,
        account_id: str,
        region: str | None = None,
    ) -> CloudAccountModel:
        """Create cloud account record."""
        with get_connection() as connection:
            acc_id = connection.execute(
                insert(cloud_accounts).values(
                    organization_id=org_id,
                    provider=provider,
                    account_name=account_name,
                    account_id=account_id,
                    region=region,
                )
            ).inserted_primary_key[0]
            row = connection.execute(
                select(cloud_accounts).where(cloud_accounts.c.id == acc_id)
            ).fetchone()
        return CloudAccountModel(**_row_to_dict(row))

    @staticmethod
    def get_org_cloud_accounts(org_id: int) -> list[CloudAccountModel]:
        """Get all active cloud accounts for organization."""
        with get_connection() as connection:
            rows = connection.execute(
                select(cloud_accounts)
                .where(cloud_accounts.c.organization_id == org_id)
                .where(cloud_accounts.c.is_active.is_(True))
                .order_by(cloud_accounts.c.created_at.desc())
            ).fetchall()
        return [CloudAccountModel(**_row_to_dict(row)) for row in rows]

    @staticmethod
    def get_or_create_cloud_account(
        org_id: int,
        provider: str,
        account_name: str,
        account_id: str,
        region: str | None = None,
    ) -> CloudAccountModel:
        """Return an existing account by provider/account_id or create it."""
        with get_connection() as connection:
            row = connection.execute(
                select(cloud_accounts).where(
                    cloud_accounts.c.organization_id == org_id,
                    cloud_accounts.c.provider == provider,
                    cloud_accounts.c.account_id == account_id,
                )
            ).fetchone()
        if row:
            return CloudAccountModel(**_row_to_dict(row))
        return CloudAccountService.create_cloud_account(
            org_id=org_id,
            provider=provider,
            account_name=account_name,
            account_id=account_id,
            region=region,
        )


class SavedReportService:
    """Service for saved report operations."""

    @staticmethod
    def create_report(
        org_id: int,
        title: str,
        report_type: str,
        summary: str,
        payload: dict[str, Any] | None = None,
        created_by: int | None = None,
    ) -> dict[str, Any]:
        """Create a saved report."""
        with get_connection() as connection:
            report_id = connection.execute(
                insert(saved_reports).values(
                    organization_id=org_id,
                    title=title,
                    report_type=report_type,
                    summary=summary,
                    payload=payload,
                    created_by=created_by,
                )
            ).inserted_primary_key[0]
            row = connection.execute(
                select(saved_reports).where(saved_reports.c.id == report_id)
            ).fetchone()
        return _row_to_dict(row)

    @staticmethod
    def get_org_reports(org_id: int, limit: int = 5) -> list[dict[str, Any]]:
        """Get recent saved reports."""
        with get_connection() as connection:
            rows = connection.execute(
                select(saved_reports)
                .where(saved_reports.c.organization_id == org_id)
                .order_by(desc(saved_reports.c.created_at))
                .limit(limit)
            ).fetchall()
        return [_row_to_dict(row) for row in rows]


class ConnectorService:
    """Service for external cloud and dataset connectors."""

    @staticmethod
    def create_connector(
        org_id: int,
        provider: str,
        connector_name: str,
        auth_mode: str,
        *,
        status: str = "planned",
        external_reference: str | None = None,
        scope_region: str | None = None,
        sync_frequency: str | None = None,
        notes: str | None = None,
        metadata_json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create a connector definition."""
        with get_connection() as connection:
            existing = connection.execute(
                select(data_connectors).where(
                    data_connectors.c.organization_id == org_id,
                    data_connectors.c.connector_name == connector_name,
                )
            ).fetchone()
            if existing:
                return _row_to_dict(existing)
            connector_id = connection.execute(
                insert(data_connectors).values(
                    organization_id=org_id,
                    provider=provider,
                    connector_name=connector_name,
                    auth_mode=auth_mode,
                    status=status,
                    external_reference=external_reference,
                    scope_region=scope_region,
                    sync_frequency=sync_frequency,
                    notes=notes,
                    metadata_json=metadata_json,
                    last_sync_at=datetime.utcnow() if status == "connected" else None,
                )
            ).inserted_primary_key[0]
            row = connection.execute(
                select(data_connectors).where(data_connectors.c.id == connector_id)
            ).fetchone()
        return _row_to_dict(row)

    @staticmethod
    def get_org_connectors(org_id: int) -> list[dict[str, Any]]:
        """Return connectors configured for an organization."""
        with get_connection() as connection:
            rows = connection.execute(
                select(data_connectors)
                .where(data_connectors.c.organization_id == org_id)
                .order_by(desc(data_connectors.c.created_at))
            ).fetchall()
        return [_row_to_dict(row) for row in rows]

    @staticmethod
    def get_connector(connector_id: int) -> dict[str, Any] | None:
        """Return one connector definition."""
        with get_connection() as connection:
            row = connection.execute(
                select(data_connectors).where(data_connectors.c.id == connector_id)
            ).fetchone()
        return _row_to_dict(row) if row else None

    @staticmethod
    def update_connector(
        connector_id: int,
        *,
        status: str | None = None,
        notes: str | None = None,
        metadata_json: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """Update mutable connector fields."""
        values: dict[str, Any] = {"updated_at": datetime.utcnow()}
        if status is not None:
            values["status"] = status
            if status == "connected":
                values["last_sync_at"] = datetime.utcnow()
        if notes is not None:
            values["notes"] = notes
        if metadata_json is not None:
            values["metadata_json"] = metadata_json
        with get_connection() as connection:
            connection.execute(
                update(data_connectors)
                .where(data_connectors.c.id == connector_id)
                .values(**values)
            )
            row = connection.execute(
                select(data_connectors).where(data_connectors.c.id == connector_id)
            ).fetchone()
        return _row_to_dict(row) if row else None

    @staticmethod
    def mark_sync(
        connector_id: int,
        *,
        status: str,
        notes: str | None = None,
    ) -> None:
        """Update connector sync metadata."""
        values: dict[str, Any] = {"status": status, "updated_at": datetime.utcnow()}
        if status == "connected":
            values["last_sync_at"] = datetime.utcnow()
        if notes is not None:
            values["notes"] = notes
        with get_connection() as connection:
            connection.execute(
                update(data_connectors)
                .where(data_connectors.c.id == connector_id)
                .values(**values)
            )


class ConnectorJobService:
    """Service for queued and scheduled connector sync work."""

    @staticmethod
    def queue_sync_job(
        org_id: int,
        connector_id: int,
        *,
        trigger_mode: str = "manual",
        requested_by: int | None = None,
        payload: dict[str, Any] | None = None,
        next_run_at: datetime | None = None,
    ) -> dict[str, Any]:
        """Queue a connector sync job."""
        with get_connection() as connection:
            job_id = connection.execute(
                insert(connector_sync_jobs).values(
                    organization_id=org_id,
                    connector_id=connector_id,
                    trigger_mode=trigger_mode,
                    status="pending",
                    requested_by=requested_by,
                    payload=payload,
                    next_run_at=next_run_at or datetime.utcnow(),
                )
            ).inserted_primary_key[0]
            row = connection.execute(
                select(connector_sync_jobs).where(connector_sync_jobs.c.id == job_id)
            ).fetchone()
        return _row_to_dict(row)

    @staticmethod
    def get_org_jobs(org_id: int, limit: int = 20) -> list[dict[str, Any]]:
        """Return recent sync jobs with connector context."""
        statement = (
            select(
                connector_sync_jobs,
                data_connectors.c.connector_name,
                data_connectors.c.provider,
            )
            .join(data_connectors, data_connectors.c.id == connector_sync_jobs.c.connector_id)
            .where(connector_sync_jobs.c.organization_id == org_id)
            .order_by(desc(connector_sync_jobs.c.queued_at))
            .limit(limit)
        )
        with get_connection() as connection:
            rows = connection.execute(statement).fetchall()
        return [_row_to_dict(row) for row in rows]

    @staticmethod
    def claim_due_jobs(limit: int = 5) -> list[dict[str, Any]]:
        """Claim queued jobs that are ready to run."""
        now = datetime.utcnow()
        with get_connection() as connection:
            rows = connection.execute(
                select(connector_sync_jobs)
                .where(connector_sync_jobs.c.status == "pending")
                .where(connector_sync_jobs.c.next_run_at <= now)
                .order_by(connector_sync_jobs.c.queued_at.asc())
                .limit(limit)
            ).fetchall()

            claimed_jobs: list[dict[str, Any]] = []
            for row in rows:
                job = _row_to_dict(row)
                connection.execute(
                    update(connector_sync_jobs)
                    .where(connector_sync_jobs.c.id == job["id"])
                    .values(
                        status="running",
                        started_at=now,
                        attempt_count=int(job.get("attempt_count") or 0) + 1,
                    )
                )
                claimed_row = connection.execute(
                    select(connector_sync_jobs).where(connector_sync_jobs.c.id == job["id"])
                ).fetchone()
                if claimed_row:
                    claimed_jobs.append(_row_to_dict(claimed_row))
        return claimed_jobs

    @staticmethod
    def complete_job(
        job_id: int,
        *,
        status: str,
        worker_notes: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """Mark a queued job complete or failed."""
        values: dict[str, Any] = {
            "status": status,
            "completed_at": datetime.utcnow(),
        }
        if worker_notes is not None:
            values["worker_notes"] = worker_notes
        if payload is not None:
            values["payload"] = payload
        with get_connection() as connection:
            connection.execute(
                update(connector_sync_jobs)
                .where(connector_sync_jobs.c.id == job_id)
                .values(**values)
            )
            row = connection.execute(
                select(connector_sync_jobs).where(connector_sync_jobs.c.id == job_id)
            ).fetchone()
        return _row_to_dict(row) if row else None


class AuditLogService:
    """Service for enterprise audit logging."""

    @staticmethod
    def log(
        org_id: int,
        action: str,
        entity_type: str,
        *,
        entity_id: str | None = None,
        user_id: int | None = None,
        severity: str = "info",
        description: str | None = None,
        metadata_json: dict[str, Any] | None = None,
    ) -> None:
        """Persist an audit log entry."""
        with get_connection() as connection:
            connection.execute(
                insert(audit_logs).values(
                    organization_id=org_id,
                    user_id=user_id,
                    action=action,
                    entity_type=entity_type,
                    entity_id=entity_id,
                    severity=severity,
                    description=description,
                    metadata_json=metadata_json,
                )
            )

    @staticmethod
    def get_org_logs(org_id: int, limit: int = 25) -> list[dict[str, Any]]:
        """Return recent audit log entries."""
        with get_connection() as connection:
            rows = connection.execute(
                select(audit_logs)
                .where(audit_logs.c.organization_id == org_id)
                .order_by(desc(audit_logs.c.created_at))
                .limit(limit)
            ).fetchall()
        return [_row_to_dict(row) for row in rows]


class AlertService:
    """Service for operational alerts."""

    @staticmethod
    def create_alert(
        org_id: int,
        title: str,
        category: str,
        *,
        description: str | None = None,
        severity: str = "medium",
        project_id: int | None = None,
        metric_value: float | None = None,
        threshold_value: float | None = None,
        metadata_json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create an alert if an open duplicate does not already exist."""
        with get_connection() as connection:
            existing = connection.execute(
                select(alerts).where(
                    alerts.c.organization_id == org_id,
                    alerts.c.title == title,
                    alerts.c.status == "open",
                )
            ).fetchone()
            if existing:
                return _row_to_dict(existing)
            alert_id = connection.execute(
                insert(alerts).values(
                    organization_id=org_id,
                    project_id=project_id,
                    title=title,
                    description=description,
                    severity=severity,
                    category=category,
                    metric_value=metric_value,
                    threshold_value=threshold_value,
                    metadata_json=metadata_json,
                )
            ).inserted_primary_key[0]
            row = connection.execute(select(alerts).where(alerts.c.id == alert_id)).fetchone()
        return _row_to_dict(row)

    @staticmethod
    def get_org_alerts(org_id: int, status: str | None = None, limit: int = 20) -> list[dict[str, Any]]:
        """Return organization alerts."""
        statement = select(alerts).where(alerts.c.organization_id == org_id)
        if status:
            statement = statement.where(alerts.c.status == status)
        statement = statement.order_by(desc(alerts.c.created_at)).limit(limit)
        with get_connection() as connection:
            rows = connection.execute(statement).fetchall()
        return [_row_to_dict(row) for row in rows]

    @staticmethod
    def generate_workspace_alerts(org_id: int) -> list[dict[str, Any]]:
        """Generate high-value alerts from current workspace state."""
        workspace = DashboardService.get_workspace_snapshot(org_id)
        created: list[dict[str, Any]] = []
        for project in workspace["portfolio"]:
            if float(project["carbon_kg"]) > 1000:
                created.append(
                    AlertService.create_alert(
                        org_id=org_id,
                        project_id=project["project_id"],
                        title=f"High carbon exposure: {project['name']}",
                        description=f"{project['name']} is above the review threshold for tracked carbon.",
                        category="carbon",
                        severity="high",
                        metric_value=float(project["carbon_kg"]),
                        threshold_value=1000.0,
                        metadata_json={"project": project["name"]},
                    )
                )
        if workspace["headline"]["estimated_monthly_spend"] > workspace["headline"]["monthly_budget"] * 0.9:
            created.append(
                AlertService.create_alert(
                    org_id=org_id,
                    title="Budget exposure approaching limit",
                    description="Estimated monthly spend is within 10% of the registered budget baseline.",
                    category="cost",
                    severity="medium",
                    metric_value=float(workspace["headline"]["estimated_monthly_spend"]),
                    threshold_value=float(workspace["headline"]["monthly_budget"] * 0.9),
                )
            )
        return created


class ActionItemService:
    """Service for enterprise action tracking."""

    @staticmethod
    def create_action_item(
        org_id: int,
        title: str,
        *,
        description: str | None = None,
        owner_user_id: int | None = None,
        priority: str = "medium",
        due_date: datetime | None = None,
        alert_id: int | None = None,
        recommendation_id: int | None = None,
    ) -> dict[str, Any]:
        """Create an action item."""
        with get_connection() as connection:
            item_id = connection.execute(
                insert(action_items).values(
                    organization_id=org_id,
                    alert_id=alert_id,
                    recommendation_id=recommendation_id,
                    title=title,
                    description=description,
                    owner_user_id=owner_user_id,
                    priority=priority,
                    due_date=due_date,
                )
            ).inserted_primary_key[0]
            row = connection.execute(select(action_items).where(action_items.c.id == item_id)).fetchone()
        return _row_to_dict(row)

    @staticmethod
    def get_org_action_items(org_id: int, limit: int = 20) -> list[dict[str, Any]]:
        """Return open and recent action items."""
        statement = (
            select(
                action_items,
                users.c.full_name.label("owner_name"),
                users.c.email.label("owner_email"),
            )
            .select_from(action_items.outerjoin(users, users.c.id == action_items.c.owner_user_id))
            .where(action_items.c.organization_id == org_id)
            .order_by(desc(action_items.c.created_at))
            .limit(limit)
        )
        with get_connection() as connection:
            rows = connection.execute(statement).fetchall()
        return [_row_to_dict(row) for row in rows]


class ForecastModelService:
    """Service for persisted forecasting model metadata."""

    @staticmethod
    def create_model_run(
        org_id: int,
        name: str,
        source_type: str,
        training_rows: int,
        horizon_days: int,
        *,
        mae: float | None = None,
        mape: float | None = None,
        residual_std: float | None = None,
        metadata_json: dict[str, Any] | None = None,
        created_by: int | None = None,
    ) -> dict[str, Any]:
        """Persist a trained forecast run."""
        with get_connection() as connection:
            model_id = connection.execute(
                insert(forecast_models).values(
                    organization_id=org_id,
                    name=name,
                    source_type=source_type,
                    training_rows=training_rows,
                    horizon_days=horizon_days,
                    mae=mae,
                    mape=mape,
                    residual_std=residual_std,
                    metadata_json=metadata_json,
                    created_by=created_by,
                )
            ).inserted_primary_key[0]
            row = connection.execute(
                select(forecast_models).where(forecast_models.c.id == model_id)
            ).fetchone()
        return _row_to_dict(row)

    @staticmethod
    def get_org_models(org_id: int, limit: int = 10) -> list[dict[str, Any]]:
        """Return recent forecast model runs."""
        with get_connection() as connection:
            rows = connection.execute(
                select(forecast_models)
                .where(forecast_models.c.organization_id == org_id)
                .order_by(desc(forecast_models.c.created_at))
                .limit(limit)
            ).fetchall()
        return [_row_to_dict(row) for row in rows]


class IngestionRunService:
    """Service for ingestion history and persisted dataset imports."""

    @staticmethod
    def log_run(
        org_id: int,
        source_type: str,
        source_name: str,
        records_ingested: int,
        total_carbon_kg_co2: float,
        *,
        status: str = "completed",
        connector_id: int | None = None,
        payload: dict[str, Any] | None = None,
        created_by: int | None = None,
    ) -> dict[str, Any]:
        """Create an ingestion run record."""
        with get_connection() as connection:
            run_id = connection.execute(
                insert(ingestion_runs).values(
                    organization_id=org_id,
                    connector_id=connector_id,
                    source_type=source_type,
                    source_name=source_name,
                    status=status,
                    records_ingested=records_ingested,
                    total_carbon_kg_co2=total_carbon_kg_co2,
                    payload=payload,
                    created_by=created_by,
                    started_at=datetime.utcnow(),
                    completed_at=datetime.utcnow(),
                )
            ).inserted_primary_key[0]
            row = connection.execute(
                select(ingestion_runs).where(ingestion_runs.c.id == run_id)
            ).fetchone()
        return _row_to_dict(row)

    @staticmethod
    def get_org_runs(org_id: int, limit: int = 8) -> list[dict[str, Any]]:
        """Return recent ingestion runs."""
        with get_connection() as connection:
            rows = connection.execute(
                select(ingestion_runs)
                .where(ingestion_runs.c.organization_id == org_id)
                .order_by(desc(ingestion_runs.c.completed_at))
                .limit(limit)
            ).fetchall()
        return [_row_to_dict(row) for row in rows]

    @staticmethod
    def persist_normalized_dataset(
        org_id: int,
        normalized_df: Any,
        *,
        source_name: str,
        provider: str,
        account_name: str,
        account_id: str,
        created_by: int | None = None,
        connector_id: int | None = None,
    ) -> dict[str, Any]:
        """Persist normalized dataset rows into workspace usage and carbon tables."""
        account = CloudAccountService.get_or_create_cloud_account(
            org_id=org_id,
            provider=provider,
            account_name=account_name,
            account_id=account_id,
        )

        grouped = (
            normalized_df.groupby(["timestamp", "project", "service", "region"], as_index=False)
            .agg(
                {
                    "vm_hours": "sum",
                    "storage_gb": "sum",
                    "network_gb": "sum",
                    "energy_kwh": "sum",
                    "carbon": "sum",
                    "cost": "sum",
                }
            )
        )

        created_projects: set[str] = set()
        for record in grouped.to_dict(orient="records"):
            project = ProjectService.get_or_create_project(
                org_id=org_id,
                name=str(record["project"]),
                cloud_provider=provider,
                region=str(record["region"]),
            )
            created_projects.add(project["name"])
            timestamp = record["timestamp"]
            if hasattr(timestamp, "to_pydatetime"):
                timestamp = timestamp.to_pydatetime()

            usage_quantity = float(record["vm_hours"] or 0.0)
            if usage_quantity <= 0:
                usage_quantity = float(record["energy_kwh"] or 0.0)
            UsageDataService.create_usage_data(
                org_id=org_id,
                project_id=project["id"],
                cloud_account_id=account.id,
                resource_type=str(record["service"]),
                quantity=usage_quantity,
                unit="vm_hours" if float(record["vm_hours"] or 0.0) > 0 else "energy_kwh",
                region=str(record["region"]),
                cost=float(record["cost"] or 0.0),
                timestamp=timestamp,
            )
            CarbonResultService.create_carbon_result(
                org_id=org_id,
                project_id=project["id"],
                energy_kwh=float(record["energy_kwh"] or 0.0),
                carbon_kg_co2=float(record["carbon"] or 0.0),
                compute_energy=float(record["vm_hours"] or 0.0),
                storage_energy=float(record["storage_gb"] or 0.0),
                network_energy=float(record["network_gb"] or 0.0),
                region=str(record["region"]),
                timestamp=timestamp,
            )

        run = IngestionRunService.log_run(
            org_id=org_id,
            connector_id=connector_id,
            source_type="dataset_upload",
            source_name=source_name,
            records_ingested=int(len(grouped)),
            total_carbon_kg_co2=float(grouped["carbon"].sum()),
            created_by=created_by,
            payload={
                "provider": provider,
                "account_name": account_name,
                "account_id": account_id,
                "projects": sorted(created_projects),
            },
        )
        return {
            "run": run,
            "account": account,
            "projects_created_or_matched": sorted(created_projects),
            "rows_persisted": int(len(grouped)),
        }


class ActivityService:
    """Service for activity events."""

    @staticmethod
    def log_event(
        org_id: int,
        title: str,
        description: str,
        event_type: str = "info",
        user_id: int | None = None,
        metadata_json: dict[str, Any] | None = None,
    ) -> None:
        """Log an organization activity event."""
        with get_connection() as connection:
            connection.execute(
                insert(activity_events).values(
                    organization_id=org_id,
                    user_id=user_id,
                    event_type=event_type,
                    title=title,
                    description=description,
                    metadata_json=metadata_json,
                )
            )

    @staticmethod
    def get_recent_activity(org_id: int, limit: int = 6) -> list[dict[str, Any]]:
        """Return recent organization activity."""
        with get_connection() as connection:
            rows = connection.execute(
                select(activity_events)
                .where(activity_events.c.organization_id == org_id)
                .order_by(desc(activity_events.c.created_at))
                .limit(limit)
            ).fetchall()
        return [_row_to_dict(row) for row in rows]


class DashboardService:
    """Service for dashboard snapshots."""

    @staticmethod
    def get_dashboard_snapshot(org_id: int) -> dict[str, Any]:
        """Build overview metrics for a SaaS dashboard."""
        with get_connection() as connection:
            total_carbon = connection.execute(
                select(func.coalesce(func.sum(carbon_results.c.carbon_kg_co2), 0.0)).where(
                    carbon_results.c.organization_id == org_id
                )
            ).scalar_one()
            project_count = connection.execute(
                select(func.count()).select_from(projects).where(projects.c.organization_id == org_id)
            ).scalar_one()
            report_count = connection.execute(
                select(func.count()).select_from(saved_reports).where(saved_reports.c.organization_id == org_id)
            ).scalar_one()
            recommendation_count = connection.execute(
                select(func.count()).select_from(recommendations).where(
                    recommendations.c.organization_id == org_id,
                    recommendations.c.is_implemented.is_(False),
                )
            ).scalar_one()
            latest_activity = connection.execute(
                select(activity_events.c.created_at)
                .where(activity_events.c.organization_id == org_id)
                .order_by(desc(activity_events.c.created_at))
                .limit(1)
            ).scalar()

        return {
            "total_carbon": float(total_carbon or 0.0),
            "project_count": int(project_count or 0),
            "report_count": int(report_count or 0),
            "open_recommendations": int(recommendation_count or 0),
            "latest_activity_at": latest_activity,
        }

    @staticmethod
    def get_workspace_snapshot(org_id: int) -> dict[str, Any]:
        """Build enterprise workspace metrics and collections for the UI shell."""
        projects_for_org = ProjectService.get_org_projects(org_id)
        accounts_for_org = CloudAccountService.get_org_cloud_accounts(org_id)
        members_for_org = MembershipService.get_org_members(org_id)
        recent_reports = SavedReportService.get_org_reports(org_id, limit=6)
        recent_activity = ActivityService.get_recent_activity(org_id, limit=8)
        recs = RecommendationService.get_org_recommendations(org_id, implemented=False)
        connectors = ConnectorService.get_org_connectors(org_id)
        recent_runs = IngestionRunService.get_org_runs(org_id, limit=6)
        recent_alerts = AlertService.get_org_alerts(org_id, limit=8)
        recent_actions = ActionItemService.get_org_action_items(org_id, limit=8)
        recent_audit_logs = AuditLogService.get_org_logs(org_id, limit=8)
        recent_models = ForecastModelService.get_org_models(org_id, limit=6)

        with get_connection() as connection:
            carbon_rows = connection.execute(
                select(
                    carbon_results.c.project_id,
                    carbon_results.c.region,
                    func.coalesce(func.sum(carbon_results.c.carbon_kg_co2), 0.0).label("carbon_total"),
                    func.coalesce(func.sum(carbon_results.c.energy_kwh), 0.0).label("energy_total"),
                    func.count().label("record_count"),
                )
                .where(carbon_results.c.organization_id == org_id)
                .group_by(carbon_results.c.project_id, carbon_results.c.region)
            ).fetchall()

            latest_timestamp = connection.execute(
                select(func.max(carbon_results.c.timestamp)).where(carbon_results.c.organization_id == org_id)
            ).scalar()

        project_index = {project["id"]: project for project in projects_for_org}
        project_rollups: dict[int, dict[str, Any]] = {}
        region_rollups: dict[str, float] = {}
        for row in carbon_rows:
            mapped = _row_to_dict(row)
            project_id = mapped.get("project_id")
            region_name = mapped.get("region") or "unassigned"
            region_rollups[region_name] = region_rollups.get(region_name, 0.0) + float(mapped["carbon_total"] or 0.0)

            if project_id is None:
                continue
            project = project_index.get(project_id)
            if not project:
                continue
            rollup = project_rollups.setdefault(
                project_id,
                {
                    "project_id": project_id,
                    "name": project["name"],
                    "cloud_provider": project["cloud_provider"],
                    "region": project["region"],
                    "status": project["status"],
                    "monthly_budget": float(project["monthly_budget"] or 0.0),
                    "carbon_kg": 0.0,
                    "energy_kwh": 0.0,
                    "records": 0,
                },
            )
            rollup["carbon_kg"] += float(mapped["carbon_total"] or 0.0)
            rollup["energy_kwh"] += float(mapped["energy_total"] or 0.0)
            rollup["records"] += int(mapped["record_count"] or 0)

        portfolio = list(project_rollups.values())
        portfolio.sort(key=lambda item: item["carbon_kg"], reverse=True)

        total_budget = sum(float(project["monthly_budget"] or 0.0) for project in projects_for_org)
        total_carbon = sum(item["carbon_kg"] for item in portfolio)
        provider_mix: dict[str, int] = {}
        for project in projects_for_org:
            provider = project["cloud_provider"]
            provider_mix[provider] = provider_mix.get(provider, 0) + 1

        risk_count = sum(1 for item in portfolio if item["carbon_kg"] > 250)
        coverage_score = min(
            100,
            (25 if projects_for_org else 0)
            + (25 if accounts_for_org else 0)
            + (25 if members_for_org else 0)
            + (25 if recent_reports else 0),
        )

        spend_proxy = total_budget * 0.78 if total_budget else 0.0
        cost_at_risk = sum(abs(float(rec.cost_impact or 0.0)) for rec in recs if float(rec.cost_impact or 0.0) < 0)

        return {
            "headline": {
                "total_carbon": total_carbon,
                "monthly_budget": total_budget,
                "estimated_monthly_spend": spend_proxy,
                "active_projects": len(projects_for_org),
                "cloud_accounts": len(accounts_for_org),
                "connectors": len(connectors),
                "team_members": len(members_for_org),
                "reports": len(recent_reports),
                "open_recommendations": len(recs),
                "open_alerts": len([alert for alert in recent_alerts if alert["status"] == "open"]),
                "open_actions": len([item for item in recent_actions if item["status"] == "open"]),
                "risk_count": risk_count,
                "coverage_score": coverage_score,
                "latest_sync": latest_timestamp,
                "cost_at_risk": cost_at_risk,
            },
            "portfolio": portfolio,
            "regions": region_rollups,
            "provider_mix": provider_mix,
            "members": members_for_org,
            "accounts": [_row_to_dict(account) if hasattr(account, "_mapping") else account.model_dump() for account in accounts_for_org],
            "connectors": connectors,
            "ingestion_runs": recent_runs,
            "alerts": recent_alerts,
            "action_items": recent_actions,
            "audit_logs": recent_audit_logs,
            "forecast_models": recent_models,
            "reports": recent_reports,
            "activity": recent_activity,
            "recommendations": [
                {
                    "id": rec.id,
                    "suggestion": rec.suggestion,
                    "priority": rec.priority,
                    "carbon_saving_percent": float(rec.carbon_saving_percent or 0.0),
                    "cost_impact": float(rec.cost_impact or 0.0),
                }
                for rec in recs
            ],
        }


class APIKeyService:
    """Service for API key operations."""

    @staticmethod
    def create_api_key(user_id: int, name: str) -> tuple[int, str]:
        """Create API key. Returns (key_id, plaintext_key)."""
        plaintext_key = secrets.token_urlsafe(32)
        key_hash = hashlib.sha256(plaintext_key.encode()).hexdigest()
        with get_connection() as connection:
            key_id = connection.execute(
                insert(api_keys).values(user_id=user_id, key=key_hash, name=name)
            ).inserted_primary_key[0]
        return int(key_id), plaintext_key

    @staticmethod
    def verify_api_key(plaintext_key: str) -> int | None:
        """Verify API key and return user ID."""
        key_hash = hashlib.sha256(plaintext_key.encode()).hexdigest()
        with get_connection() as connection:
            row = connection.execute(
                select(api_keys.c.id, api_keys.c.user_id)
                .where(api_keys.c.key == key_hash)
                .where(api_keys.c.is_active.is_(True))
            ).fetchone()
            if not row:
                return None
            connection.execute(
                update(api_keys)
                .where(api_keys.c.id == row._mapping["id"])
                .values(last_used=datetime.utcnow())
            )
        return int(row._mapping["user_id"])
