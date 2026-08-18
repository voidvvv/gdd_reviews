"""RAG 同步层: 把 knowledge_wiki/ 页面嵌入向量库, 供语义检索.

设计依据 docs/rag-integration-analysis.md 第三节:
  - embedding 与评审流程分离: 入库只发生在手动执行 `gdd-review embed` 时,
    评审流程只读, 文档零重复嵌入
  - 全量重建策略: 删集合 → 整库重嵌入. wiki 规模小(几分钱/次),
    且规避 crewAI 底层"文档更新后旧 chunk 残留"的缺陷
  - Embedding 配置独立于 Agent LLM(EMBEDDING_* 变量), 可用不同供应商
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
KB_DIR = PROJECT_ROOT / "kb_storage"
COLLECTION_NAME = "gdd_wiki"
EMBEDDING_BATCH_DOCS = 50  # RagTool add 每批默认100, 这里留余量


def embedding_configured() -> bool:
    """embedding 配置是否齐全(缺任一项视为未启用, 检索降级关键词)."""
    return bool(
        os.getenv("EMBEDDING_API_KEY")
        and os.getenv("EMBEDDING_BASE_URL")
        and os.getenv("EMBEDDING_MODEL")
    )


def build_rag_tool(collection_name: str = COLLECTION_NAME) -> Any:
    """构造 RagTool(不在模块导入时调用, 避免 embedding 未配置时拖垮 CLI)."""
    from crewai_tools.tools import RagTool

    return RagTool(
        collection_name=collection_name,
        config={
            "vectordb": {
                "provider": "chromadb",
                "config": {"dir": str(KB_DIR)},
            },
            "embedding_model": {
                "provider": "openai",
                "config": {
                    "api_key": os.environ["EMBEDDING_API_KEY"],
                    "api_base": os.environ["EMBEDDING_BASE_URL"],
                    "model_name": os.environ["EMBEDDING_MODEL"],
                },
            },
        },
    )


def rebuild_index(wiki_dir: Path | None = None) -> dict[str, int]:
    """全量重建向量索引: 删集合 → 逐页 add. 返回统计.

    幂等: 重复执行安全; wiki 页面人工修订后重跑即可.
    """
    from gdd_review import wiki as wiki_mod

    wiki_dir = wiki_dir or wiki_mod.WIKI_DIR
    pages = [p for p in wiki_mod.load_pages()]
    if not pages:
        raise SystemExit(
            f"✗ {wiki_dir} 下没有知识页面, 先运行 gdd-review distill 建立知识库"
        )

    tool = build_rag_tool()
    client = tool.adapter._client  # noqa: SLF001 - 底层API: 删集合是唯一清理手段

    # 容忍首次运行时集合不存在
    try:
        client.delete_collection(collection_name=COLLECTION_NAME)
    except Exception:  # noqa: S110
        pass

    tool.add(directory_path=str(wiki_dir))
    count = _collection_count(client)
    return {"pages": len(pages), "chunks": count}


def _collection_count(client: Any) -> int:
    """读取集合 chunk 数(读失败返回 -1, 不阻塞主流程)."""
    try:
        collection = client.get_or_create_collection(
            collection_name=COLLECTION_NAME
        )
        return int(collection.count())
    except Exception:  # noqa: S110
        return -1


def search(
    query: str,
    limit: int = 5,
    score_threshold: float = 0.4,
) -> list[dict[str, Any]]:
    """语义检索向量库(只读, 仅嵌入问题文本). 返回 [{content, source, score}]."""
    tool = build_rag_tool()
    client = tool.adapter._client  # noqa: SLF001
    results: list[dict[str, Any]] = client.search(
        collection_name=COLLECTION_NAME,
        query=query,
        limit=limit,
        score_threshold=score_threshold,
    )
    out: list[dict[str, Any]] = []
    for r in results:
        meta = r.get("metadata") or {}
        out.append(
            {
                "content": r.get("content", ""),
                "source": str(meta.get("source", meta.get("file_path", "?"))),
                "page": Path(str(meta.get("file_path", ""))).stem or "?",
                "score": r.get("score", 0.0),
            }
        )
    return out
