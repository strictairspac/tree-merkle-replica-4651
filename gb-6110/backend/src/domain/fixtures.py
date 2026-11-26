from itertools import cycle


def _reference():
    streets = cycle(["槐河路", "栖霞巷", "东砖街"])
    return [
        {"tree": tree, "street": next(streets), "status": "巡检完成", "revision": 2}
        for tree in range(1233, 1281)
    ]


def _replica(reference):
    replica = [{**row} for row in reference if row["tree"] != 1259]
    next(row for row in replica if row["tree"] == 1234).update(status="待扶正", revision=1)
    next(row for row in replica if row["tree"] == 1260).update(status="待复验")
    replica.append({"tree": 1281, "street": "东砖街", "status": "待修枝", "revision": 1})
    return list(reversed(replica))


def _handover():
    """交班对账：主账 09:10、终端 08:30 各留快照，凭变更流水把主账回退到 08:30。"""
    replica = [{**row} for row in _reference() if row["tree"] != 1259]
    next(row for row in replica if row["tree"] == 1234).update(status="待扶正")
    next(row for row in replica if row["tree"] == 1235).update(status="待修枝")
    next(row for row in replica if row["tree"] == 1260).update(status="待复验")
    next(row for row in replica if row["tree"] == 1262).update(status="待修枝", revision=4)
    replica.append({"tree": 1281, "street": "东砖街", "status": "待修枝", "revision": 1})
    reference = [{**row} for row in _reference()]
    next(row for row in reference if row["tree"] == 1235).update(status="巡检完成", revision=3)
    next(row for row in reference if row["tree"] == 1262).update(status="待扶正", revision=1)
    # 流水乱序送达：1235 修枝完成；1262 迁走后补栽，修订号从 1 重计；1260 复验通过。
    journal = [
        {"seq": 43, "tree": 1235, "at": "2026-11-26T08:55+08:00",
         "before": {"street": "东砖街", "status": "待修枝", "revision": 2},
         "after": {"street": "东砖街", "status": "巡检完成", "revision": 3}},
        {"seq": 41, "tree": 1260, "at": "2026-11-26T08:47+08:00",
         "before": {"street": "槐河路", "status": "待复验", "revision": 2},
         "after": {"street": "槐河路", "status": "巡检完成", "revision": 2}},
        {"seq": 44, "tree": 1262, "at": "2026-11-26T09:02+08:00",
         "before": None,
         "after": {"street": "东砖街", "status": "待扶正", "revision": 1}},
        {"seq": 42, "tree": 1262, "at": "2026-11-26T08:50+08:00",
         "before": {"street": "东砖街", "status": "待修枝", "revision": 4},
         "after": None},
    ]
    return reference, replica, journal


def _handover_case(reference, replica, journal):
    return {
        "epoch": "2026-11-26T09:10+08:00",
        "replica_epoch": "2026-11-26T08:30+08:00",
        "reference": reference,
        "replica": replica,
        "journal": journal,
    }


REFERENCE = _reference()
_HANDOVER = _handover()
FIXTURES = [
    {
        "code": "ST-XH-1126",
        "title": "西河片区交班对账",
        "description": "主账 09:10、终端 08:30 各留快照，凭乱序送达的变更流水把主账回退到 08:30；1262 号迁走后补栽，修订号从 1 重计。",
        "payload": _handover_case(*_HANDOVER),
    },
    {
        "code": "ST-XH-1126B",
        "title": "西河片区流水缺号",
        "description": "同一交班批，流水 43 号未送达，运行标出缺口并暂缓出单；补录缺失流水后原批次继续对账。",
        "payload": _handover_case(_HANDOVER[0], _HANDOVER[1],
                                  [row for row in _HANDOVER[2] if row["seq"] != 43]),
    },
    {
        "code": "ST-XH-1126C",
        "title": "西河片区前后值对不上",
        "description": "补栽记录的变更前值与迁走记录的变更后值衔接不上，运行标出缺口并暂缓出单。",
        "payload": _handover_case(_HANDOVER[0], _HANDOVER[1], [
            {**row, "before": {"street": "东砖街", "status": "待修枝", "revision": 4}}
            if row["seq"] == 44 else row
            for row in _HANDOVER[2]
        ]),
    },
    {
        "code": "ST-XH-1124",
        "title": "西河片区晨班副本点验",
        "description": "核对 48 株现场巡检副本，定位旧版、缺株、孤立行与同版冲突。",
        "payload": {
            "epoch": "2026-11-24T08:40+08:00",
            "replica_epoch": "2026-11-24T08:40+08:00",
            "reference": REFERENCE,
            "replica": _replica(REFERENCE),
        },
    },
    {
        "code": "ST-DC-1124",
        "title": "东城调序后保持一致",
        "description": "终端将同一快照按逆序导出，两边的 Merkle 根仍然一致。",
        "payload": {
            "epoch": "2026-11-24T09:15+08:00",
            "replica_epoch": "2026-11-24T09:15+08:00",
            "reference": REFERENCE[:6],
            "replica": list(reversed(REFERENCE[:6])),
        },
    },
]
