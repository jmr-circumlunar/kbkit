"""Evaluate block retrieval on a known-answer set and report Hit@5 and MRR."""

from __future__ import annotations

import argparse
import json
import os
import statistics
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from kbkit.application import ApplicationService
from kbkit.core import init_vault


TOPICS = {
    "service/deploy.md": ("生产部署", "灰度发布", "配置回滚", "健康探针", "RollbackCoordinator"),
    "service/network.md": ("入口路由", "服务发现", "网络隔离", "负载均衡", "RouteRegistry"),
    "data/database.md": ("数据库连接池", "事务隔离", "数据模型", "索引维护", "DB_POOL_TIMEOUT"),
    "data/import.md": ("批量导入", "读取游标", "重复记录", "审计字段", "ImportBatchReader"),
    "operations/report.md": ("周报统计", "导出明细", "异常巡检", "审核记录", "WeeklyReportExcelExporter"),
    "operations/backup.md": ("异地备份", "恢复演练", "快照保留", "备份校验", "BackupSnapshotReader"),
}


def synthetic(root: Path) -> tuple[list[dict], list[dict]]:
    profile = init_vault(root)
    with profile.open("a", encoding="utf-8") as stream:
        stream.write('\n[search.exclude]\nprefixes = ["scratch"]\nallow = ["scratch/shared"]\n')
    cases = []
    for path, (topic, first, second, third, symbol) in TOPICS.items():
        target = root / path
        target.parent.mkdir(exist_ok=True)
        target.write_text(
            f"---\nkind: guide\nstate: active\ntags: [current, {target.parent.name}]\n---\n"
            f"# {topic}\n{topic}流程说明。{first}和{second}见操作步骤。\n"
            f"## {first}\n遇到问题时执行{second}。命令入口是 {symbol}。\n"
            f"## {third}\n检查{third}并保存记录。\n", encoding="utf-8",
        )
        for query in (topic, first, second, third):
            cases.append({"arguments": {"query": query}, "expected_path": path})
        cases.append({"arguments": {"symbols": [symbol]}, "expected_path": path})

    decoys = {
        "scratch/notes.md": "# 数据模型\nWeeklyReportExcelExporter\n",
        "scratch/shared/guide.md": "# 数据模型\n本节描述许可测试。\n",
        "service/notes.md": "---\nkind: notes\nstate: archived\ntags: [old]\n---\n# 数据模型\nweeklyreportexcelexporter\n",
        "operations/notes.md": "# 恢复演练安排与生产部署参考\n",
        "data/parts.md": "# 数据库。连接池。\n",
    }
    for path, content in decoys.items():
        target = root / path
        target.parent.mkdir(exist_ok=True, parents=True)
        target.write_text(content, encoding="utf-8")
    cases.extend([
        {"arguments": {"query": "数据模型", "kind": "guide", "tags": ["data", "current"]}, "expected_path": "data/database.md"},
        {"arguments": {"query": "数据模型", "path": ["scratch"]}, "expected_path": "scratch/shared/guide.md"},
        {"arguments": {"query": "数据模型", "state": "archived"}, "expected_path": "service/notes.md"},
        {"arguments": {"query": "据库"}, "expected_path": "data/database.md"},
    ])
    negatives = [{"query": "数据库连接池", "path": "data/parts.md"}, {"symbols": ["WEEKLYREPORTEXCELEXPORTER"]},
                 {"query": "数据模型", "path": "scratch/notes.md"}, {"query": "数据模型", "path": "service/notes.md"}]
    return cases, negatives


def evaluate(app: ApplicationService, cases: list[dict], negatives: list[dict]) -> dict:
    if not cases:
        raise ValueError("at least one ranked query is required")
    ranks = []
    for case in cases:
        arguments = case["arguments"] if "arguments" in case else {"query": case["query"]}
        arguments = {**arguments, "limit": 50, "select": "path"}
        paths = list(dict.fromkeys(hit["path"] for hit in app.search(**arguments)["hits"]))
        expected = case["expected_path"]
        ranks.append(paths.index(expected) + 1 if expected in paths else None)
    leakage = sum(app.search(**arguments, limit=1, select="path")["total_candidates"] > 0 for arguments in negatives)
    return {"queries": len(cases), "hit_at_5": statistics.mean(rank is not None and rank <= 5 for rank in ranks),
            "mrr_at_50": statistics.mean(1 / rank if rank else 0 for rank in ranks),
            "negative_cases": len(negatives), "negative_failures": leakage, "ranks": ranks}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vault", type=Path, help="An initialized evaluation copy, supplied with --queries.")
    parser.add_argument("--queries", type=Path, help="JSON rows with query or arguments and expected_path.")
    parser.add_argument("--min-hit-at-5", type=float, default=0.97)
    parser.add_argument("--min-mrr", type=float, default=0.85)
    args = parser.parse_args()
    if bool(args.vault) != bool(args.queries):
        parser.error("--vault and --queries must be supplied together")
    if args.vault:
        config = json.loads(args.queries.read_bytes())
        cases = config["queries"] if isinstance(config, dict) else config
        negatives = config.get("negatives", []) if isinstance(config, dict) else []
        result = evaluate(ApplicationService(args.vault), cases, negatives)
    else:
        with TemporaryDirectory() as folder:
            root = Path(folder)
            with patch.dict(os.environ, {"KBKIT_HOME": "", "KBKIT_INDEX_DIR": str(root / "indexes")}):
                vault = root / "vault"
                cases, negatives = synthetic(vault)
                result = evaluate(ApplicationService(vault), cases, negatives)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return int(result["hit_at_5"] < args.min_hit_at_5 or result["mrr_at_50"] < args.min_mrr or result["negative_failures"] > 0)


if __name__ == "__main__":
    raise SystemExit(main())
