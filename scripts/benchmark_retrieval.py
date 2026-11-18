"""Measure retrieval on a reproducible synthetic Chinese Markdown vault."""

from __future__ import annotations

import argparse
import json
import math
import os
import platform
import random
import sqlite3
import statistics
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from kbkit.application import ApplicationService
from kbkit.core import init_vault
from kbkit.vault_profile import index_path


TOPICS = ("请求转发", "告警降级", "数据加载", "测试配置", "备份恢复", "服务扩容", "日志检查", "异常巡检")
SUBJECTS = ("维护员", "开发人员", "值班人员", "复核人员", "平台团队", "文档维护者")
EVIDENCE = ("运行记录", "交接记录", "错误状态", "服务配置", "测试输出", "变更详情", "依赖清单", "系统报告")
ACTION = ("校验", "比对", "确认", "记录", "抽查", "汇总", "核对", "追溯")


def generate(vault: Path, documents: int, sections: int) -> int:
    rng = random.Random(1769)
    size = 0
    for number in range(documents):
        text = []
        for section in range(sections):
            topic = "连接池" if number % 10 == 0 and section == 0 else rng.choice(TOPICS)
            text.append(f"# 第{section + 1}节 {topic} TEST_DOC_{number:05d}_{section:02d}\n")
            for _ in range(6 if sections > 1 else 1):
                text.append(
                    f"{rng.choice(SUBJECTS)}应{rng.choice(ACTION)}{rng.choice(EVIDENCE)}，"
                    f"按照当前规则{rng.choice(ACTION)}{rng.choice(EVIDENCE)}。"
                    "变更确认后检查有关手册，并保留必要的状态和来源用于后续复核。\n"
                )
        raw = "\n".join(text).encode("utf-8")
        (vault / f"note-{number:05d}.md").write_bytes(raw)
        size += len(raw)
    return size


def measure(app: ApplicationService, query: str, expected: int, samples: int) -> dict:
    elapsed: list[float] = []
    for iteration in range(samples + 1):
        start = time.perf_counter()
        hits = app.search(query)["hits"]
        duration = (time.perf_counter() - start) * 1000
        if len(hits) != expected:
            raise ValueError(f"{query}: expected {expected} results, got {len(hits)}")
        if iteration:
            elapsed.append(duration)
    elapsed.sort()
    return {
        "hits": expected,
        "p50_ms": round(statistics.median(elapsed), 1),
        "p95_ms": round(elapsed[math.ceil(0.95 * samples) - 1], 1),
        "p99_ms": round(elapsed[math.ceil(0.99 * samples) - 1], 1),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--documents", type=int, default=10000)
    parser.add_argument("--sections", type=int, default=10)
    parser.add_argument("--samples", type=int, default=20)
    args = parser.parse_args()
    if min(args.documents, args.sections, args.samples) < 1:
        parser.error("all counts must be positive")
    with TemporaryDirectory(prefix="kbkit-search-benchmark-") as directory:
        root = Path(directory)
        vault = root / "vault"
        with patch.dict(os.environ, {"KBKIT_INDEX_DIR": str(root / "index")}):
            init_vault(vault)
            size = generate(vault, args.documents, args.sections)
            app = ApplicationService(vault)
            started = time.perf_counter()
            blocks = app.index()["blocks"]
            build = time.perf_counter() - started
            index_size = index_path(vault).stat().st_size
            queries = {
                "identifier": measure(app, "TEST_DOC_00000_00", 1, args.samples),
                "chinese": measure(app, "连接池", (args.documents + 9) // 10, args.samples),
            }
            with (vault / "note-00000.md").open("ab") as note:
                note.write("\n增量复核文本。".encode("utf-8"))
            started = time.perf_counter()
            changed = app.index()["blocks"]
            incremental = time.perf_counter() - started
            print(json.dumps({
                "platform": platform.platform(), "python": platform.python_version(), "sqlite": sqlite3.sqlite_version,
                "seed": 1769, "documents": args.documents, "sections": args.sections, "samples": args.samples,
                "blocks": blocks, "source_bytes": size, "build_seconds": round(build, 3), "index_bytes": index_size,
                "index_to_source": round(index_size / size, 2), "incremental_seconds": round(incremental, 3),
                "incremental_blocks": changed, "queries": queries,
            }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
