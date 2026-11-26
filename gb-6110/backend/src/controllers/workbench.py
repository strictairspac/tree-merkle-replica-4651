from redis.exceptions import RedisError
from src.config.resources import cache, engine
from src.services import cases, runs, reviews


def new_case(data, user):
    with engine.begin() as db:
        return cases.create(db, data, user["username"])


def new_run(case_id, data, user):
    with engine.begin() as db:
        run = runs.enqueue(db, case_id, data.parameter, user["username"])
    wake(run)
    return run


def wake(run):
    try:
        cache.lpush("workbench:wake", str(run["id"]))
        cache.ltrim("workbench:wake", 0, 99)
    except RedisError:
        # The database holds the durable queue. The worker also polls it.
        pass


def append_journal(case_id, data, user):
    with engine.begin() as db:
        return cases.append_journal(db, case_id, data.records, user["username"])


def resume_run(run_id, user):
    with engine.begin() as db:
        run = runs.resume(db, run_id, user["username"])
    wake(run)
    return run


def new_review(run_id, data, user):
    with engine.begin() as db:
        return reviews.sign(db, run_id, data, user["username"])
