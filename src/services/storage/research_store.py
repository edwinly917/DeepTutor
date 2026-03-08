from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
import uuid

from sqlalchemy import and_, or_, select, update

from .db import get_engine, research_run_events, research_runs, utc_now

ACTIVE_RUN_STATUSES = ("PENDING", "RUNNING", "CANCEL_REQUESTED")
TERMINAL_RUN_STATUSES = ("COMPLETED", "FAILED", "CANCELLED")


def _new_id() -> str:
    return str(uuid.uuid4())


def _to_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def _run_row_to_dict(row: Any) -> dict[str, Any]:
    return {
        "id": row.id,
        "research_id": row.research_id,
        "notebook_id": row.notebook_id,
        "session_id": row.session_id,
        "dedupe_key": row.dedupe_key,
        "topic": row.topic,
        "kb_name": row.kb_name,
        "plan_mode": row.plan_mode,
        "enabled_tools": row.enabled_tools or [],
        "config_snapshot": row.config_snapshot or {},
        "status": row.status,
        "phase": row.phase,
        "progress": row.progress or {},
        "checkpoint": row.checkpoint or {},
        "report_path": row.report_path,
        "metadata_path": row.metadata_path,
        "error_message": row.error_message,
        "last_heartbeat_at": _to_iso(row.last_heartbeat_at),
        "lease_owner": row.lease_owner,
        "lease_expires_at": _to_iso(row.lease_expires_at),
        "created_at": _to_iso(row.created_at),
        "updated_at": _to_iso(row.updated_at),
        "finished_at": _to_iso(row.finished_at),
    }


def _event_row_to_dict(row: Any) -> dict[str, Any]:
    return {
        "id": row.id,
        "run_id": row.run_id,
        "event_type": row.event_type,
        "stage": row.stage,
        "payload": row.payload or {},
        "created_at": _to_iso(row.created_at),
    }


def create_run(
    *,
    research_id: str,
    notebook_id: str | None,
    session_id: str | None,
    dedupe_key: str,
    topic: str,
    kb_name: str | None,
    plan_mode: str,
    enabled_tools: list[str],
    config_snapshot: dict[str, Any],
    status: str = "PENDING",
    phase: str = "PLANNING",
    progress: dict[str, Any] | None = None,
    checkpoint: dict[str, Any] | None = None,
) -> dict[str, Any]:
    run_id = _new_id()
    now = utc_now()
    stmt = research_runs.insert().values(
        id=run_id,
        research_id=research_id,
        notebook_id=notebook_id,
        session_id=session_id,
        dedupe_key=dedupe_key,
        topic=topic,
        kb_name=kb_name,
        plan_mode=plan_mode,
        enabled_tools=enabled_tools,
        config_snapshot=config_snapshot,
        status=status,
        phase=phase,
        progress=progress or {},
        checkpoint=checkpoint or {},
        report_path=None,
        metadata_path=None,
        error_message=None,
        last_heartbeat_at=None,
        lease_owner=None,
        lease_expires_at=None,
        created_at=now,
        updated_at=now,
        finished_at=None,
    )
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(stmt)
        row = conn.execute(select(research_runs).where(research_runs.c.id == run_id)).first()
    return _run_row_to_dict(row)


def get_run(run_id: str) -> dict[str, Any] | None:
    engine = get_engine()
    with engine.begin() as conn:
        row = conn.execute(select(research_runs).where(research_runs.c.id == run_id)).first()
    return _run_row_to_dict(row) if row else None


def get_run_by_research_id(research_id: str) -> dict[str, Any] | None:
    engine = get_engine()
    with engine.begin() as conn:
        row = conn.execute(
            select(research_runs)
            .where(research_runs.c.research_id == research_id)
            .order_by(research_runs.c.created_at.desc())
        ).first()
    return _run_row_to_dict(row) if row else None


def find_active_run_by_dedupe_key(dedupe_key: str) -> dict[str, Any] | None:
    engine = get_engine()
    with engine.begin() as conn:
        row = conn.execute(
            select(research_runs)
            .where(
                and_(
                    research_runs.c.dedupe_key == dedupe_key,
                    research_runs.c.status.in_(ACTIVE_RUN_STATUSES),
                )
            )
            .order_by(research_runs.c.created_at.desc())
        ).first()
    return _run_row_to_dict(row) if row else None


def update_run(run_id: str, **fields: Any) -> dict[str, Any] | None:
    if not fields:
        return get_run(run_id)
    terminal = fields.get("status") in TERMINAL_RUN_STATUSES
    if terminal and "finished_at" not in fields:
        fields["finished_at"] = utc_now()
    fields["updated_at"] = utc_now()
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(update(research_runs).where(research_runs.c.id == run_id).values(**fields))
        row = conn.execute(select(research_runs).where(research_runs.c.id == run_id)).first()
    return _run_row_to_dict(row) if row else None


