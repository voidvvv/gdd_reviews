"""CLI 入口: gdd-review <review|distill|lint|wiki> [args]."""

from __future__ import annotations

import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def main() -> None:
    if len(sys.argv) < 2:
        _usage()
        raise SystemExit(1)

    cmd = sys.argv[1]

    if cmd == "review":
        if len(sys.argv) < 3:
            print("用法: gdd-review review <gdd文档路径>")
            raise SystemExit(1)
        from gdd_review.review import run_review

        report = run_review(sys.argv[2])
        print(f"\n✓ 评审完成,报告: {report}")

    elif cmd == "distill":
        from gdd_review.distill import run_distill

        run_distill()

    elif cmd == "lint":
        from gdd_review import wiki

        issues = wiki.lint()
        if not issues:
            print("✓ wiki 健康,无问题")
        else:
            print(f"发现 {len(issues)} 个问题:")
            for i in issues:
                print(f"  - {i}")

    elif cmd == "wiki":
        # 调试命令: 查看知识库状态与检索效果(不调LLM)
        from gdd_review import wiki

        pages = wiki.load_pages()
        print(f"wiki页面: {len(pages)}")
        for p in pages:
            print(f"  - {p.name} (tags={p.tags})")
        if len(sys.argv) >= 3:
            q = " ".join(sys.argv[2:])
            print(f"\n检索'{q}':")
            for h in wiki.search(q):
                print(f"  → {h['name']}: {h['snippet'][:80]}")
        for dim in ("defect", "highlight"):
            print(f"门控[{dim}]:", wiki.knowledge_sufficiency(dim)["reason"])

    else:
        _usage()
        raise SystemExit(1)


def _usage() -> None:
    print(
        "GDD 评审框架\n\n"
        "用法:\n"
        "  gdd-review review <gdd路径>   评审一份GDD,输出报告到 reports/\n"
        "  gdd-review distill            蒸馏 raw_gdds/ 下全部GDD进知识库\n"
        "  gdd-review lint               知识库健康检查\n"
        "  gdd-review wiki [关键词]       查看知识库/试检索(不调LLM)\n"
    )


if __name__ == "__main__":
    main()
