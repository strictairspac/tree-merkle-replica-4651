from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime

from src.utils.serial import content_digest

from .fixtures import FIXTURES
from .merkle import EMPTY, KeyTree, compare
from .snapshot import Entry, parse_journal, parse_moment, parse_snapshot


CONFIG = {
    "title": "青徊园护·行道树副本点验",
    "team": "青徊园护 12 人行道树巡养与离线数据组",
    "description": "主账与巡养终端各自留快照，交班时凭变更流水把较晚一侧回退到较早的截止时点，再分段点验。",
    "direction": "副本反熵与 Merkle 区间比对",
    "mechanism": "共享主键边界的稀疏 Merkle 树，按区间展开缺行、孤立行和不同版本；流水缺号或前后值对不上时暂缓出单。",
    "modules": ["巡护交班", "双侧养护快照", "分段点验", "补录核查单"],
    "unit": "副本点验批",
    "max_parameter": 65536,
    "parameter_label": "每个叶区间包含的树号数（1–65536）",
    "default_parameter": 16,
    "facts": ["差异区间", "差异树木", "比较摘要"],
    "palette": 10,
    "fixture": "ST-XH-1126 / 西河片区交班",
}


@dataclass
class Reconciliation:
    epoch: datetime
    replica_epoch: datetime
    reference: dict
    replica: dict
    journal: list

    @property
    def cutoff(self):
        return min(self.epoch, self.replica_epoch)

    @property
    def later(self):
        if self.epoch > self.replica_epoch:
            return "reference", self.epoch, self.reference
        if self.replica_epoch > self.epoch:
            return "replica", self.replica_epoch, self.replica
        return None, self.epoch, None


def normalize(payload):
    if not isinstance(payload, dict):
        raise ValueError("输入需为对象")
    return Reconciliation(
        epoch=parse_moment(payload.get("epoch"), "epoch"),
        replica_epoch=parse_moment(payload.get("replica_epoch"), "replica_epoch"),
        reference=parse_snapshot(payload.get("reference"), "reference"),
        replica=parse_snapshot(payload.get("replica"), "replica"),
        journal=parse_journal(payload.get("journal")),
    )


def validate(payload):
    normalize(payload)


def classify(reference, replica):
    if not reference:
        return "副本多行"
    if not replica:
        return "副本缺行"
    if replica.revision < reference.revision:
        return "副本版本落后"
    if replica.revision > reference.revision:
        return "副本版本超前"
    return "同代内容冲突"


def _seqs_text(seqs):
    shown = "、".join(str(seq) for seq in seqs[:8])
    return shown if len(seqs) <= 8 else f"{shown} 等 {len(seqs)} 个"


def find_gaps(data):
    """核查对账窗口内的变更流水：重号、缺号、前后值对不上。返回 (缺口, 窗口内流水)。"""
    _side, later_epoch, later_snapshot = data.later
    cutoff = data.cutoff
    needed = [change for change in data.journal if cutoff < change.at <= later_epoch]
    if not needed:
        return [], []
    gaps = []
    groups = defaultdict(list)
    for change in data.journal:
        groups[change.seq].append(change)
    duplicates = sorted(seq for seq, items in groups.items() if len(items) > 1)
    if duplicates:
        gaps.append({
            "类型": "流水重号",
            "位置": f"流水号 {_seqs_text(duplicates)}",
            "说明": "同一流水号收到多条记录，以原始流水为准去重后补送。",
        })
    low = min(change.seq for change in needed)
    high = max(change.seq for change in needed)
    missing = [seq for seq in range(low, high + 1) if seq not in groups]
    if missing:
        gaps.append({
            "类型": "流水缺号",
            "位置": f"流水号 {_seqs_text(missing)}",
            "说明": f"对账窗口需要流水 {low}–{high}，缺口补齐前暂缓出单。",
        })
    if not duplicates:
        by_tree = defaultdict(list)
        for change in data.journal:
            if low <= change.seq <= high:
                by_tree[change.tree].append(change)
        for tree in sorted(by_tree):
            chain = sorted(by_tree[tree], key=lambda change: change.seq)
            for previous, current in zip(chain, chain[1:]):
                if previous.after != current.before:
                    gaps.append({
                        "类型": "前后值对不上",
                        "位置": f"树号 {tree} 流水 {previous.seq}→{current.seq}",
                        "说明": "前一条的变更后值与后一条的变更前值不一致。",
                    })
        touched = defaultdict(list)
        for change in needed:
            touched[change.tree].append(change)
        for tree in sorted(touched):
            last = max(touched[tree], key=lambda change: change.seq)
            current = later_snapshot.get(tree)
            if last.after != (current.state() if current else None):
                gaps.append({
                    "类型": "前后值对不上",
                    "位置": f"树号 {tree} 流水 {last.seq}",
                    "说明": "流水末端与较晚一侧快照不一致，可能有变更未送达。",
                })
    return gaps, needed