def append_event(
    run_id: str, *, event_type: str, stage: str | None, payload: dict[str, Any]
) -> dict[str, Any]:
    now = utc_now()
    stmt = research_run_events.insert().values(
        run_id=run_id,
        event_type=event_type,
        stage=stage,
        payload=payload,
        created_at=now,
    )
    engine = get_engine()
    with engine.begin() as conn:
        result = conn.execute(stmt)
        event_id = result.inserted_primary_key[0]
        row = conn.execute(
            select(research_run_events).where(research_run_events.c.id == event_id)
        ).first()
    return _event_row_to_dict(row)


def list_events(run_id: str, *, after_id: int = 0, limit: int = 500) -> list[dict[str, Any]]:
    engine = get_engine()
    with engine.begin() as conn:
        rows = conn.execute(
            select(research_run_events)
            .where(
                and_(
                    research_run_events.c.run_id == run_id,
                    research_run_events.c.id > after_id,
                )
            )
            .order_by(research_run_events.c.id.asc())
            .limit(limit)
        ).all()
    return [_event_row_to_dict(row) for row in rows]


def claim_next_run(worker_id: str, *, lease_ttl_seconds: int) -> dict[str, Any] | None:
    now = utc_now()
    lease_expiry = now + timedelta(seconds=max(1, lease_ttl_seconds))
    engine = get_engine()
    with engine.begin() as conn:
        row = conn.execute(
            select(research_runs)
            .where(
                or_(
                    research_runs.c.status == "PENDING",
                    and_(
                        research_runs.c.status == "RUNNING",
                        or_(
                            research_runs.c.lease_expires_at.is_(None),
                            research_runs.c.lease_expires_at < now,
                        ),
                    ),
                    and_(
                        research_runs.c.status == "CANCEL_REQUESTED",
                        or_(
                            research_runs.c.lease_expires_at.is_(None),
                            research_runs.c.lease_expires_at < now,
                        ),
                    ),
                )
            )
            .order_by(research_runs.c.created_at.asc())
            .with_for_update(skip_locked=True)
        ).first()
        if not row:
            return None
        conn.execute(
            update(research_runs)
            .where(research_runs.c.id == row.id)
            .values(
                status=row.status if row.status == "CANCEL_REQUESTED" else "RUNNING",
                lease_owner=worker_id,
                last_heartbeat_at=now,
                lease_expires_at=lease_expiry,
                updated_at=now,
            )
        )
        claimed = conn.execute(select(research_runs).where(research_runs.c.id == row.id)).first()
    return _run_row_to_dict(claimed) if claimed else None


def renew_lease(run_id: str, worker_id: str, *, lease_ttl_seconds: int) -> dict[str, Any] | None:
    now = utc_now()
    lease_expiry = now + timedelta(seconds=max(1, lease_ttl_seconds))
    engine = get_engine()
    with engine.begin() as conn:
        row = conn.execute(select(research_runs).where(research_runs.c.id == run_id)).first()
        if not row or row.lease_owner != worker_id:
            return None
        conn.execute(
            update(research_runs)
            .where(research_runs.c.id == run_id)
            .values(
                last_heartbeat_at=now,
                lease_expires_at=lease_expiry,
                updated_at=now,
            )
        )
        renewed = conn.execute(select(research_runs).where(research_runs.c.id == run_id)).first()
    return _run_row_to_dict(renewed) if renewed else None


def release_lease(run_id: str, worker_id: str) -> dict[str, Any] | None:
    engine = get_engine()
    with engine.begin() as conn:
        row = conn.execute(select(research_runs).where(research_runs.c.id == run_id)).first()
        if not row or row.lease_owner != worker_id:
            return _run_row_to_dict(row) if row else None
        conn.execute(
            update(research_runs)
            .where(research_runs.c.id == run_id)
            .values(lease_owner=None, lease_expires_at=None, updated_at=utc_now())
        )
        released = conn.execute(select(research_runs).where(research_runs.c.id == run_id)).first()
    return _run_row_to_dict(released) if released else None


def cancel_run(run_id: str) -> dict[str, Any] | None:
    run = get_run(run_id)
    if not run:
        return None
    if run["status"] in TERMINAL_RUN_STATUSES:
        return run
    return update_run(run_id, status="CANCEL_REQUESTED")


def list_terminal_stale_runs(*, older_than_seconds: int) -> list[dict[str, Any]]:
    if older_than_seconds <= 0:
        return []
    threshold = utc_now() - timedelta(seconds=older_than_seconds)
    engine = get_engine()
    with engine.begin() as conn:
        rows = conn.execute(
            select(research_runs)
            .where(
                and_(
                    research_runs.c.status == "RUNNING",
                    research_runs.c.updated_at < threshold,
                )
            )
            .order_by(research_runs.c.updated_at.asc())
        ).all()
    return [_run_row_to_dict(row) for row in rows]
