from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import insert, select, update

from src.domain import scenario
from src.models.cases import cases
from .audit import record


def get(db, case_id):
    entry = db.execute(select(cases).where(cases.c.id == case_id)).mappings().first()
    if entry is None:
        raise HTTPException(404, "资料不存在")
    return dict(entry)


def list_entries(db):
    return [dict(row) for row in db.execute(select(cases).order_by(cases.c.id.desc()).limit(100)).mappings()]


def create(db, data, actor):
    validator = getattr(scenario, "validate", None)
    if validator is not None:
        try:
            validator(data.payload)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
    change = db.execute(insert(cases).values(**data.model_dump(), code=f"CASE-{uuid4().hex[:12].upper()}", created_by=actor))
    case_id = change.inserted_primary_key[0]
    record(db, "create_case", actor, "case", case_id)
    return get(db, case_id)


def append_journal(db, case_id, records, actor):
    """只追加不改写：已收到的流水保持原样，后到的记录不影响已出的单。"""
    statement = select(cases).where(cases.c.id == case_id).with_for_update()
    entry = db.execute(statement).mappings().first()
    if entry is None:
        raise HTTPException(404, "资料不存在")
    try:
        changes = scenario.parse_journal(records)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    incoming = [change.seq for change in changes]
    if len(set(incoming)) != len(incoming):
        raise HTTPException(422, "补录记录内流水号重复")
    payload = dict(entry["payload"])
    journal = list(payload.get("journal") or [])
    existing = {row.get("seq") for row in journal if isinstance(row, dict)}
    duplicates = sorted(seq for seq in incoming if seq in existing)
    if duplicates:
        raise HTTPException(409, f"流水号已存在，不可改写：{duplicates}")
    if len(journal) + len(records) > 5000:
        raise HTTPException(422, "变更流水最多 5000 条")
    journal.extend(records)
    payload["journal"] = journal
    db.execute(update(cases).where(cases.c.id == case_id).values(payload=payload))
    record(db, "append_journal", actor, "case", case_id)
    return get(db, case_id)
