import json
import re
from dataclasses import astuple, dataclass
from datetime import datetime


@dataclass(frozen=True)
class State:
    street: str
    status: str
    revision: int


@dataclass(frozen=True)
class Entry:
    tree: int
    street: str
    status: str
    revision: int

    def text(self):
        return f"{self.street}｜{self.status}｜v{self.revision}"

    def state(self):
        return State(self.street, self.status, self.revision)

    def canonical(self):
        return json.dumps(
            [self.tree, self.street, self.status, self.revision],
            ensure_ascii=False, separators=(",", ":"),
        ).encode()


@dataclass(frozen=True)
class Change:
    seq: int
    tree: int
    at: datetime
    before: State | None
    after: State | None

    def canonical(self):
        return json.dumps(
            [self.seq, self.tree, self.at.isoformat(),
             None if self.before is None else astuple(self.before),
             None if self.after is None else astuple(self.after)],
            ensure_ascii=False, separators=(",", ":"),
        ).encode()


STATUS = {"巡检完成", "待修枝", "待扶正", "待复验"}


def parse_tree(value):
    if type(value) is not int or not 1 <= value <= 10_000_000:
        raise ValueError("树木编号须为 1 至 10000000 的整数")
    return value


def parse_state(row, name):
    if not isinstance(row, dict):
        raise ValueError(f"{name} 须为对象")
    street, status, revision = (row.get(key) for key in ("street", "status", "revision"))
    if not isinstance(street, str) or not re.fullmatch(r"[^\x00-\x1f\ud800-\udfff]{1,32}", street):
        raise ValueError("路段需要 1 至 32 位合法字符")
    if not isinstance(status, str) or status not in STATUS:
        raise ValueError("状态须为巡检完成、待修枝、待扶正或待复验")
    if type(revision) is not int or not 1 <= revision <= 1_000_000:
        raise ValueError("修订号须为 1 至 1000000")
    return State(street, status, revision)


def parse_moment(value, name):
    moment = None
    if isinstance(value, str):
        try:
            moment = datetime.fromisoformat(value)
        except ValueError:
            moment = None
    if moment is None or moment.utcoffset() is None:
        raise ValueError(f"{name} 须为带时区的 ISO 8601 时间")
    return moment


def parse_snapshot(rows, name):
    if not isinstance(rows, list) or len(rows) > 2000:
        raise ValueError(f"{name} 须为最多 2000 条树木养护记录")
    snapshot = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("养护记录必须是对象")
        tree = parse_tree(row.get("tree"))
        if tree in snapshot:
            raise ValueError(f"{name} 有重复树木主键：{tree}")
        state = parse_state(row, "养护记录")
        snapshot[tree] = Entry(tree, state.street, state.status, state.revision)
    return snapshot


def parse_journal(rows):
    if rows is None:
        return []
    if not isinstance(rows, list) or len(rows) > 5000:
        raise ValueError("journal 须为最多 5000 条变更流水")
    journal = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("变更流水必须是对象")
        seq = row.get("seq")
        if type(seq) is not int or not 1 <= seq <= 1_000_000_000:
            raise ValueError("流水号须为 1 至 1000000000 的整数")
        at = parse_moment(row.get("at"), "变更时间 at")
        before, after = row.get("before"), row.get("after")
        if before is None and after is None:
            raise ValueError("变更流水的 before 和 after 不能同时为空")
        journal.append(Change(
            seq=seq, tree=parse_tree(row.get("tree")), at=at,
            before=None if before is None else parse_state(before, "before"),
            after=None if after is None else parse_state(after, "after"),
        ))
    return journal
