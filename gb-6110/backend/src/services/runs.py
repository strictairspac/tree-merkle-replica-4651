from time import time

from fastapi import HTTPException
from sqlalchemy import insert, select, update

from src.constants.job_state import JobState
from src.domain.scenario import CONFIG
from src.models.cases import cases
from src.models.runs import runs
from . import audit, cases as case_service


def query():
    return select(runs, cases.c.title.label("case_title")).join(cases, cases.c.id == runs.c.case_id)


def get(db, run_id):
    run = db.execute(query().where(runs.c.id == run_id)).mappings().first()
    if run is None:
        raise HTTPException(404, "执行批次不存在")
    return dict(run)


def list_entries(db):
    return [dict(row) for row in db.execute(query().order_by(runs.c.id.desc()).limit(100)).mappings()]


def enqueue(db, case_id, parameter, actor):
    if parameter > CONFIG["max_parameter"]:
        raise HTTPException(422, f"参数不能超过 {CONFIG['max_parameter']}")
    case_service.get(db, case_id)
    change = db.execute(insert(runs).values(
        case_id=case_id, status=JobState.QUEUED, parameter=parameter, actor=actor, created_at=int(time())
    ))
    run_id = change.inserted_primary_key[0]
    audit.record(db, "enqueue", actor, "run", run_id)
    return get(db, run_id)


def resume(db, run_id, actor):
    statement = select(runs).where(runs.c.id == run_id).with_for_update()
    run = db.execute(statement).mappings().first()
    if run is None:
        raise HTTPException(404, "执行批次不存在")
    if run["status"] != JobState.WITHHELD:
        raise HTTPException(409, "仅暂缓出单的批次可以补缺续跑；已出的单不再更改")
    db.execute(update(runs).where(runs.c.id == run_id).values(
        status=JobState.QUEUED, result=None, failure=None, digest=None, finished_at=None,
    ))
    audit.record(db, "resume", actor, "run", run_id)
    return get(db, run_id)
