"""Agent 工具层: wiki 检索/阅读 + GDD 文档访问."""

from __future__ import annotations

from pathlib import Path

from crewai.tools import BaseTool
from pydantic import BaseModel, Field

from gdd_review import wiki


class WikiSearchInput(BaseModel):
    query: str = Field(..., description="检索问题或关键词,如 '抽卡保底的设计陷阱'")
    tag: str | None = Field(
        None,
        description="按tag过滤: pitfall(反例)/standard(标准)/exemplar(范例);留空搜全部."
        "注意: 仅关键词检索模式支持tag过滤",
    )


class WikiSearchTool(BaseTool):
    name: str = "wiki_search"
    description: str = (
        "在GDD评审知识库做语义检索(向量匹配,同义表述也能召回,如'概率上限'能搜到'保底')。"
        "命中后用 wiki_read 读该页全文获取完整条目和检查动作。"
        "搜不到时换一种问法重试,仍无命中则如实返回无相关标准。"
    )
    args_schema: type[BaseModel] = WikiSearchInput

    def _run(self, query: str, tag: str | None = None) -> str:
        # 语义检索优先; 未配置embedding或向量库为空时降级关键词检索
        if tag is None:
            semantic = _semantic_search(query)
            if semantic is not None:
                if not semantic:
                    return "无命中。建议: 换一种问法重试(语义检索已启用,同义表述也应能命中)。"
                return "\n\n".join(
                    f"## {h['page']} (来源:{h['source']}, 相关度{h['score']:.2f})\n"
                    f"{h['content'][:400]}"
                    for h in semantic
                )
        hits = wiki.search(query, tag=tag)
        if not hits:
            return "无命中。建议: 换同义词/减少关键词/去掉tag过滤后重试。"
        mode_note = (
            "(关键词模式: 语义检索未启用,配置EMBEDDING_*后运行embed升级)\n"
            if tag is None
            else ""
        )
        return mode_note + "\n\n".join(
            f"## {h['name']} (tags:{','.join(h['tags'])})\n{h['snippet']}" for h in hits
        )


def _semantic_search(query: str) -> list[dict] | None:
    """语义检索向量库. 返回 None 表示不可用(降级关键词), 空列表表示无命中."""
    from gdd_review import rag_sync

    if not rag_sync.embedding_configured():
        return None
    try:
        return rag_sync.search(query)
    except Exception:
        # 向量库未初始化/连接失败等 → 降级关键词, 不阻塞评审
        return None


class WikiReadInput(BaseModel):
    page: str = Field(..., description="页面名,如 pitfalls-economy")


class WikiReadTool(BaseTool):
    name: str = "wiki_read"
    description: str = "读取wiki一个页面的完整内容(全部条目+编号+检查动作)。"
    args_schema: type[BaseModel] = WikiReadInput

    def _run(self, page: str) -> str:
        content = wiki.read_page(page)
        if content is None:
            available = ", ".join(p.name for p in wiki.load_pages()) or "(空)"
            return f"页面不存在。可用页面: {available}"
        return content


class GddReadInput(BaseModel):
    section: str | None = Field(
        None,
        description="可选:只读某一章。匹配规则: 章节标题包含该词,如 '经济'/'3'",
    )


class GddReadTool(BaseTool):
    """让 Agent 按需读取待评审 GDD 的章节,而不是全文塞上下文."""

    name: str = "gdd_read"
    description: str = (
        "读取当前待评审GDD的内容。可传section只读某章(按标题关键词匹配),"
        "不传读全文。长文档请分章节读取,避免遗漏。"
    )
    args_schema: type[BaseModel] = GddReadInput

    def _run(self, section: str | None = None) -> str:
        # GDD 路径由 cli 在运行前写入环境变量,工具运行时读取
        import os

        gdd_path = os.environ.get("GDD_UNDER_REVIEW")
        if not gdd_path:
            return "错误: 当前没有待评审的GDD(环境变量GDD_UNDER_REVIEW未设置)。"
        content = Path(gdd_path).read_text(encoding="utf-8")
        if not section:
            return content
        # 按markdown标题切块,标题含关键词的块全部返回
        blocks: list[tuple[str, str]] = []
        current_title = "(开头)"
        current: list[str] = []
        for line in content.splitlines():
            if line.lstrip().startswith("#"):
                if current:
                    blocks.append((current_title, "\n".join(current)))
                current_title = line.lstrip("# ").strip()
                current = [line]
            else:
                current.append(line)
        if current:
            blocks.append((current_title, "\n".join(current)))
        matched = [b for t, b in blocks if section.lower() in t.lower()]
        if not matched:
            titles = "\n".join(f"- {t}" for t, _ in blocks)
            return f"无标题含'{section}'的章节。文档章节:\n{titles}"
        return f"({len(matched)}个章节命中)\n\n" + "\n\n".join(matched)