def rollback(needed, snapshot):
    """按流水号逆序回退；before/after 携带完整记录，修订号重用也能还原当时那条。"""
    state = dict(snapshot)
    for change in sorted(needed, key=lambda item: item.seq, reverse=True):
        if change.before is None:
            state.pop(change.tree, None)
        else:
            before = change.before
            state[change.tree] = Entry(change.tree, before.street, before.status, before.revision)
    return state


def run(payload, parameter, db):
    data = normalize(payload)
    gaps, needed = find_gaps(data)
    if gaps:
        return {
            "summary": f"变更流水存在 {len(gaps)} 处缺口，暂缓出单；补齐缺口后在原批次继续对账。",
            "metrics": {"流水缺口": len(gaps), "窗口内变更": len(needed)},
            "rows": [],
            "gaps": gaps,
            "sheet": None,
        }
    side, _later_epoch, later_snapshot = data.later
    reference, replica = data.reference, data.replica
    if side == "reference":
        reference = rollback(needed, later_snapshot)
    elif side == "replica":
        replica = rollback(needed, later_snapshot)
    largest_key = max(max(reference, default=1), max(replica, default=1))
    leaf_count = 1 << ((largest_key - 1) // parameter).bit_length()
    official = KeyTree(reference, parameter, leaf_count)
    field = KeyTree(replica, parameter, leaf_count)
    comparison = compare(official, field)
    rows = []
    drift = 0
    for index, official_hash, replica_hash in comparison.windows:
        interval = f"{index * parameter + 1}–{(index + 1) * parameter}"
        left = {entry.tree: entry for entry in official.bins.get(index, ())}
        right = {entry.tree: entry for entry in field.bins.get(index, ())}
        for tree in sorted(left.keys() | right.keys()):
            a, b = left.get(tree), right.get(tree)
            if a == b:
                continue
            drift += 1
            rows.append({
                "区间": interval, "树号": tree, "结论": classify(a, b),
                "主侧记录": a.text() if a else None, "副侧记录": b.text() if b else None,
                "主侧摘要": official_hash, "副侧摘要": replica_hash,
            })
    if not rows:
        rows.append({
            "区间": f"1–{leaf_count * parameter}", "树号": None, "结论": "根摘要一致",
            "主侧记录": f"{len(reference)} 条", "副侧记录": f"{len(replica)} 条",
            "主侧摘要": official.levels[-1].get(0, EMPTY).hex(),
            "副侧摘要": field.levels[-1].get(0, EMPTY).hex(),
        })
    ordered = sorted(needed, key=lambda change: change.seq)
    sheet = {
        "比对时点": data.cutoff.isoformat(),
        "主账快照时点": data.epoch.isoformat(),
        "终端快照时点": data.replica_epoch.isoformat(),
        "回退侧": {"reference": "主账", "replica": "终端", None: "无"}[side],
        "流水范围": f"{ordered[0].seq}–{ordered[-1].seq}" if ordered else "未使用",
        "流水条数": len(ordered),
        "流水摘要": content_digest([change.canonical().decode() for change in ordered]) if ordered else None,
    }
    metrics = {
        "差异区间": len(comparison.windows), "差异树木": drift,
        "比较摘要": comparison.checked, "跳过叶区间": comparison.spared_leaves,
        "总叶区间": leaf_count, "回退变更": len(ordered),
    }
    if ordered:
        summary = (f"比对时点 {sheet['比对时点']}，按流水 {sheet['流水范围']} 回退{sheet['回退侧']} "
                   f"{len(ordered)} 条；检查 {comparison.checked} 个节点摘要，"
                   f"{len(comparison.windows)} 个区间有差异。")
    else:
        summary = (f"比对时点 {sheet['比对时点']}，窗口内无变更流水；检查 {comparison.checked} 个节点摘要，"
                   f"{len(comparison.windows)} 个区间有差异。")
    return {"summary": summary, "metrics": metrics, "rows": rows, "gaps": [], "sheet": sheet}
