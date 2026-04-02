from datetime import datetime, timezone
import os
from pathlib import Path

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
    Column("style_preset_id", String, nullable=True),
    Column("style_custom_text", Text, nullable=True),
    Column("template_image_path", String, nullable=True),
    Column("template_file_refs", JSON, nullable=True),
    Column("reference_style_prompt", Text, nullable=True),
    Column("reference_layout_prompt", Text, nullable=True),
    Column("reference_content_prompt", Text, nullable=True),
    Column("image_aspect_ratio", String, nullable=False),
    Column("language", String, nullable=False),
    Column("reference_sources", JSON, nullable=True),
    Column("source_refs", JSON, nullable=True),
    Column("record_ids", JSON, nullable=True),
    Column("normalized_content", Text, nullable=True),
    Column("content_cached_at", DateTime(timezone=True), nullable=True),
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
    Column("is_dirty", Boolean, nullable=False, server_default="false"),
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

ppt_slide_chat_messages = Table(
    "ppt_slide_chat_messages",
    _metadata,
    Column("id", String, primary_key=True),
    Column("page_id", String, ForeignKey("ppt_pages.id"), nullable=False, index=True),
    Column("role", String, nullable=False),
    Column("content", Text, nullable=False),
    Column("edit_type", String, nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False, index=True),
)


def get_database_url() -> str:
    url = os.getenv("DATABASE_URL")
    if url:
        return url
    # For local development without explicit database configuration, use a
    # file-based SQLite database so PPT/storage features work without Postgres.
    project_root = Path(__file__).resolve().parents[3]
    sqlite_dir = project_root / "data" / "user" / "storage"
    sqlite_dir.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{sqlite_dir / 'deeptutor.db'}"


def get_engine():
    global _engine
    if _engine is None:
        database_url = get_database_url()
        engine_kwargs = {}
        if database_url.startswith("sqlite"):
            engine_kwargs["connect_args"] = {"check_same_thread": False}
        else:
            engine_kwargs["pool_pre_ping"] = True
        _engine = create_engine(database_url, **engine_kwargs)
    return _engine


def init_db():
    engine = get_engine()
    _metadata.create_all(engine)
    if engine.dialect.name != "sqlite":
        _ensure_additive_schema(engine)


def _ensure_additive_schema(engine) -> None:
    with engine.begin() as conn:
        conn.exec_driver_sql(
            """
            ALTER TABLE ppt_projects
            ADD COLUMN IF NOT EXISTS style_preset_id VARCHAR
            """
        )
        conn.exec_driver_sql(
            """
            ALTER TABLE ppt_projects
            ADD COLUMN IF NOT EXISTS style_custom_text TEXT
            """
        )
        conn.exec_driver_sql(
            """
            ALTER TABLE ppt_projects
            ADD COLUMN IF NOT EXISTS template_file_refs JSON
            """
        )
        conn.exec_driver_sql(
            """
            ALTER TABLE ppt_projects
            ADD COLUMN IF NOT EXISTS reference_layout_prompt TEXT
            """
        )
        conn.exec_driver_sql(
            """
            ALTER TABLE ppt_projects
            ADD COLUMN IF NOT EXISTS reference_content_prompt TEXT
            """
        )
        conn.exec_driver_sql(
            """
            ALTER TABLE ppt_projects
            ADD COLUMN IF NOT EXISTS source_refs JSON
            """
        )
        conn.exec_driver_sql(
            """
            ALTER TABLE ppt_projects
            ADD COLUMN IF NOT EXISTS normalized_content TEXT
            """
        )
        conn.exec_driver_sql(
            """
            ALTER TABLE ppt_projects
            ADD COLUMN IF NOT EXISTS record_ids JSON
            """
        )
        conn.exec_driver_sql(
            """
            ALTER TABLE ppt_projects
            ADD COLUMN IF NOT EXISTS content_cached_at TIMESTAMPTZ
            """
        )
        conn.exec_driver_sql(
            """
            ALTER TABLE ppt_pages
            ADD COLUMN IF NOT EXISTS is_dirty BOOLEAN DEFAULT FALSE
            """
        )
        conn.exec_driver_sql(
            """
            CREATE TABLE IF NOT EXISTS ppt_slide_chat_messages (
                id VARCHAR PRIMARY KEY,
                page_id VARCHAR NOT NULL REFERENCES ppt_pages(id),
                role VARCHAR NOT NULL,
                content TEXT NOT NULL,
                edit_type VARCHAR NULL,
                created_at TIMESTAMPTZ NOT NULL
            )
            """
        )
        conn.exec_driver_sql(
            """
            CREATE INDEX IF NOT EXISTS idx_ppt_slide_chat_messages_page
            ON ppt_slide_chat_messages(page_id)
            """
        )
        conn.exec_driver_sql(
            """
            CREATE INDEX IF NOT EXISTS idx_ppt_slide_chat_messages_page_created_at
            ON ppt_slide_chat_messages(page_id, created_at)
            """
        )


def utc_now():
    return datetime.now(timezone.utc)
