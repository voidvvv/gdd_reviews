"""Wiki 知识库层 —— Karpathy LLM Wiki 模式(参考 llm_wiki.md).

三层架构:
  raw_gdds/       原始语料(不可变,只读)
  knowledge_wiki/ LLM维护的wiki页面(markdown,本模块管理)
  index/log       双索引: 内容目录 + 时序日志

页面 frontmatter 约定:
  title:  页面标题
  tags:   分类标签 [standard|pitfall|exemplar|synthesis]
  sources: 提炼自哪些原始文档
正文约定:
  条目带稳定编号 [S*]/[D*](标准) [P*](反例) [G*](亮点范式)
  反例四元组: 设计+后果+检查动作
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import yaml

WIKI_DIR = Path(__file__).resolve().parents[2] / "knowledge_wiki"
RAW_DIR = Path(__file__).resolve().parents[2] / "raw_gdds"

PAGE_SUFFIX = ".md"


@dataclass
class WikiPage:
    """一个 wiki 页面: frontmatter 元数据 + 正文."""

    name: str  # 文件名(不含后缀), 同时是引用ID
    title: str = ""
    tags: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    body: str = ""

    @property
    def path(self) -> Path:
        return WIKI_DIR / f"{self.name}{PAGE_SUFFIX}"

    def render(self) -> str:
        front = {
            "title": self.title or self.name,
            "tags": self.tags,
            "sources": self.sources,
            "updated": datetime.now().strftime("%Y-%m-%d"),
        }
        return f"---\n{yaml.safe_dump(front, allow_unicode=True, sort_keys=False)}---\n\n{self.body.strip()}\n"


def load_pages() -> list[WikiPage]:
    """加载全部 wiki 页面(跳过 index/log 这两个特殊文件)."""
    pages: list[WikiPage] = []
    if not WIKI_DIR.exists():
        return pages
    for p in sorted(WIKI_DIR.glob(f"*{PAGE_SUFFIX}")):
        if p.stem in ("index", "log"):
            continue
        raw = p.read_text(encoding="utf-8")
        meta: dict = {}
        body = raw
        if raw.startswith("---"):
            parts = raw.split("---", 2)
            if len(parts) == 3:
                try:
                    meta = yaml.safe_load(parts[1]) or {}
                except yaml.YAMLError:
                    meta = {}
                body = parts[2]
        pages.append(
            WikiPage(
                name=p.stem,
                title=str(meta.get("title", p.stem)),
                tags=[str(t) for t in meta.get("tags", [])],
                sources=[str(s) for s in meta.get("sources", [])],
                body=body.strip(),
            )
        )
    return pages


def save_page(page: WikiPage) -> None:
    """写入页面并刷新 index 与 log."""
    WIKI_DIR.mkdir(parents=True, exist_ok=True)
    page.path.write_text(page.render(), encoding="utf-8")
    rebuild_index()
    append_log(
        f"{'update' if page.name in _existing_names() else 'create'}",
        page.name,
    )


def _existing_names() -> set[str]:
    return {p.stem for p in WIKI_DIR.glob(f"*{PAGE_SUFFIX}")} if WIKI_DIR.exists() else set()


def delete_page(name: str) -> bool:
    path = WIKI_DIR / f"{name}{PAGE_SUFFIX}"
    if path.exists():
        path.unlink()
        rebuild_index()
        append_log("delete", name)
        return True
    return False


# ── 检索 ─────────────────────────────────────────────────────────


def search(
    query: str,
    tag: str | None = None,
    limit: int = 5,
) -> list[dict]:
    """关键词检索: 逐词在页面全文中匹配, 返回命中页面+首个命中行.

    Returns:
        [{"name","title","tags","snippet","score}] 按命中词数降序.
    """
    keywords = [k.lower() for k in re.split(r"\s+", query.strip()) if k]
    if not keywords:
        return []
    hits: list[dict] = []
    for page in load_pages():
        if tag and tag not in page.tags:
            continue
        body_l = page.body.lower()
        matched = [k for k in keywords if k in body_l or k in page.title.lower()]
        if not matched:
            continue
        snippet = ""
        for line in page.body.splitlines():
            if any(k in line.lower() for k in matched) and line.strip():
                snippet = line.strip()
                break
        hits.append(
            {
                "name": page.name,
                "title": page.title,
                "tags": page.tags,
                "snippet": snippet[:200],
                "score": len(matched),
            }
        )
    hits.sort(key=lambda h: h["score"], reverse=True)
    return hits[:limit]


def read_page(name: str) -> str | None:
    path = WIKI_DIR / f"{name}{PAGE_SUFFIX}"
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8")


def knowledge_sufficiency(dimension: str) -> dict:
    """评估某评审维度的知识充分性(缺陷/亮点检查的门控).

    缺陷检查需要 tag=pitfall 的页面, 亮点检查需要 tag=exemplar 的页面。
    阈值: 至少 2 个相关页面且合计不少于 5 条编号条目, 否则视为知识不足。
    """
    tag_map = {
        "defect": ("pitfall", ["[P"]),
        "highlight": ("exemplar", ["[G", "[S", "[D"]),
    }
    if dimension not in tag_map:
        return {"sufficient": True, "pages": 0, "entries": 0, "reason": "该维度不依赖知识库"}
    want_tag, prefixes = tag_map[dimension]
    pages = [p for p in load_pages() if want_tag in p.tags]
    entries = sum(
        sum(p.body.count(prefix) for prefix in prefixes) for p in pages
    )
    sufficient = len(pages) >= 2 and entries >= 5
    reason = (
        f"知识充分: {len(pages)}个{want_tag}页面,{entries}条条目"
        if sufficient
        else f"知识不足: 仅{len(pages)}个{want_tag}页面/{entries}条条目(要求≥2页面且≥5条)"
    )
    return {"sufficient": sufficient, "pages": len(pages), "entries": entries, "reason": reason}


# ── index / log / lint (llm_wiki.md 三操作之 Ingest 记账与 Lint) ──


def rebuild_index() -> None:
    """重建 index.md: 按tag分组的内容目录(llm_wiki.md: 查询先读index)."""
    pages = load_pages()
    sections: dict[str, list[WikiPage]] = {}
    for p in pages:
        for t in p.tags or ["untagged"]:
            sections.setdefault(t, []).append(p)

    lines = [
        "# Knowledge Wiki Index",
        "",
        f"> {len(pages)} pages | auto-maintained | 检索建议: 先按tag定位, 再读页面全文",
        "",
    ]
    tag_order = ["standard", "pitfall", "exemplar", "synthesis"]
    for t in tag_order + sorted(k for k in sections if k not in tag_order):
        if t not in sections:
            continue
        lines.append(f"## {t}")
        for p in sorted(sections[t], key=lambda x: x.name):
            lines.append(f"- [[{p.name}]] — {p.title}")
        lines.append("")
    (WIKI_DIR / f"index{PAGE_SUFFIX}").write_text("\n".join(lines), encoding="utf-8")


def append_log(op: str, target: str, detail: str = "") -> None:
    """追加 log.md 条目(llm_wiki.md: '## [date] op | target' 前缀约定)."""
    WIKI_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    line = f"## [{ts}] {op} | {target}"
    if detail:
        line += f"\n{detail}"
    with open(WIKI_DIR / f"log{PAGE_SUFFIX}", "a", encoding="utf-8") as f:
        f.write(line + "\n")


def lint() -> list[str]:
    """wiki 健康检查(llm_wiki.md Lint操作): 孤儿页/缺编号/超大页/坏链接."""
    issues: list[str] = []
    pages = load_pages()
    if not pages:
        return ["wiki 为空: 没有任何知识页面,请先运行蒸馏(gdd-review distill)"]

    names = {p.name for p in pages}
    inbound: dict[str, int] = {n: 0 for n in names}
    for p in pages:
        for link in re.findall(r"\[\[([^\]]+)\]\]", p.body):
            if link in inbound:
                inbound[link] += 1
        size = len(p.body)
        if size > 20000:
            issues.append(f"[超大页] {p.name}: {size}字符,建议拆分")
        has_entries = any(m in p.body for m in ("[S", "[D", "[P", "[G"))
        if p.tags and not has_entries:
            issues.append(f"[无编号条目] {p.name}: tags={p.tags} 但正文无[S/D/P/G]编号")

    for n, c in inbound.items():
        if c == 0:
            issues.append(f"[孤儿页] {n}: 无任何页面链接到它,建议在相关页面添加[[{n}]]")

    return issues
