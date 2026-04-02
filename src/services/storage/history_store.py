from sqlalchemy import select, update

from .db import co_writer_history, get_engine, utc_now


def list_history() -> list[dict]:
    engine = get_engine()
    with engine.begin() as conn:
        rows = conn.execute(
            select(co_writer_history.c.payload).order_by(co_writer_history.c.created_at.desc())
        ).all()
    return [row[0] for row in rows]


def get_history_item(item_id: str) -> dict | None:
    engine = get_engine()
    with engine.begin() as conn:
        row = conn.execute(
            select(co_writer_history.c.payload).where(co_writer_history.c.id == item_id)
        ).first()
    return row[0] if row else None


def upsert_history_item(payload: dict) -> None:
    item_id = payload.get("id")
    if not item_id:
        raise ValueError("history item id is required")
    engine = get_engine()
    if engine.dialect.name == "sqlite":
        from sqlalchemy.dialects.sqlite import insert as dialect_insert
    else:
        from sqlalchemy.dialects.postgresql import insert as dialect_insert

    stmt = dialect_insert(co_writer_history).values(
        id=item_id,
        created_at=utc_now(),
        payload=payload,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=[co_writer_history.c.id],
        set_={"payload": payload},
    )
    with engine.begin() as conn:
        conn.execute(stmt)


def update_history_item(item_id: str, payload: dict) -> None:
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            update(co_writer_history)
            .where(co_writer_history.c.id == item_id)
            .values(payload=payload)
        )
