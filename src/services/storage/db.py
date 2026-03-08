from datetime import datetime, timezone
import os

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    create_engine,
)

_engine = None
_metadata = MetaData()

co_writer_history = Table(
    "co_writer_history",
    _metadata,
    Column("id", String, primary_key=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("payload", JSON, nullable=False),
)

generated_files = Table(
    "generated_files",
    _metadata,
    Column("id", String, primary_key=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("file_type", String, nullable=False),
    Column("filename", String, nullable=False),
    Column("bucket", String, nullable=False),
    Column("object_key", String, nullable=False),
    Column("content_type", String, nullable=False),
    Column("metadata", JSON, nullable=True),
)

ppt_projects = Table(
    "ppt_projects",
    _metadata,
    Column("id", String, primary_key=True),
    Column("notebook_id", String, nullable=True),
    Column("session_id", String, nullable=True),
    Column("creation_type", String, nullable=False),
    Column("idea_prompt", Text, nullable=True),
    Column("outline_text", Text, nullable=True),
    Column("description_text", Text, nullable=True),
    Column("source_content", Text, nullable=True),
    Column("template_style", Text, nullable=True),
    Column("template_image_path", String, nullable=True),
    Column("reference_style_prompt", Text, nullable=True),
    Column("image_aspect_ratio", String, nullable=False),
    Column("language", String, nullable=False),
    Column("reference_sources", JSON, nullable=True),
    Column("status", String, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

ppt_pages = Table(
    "ppt_pages",
    _metadata,
    Column("id", String, primary_key=True),
    Column("project_id", String, ForeignKey("ppt_projects.id"), nullable=False, index=True),
    Column("order_index", Integer, nullable=False, index=True),
    Column("part", String, nullable=True),
    Column("outline_content", JSON, nullable=False),
    Column("description_content", JSON, nullable=True),
    Column("image_prompt", Text, nullable=True),
    Column("generated_image_path", String, nullable=True),
    Column("cached_image_path", String, nullable=True),
    Column("status", String, nullable=False, index=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

ppt_page_image_versions = Table(
    "ppt_page_image_versions",
    _metadata,
    Column("id", String, primary_key=True),
    Column("page_id", String, ForeignKey("ppt_pages.id"), nullable=False, index=True),
    Column("version_number", Integer, nullable=False),
    Column("image_path", String, nullable=False),
    Column("cached_image_path", String, nullable=True),
    Column("prompt_used", Text, nullable=True),
    Column("is_current", Boolean, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

ppt_tasks = Table(
    "ppt_tasks",
    _metadata,
    Column("id", String, primary_key=True),
    Column("project_id", String, ForeignKey("ppt_projects.id"), nullable=False, index=True),
    Column("task_type", String, nullable=False, index=True),
    Column("status", String, nullable=False, index=True),
    Column("progress", JSON, nullable=True),
    Column("error_message", Text, nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Column("finished_at", DateTime(timezone=True), nullable=True),
)

research_runs = Table(
    "research_runs",
    _metadata,
    Column("id", String, primary_key=True),
    Column("research_id", String, nullable=False, index=True),
    Column("notebook_id", String, nullable=True),
    Column("session_id", String, nullable=True),
    Column("dedupe_key", String, nullable=False, index=True),
    Column("topic", Text, nullable=False),
    Column("kb_name", String, nullable=True),
    Column("plan_mode", String, nullable=False),
    Column("enabled_tools", JSON, nullable=False),
    Column("config_snapshot", JSON, nullable=False),
    Column("status", String, nullable=False, index=True),
    Column("phase", String, nullable=False, index=True),
    Column("progress", JSON, nullable=True),
    Column("checkpoint", JSON, nullable=True),
    Column("report_path", String, nullable=True),
    Column("metadata_path", String, nullable=True),
    Column("error_message", Text, nullable=True),
    Column("last_heartbeat_at", DateTime(timezone=True), nullable=True),
    Column("lease_owner", String, nullable=True, index=True),
    Column("lease_expires_at", DateTime(timezone=True), nullable=True, index=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Column("finished_at", DateTime(timezone=True), nullable=True),
)

research_run_events = Table(
    "research_run_events",
    _metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("run_id", String, ForeignKey("research_runs.id"), nullable=False, index=True),
    Column("event_type", String, nullable=False, index=True),
    Column("stage", String, nullable=True, index=True),
    Column("payload", JSON, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)


def get_database_url() -> str:
    url = os.getenv("DATABASE_URL")
    if url:
        return url
    host = os.getenv("POSTGRES_HOST", "localhost")
    port = os.getenv("POSTGRES_PORT", "5432")
    user = os.getenv("POSTGRES_USER", "deeptutor")
    password = os.getenv("POSTGRES_PASSWORD", "deeptutor")
    dbname = os.getenv("POSTGRES_DB", "deeptutor")
    return f"postgresql+psycopg://{user}:{password}@{host}:{port}/{dbname}"


def get_engine():
    global _engine
    if _engine is None:
        _engine = create_engine(get_database_url(), pool_pre_ping=True)
    return _engine


def init_db():
    engine = get_engine()
    _metadata.create_all(engine)


def utc_now():
    return datetime.now(timezone.utc)
