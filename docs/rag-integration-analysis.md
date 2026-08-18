# RAG 接入分析：crewAI 机制审计与 gdd_review 接入方案

> 结论产出时间：2026-08-18
> 分析范围：crewAI v1.15.16 源码（`lib/crewai` + `lib/crewai-tools`）+ 本项目现状
> 状态：**方案已定，尚未实施**。实施时以本文档第三节为准。

---

## 一、crewAI 的 RAG 机制审计（源码结论）

### 1.1 调用链全景

```
RagTool (crewai_tools/tools/rag/rag_tool.py)
  └─ CrewAIRagAdapter (crewai_tools/adapters/crewai_rag_adapter.py)   ← 默认路径
       └─ crewai.rag 原生 client → ChromaDBClient.add_documents (chromadb/client.py)
  └─ RAGAdapter → RAG (crewai_tools/rag/core.py)                      ← 旧路径，非默认
```

Crew 级 `Knowledge`（`Crew(knowledge_sources=[...])`）最终也走到同一个
`add_documents()` → `collection.upsert()`（knowledge_storage.py:120）。

### 1.2 chunk 与 embedding 是两件事

| 动作 | 性质 | 费用 |
|------|------|------|
| chunk（分块） | 纯 Python 字符串切分（TextChunker 等） | **零 token** |
| embedding（向量化） | 调 embedding API | **唯一的文档级 token 费用** |

### 1.3 embedding 的两个触发时机

1. **每次 `rag_tool.add()`**：末端是 `collection.upsert(ids, documents)`
   （chromadb/client.py:354），只传文本不传向量——ChromaDB 在 upsert 内部
   对**每一条**文本调 embedding 接口，按批（默认 100 条/批）执行。
2. **每次检索 `query`**：仅嵌入问题文本本身（几十 token/次），可忽略但需知情。

### 1.4 同一文档会被重复 embedding 吗？——会

- **默认路径（CrewAIRagAdapter）**：`add()` 无任何内容指纹门控。重复 add
  未变化的文件 → 重新 load + chunk + **全额重付 embedding 费**。存储上因
  chunk ID 是确定性哈希（`sha256(doc_id_序号_内容)`，crewai_rag_adapter.py:337）
  而同 ID 覆盖，库里不堆积——**存储幂等，费用不幂等**。
- **旧路径（core.py）**：有"已存在就 return"的门控（core.py:151-155），但
  embedding 发生在门控检查**之前**（core.py:123）——钱同样已经花了。
  （注意：早先讨论中曾误判旧路径能省钱，此处为更正后的结论。）
- `EmbeddingService` 无任何缓存（grep `cache|lru` 零命中）。

### 1.5 定性：哪些是 bug

| 行为 | 定性 |
|------|------|
| 重复 add 未变化文档 → 重复付 embedding 费 | 设计偷懒，无害（存储结果正确） |
| 文档内容修改后重新 add → **旧版本 chunk 残留**，检索可召回过期内容 | **真回归/缺陷**。旧路径 core.py:157-159 会先删旧 chunk，新路径丢失了该清理；且新 `BaseClient` API 只暴露 `delete_collection`，无按文档删除接口，想清理都做不到 |

**推论：任何"入库前查重省钱"的门控必须自己做在 `add()` 之前，框架不会帮你。**

---

## 二、gdd_review 现状：知识管理是怎么做的

当前体系**无 embedding，纯关键词匹配**。三层流水线：

```
raw_gdds/*.md          原始 GDD 语料（只读，有好有坏）
    │  gdd-review distill（人工触发，调 LLM：extract 逐份盘点 → synthesize 跨文档归纳）
    ▼
extracted/*.md         每份 GDD 一份"事实盘点"（只记录不评价）
    ▼
knowledge_wiki/*.md    人工复核后的知识页，条目带稳定编号：
                       [S*]/[D*] 标准、[P*] 反例、[G*] 亮点范式
```

- **存储**：markdown 文件 + frontmatter（title/tags/sources），自动维护
  `index.md`（内容目录）与 `log.md`（操作日志）。
- **检索**：`wiki.search()`（wiki.py:115）——查询拆词后逐词**子串匹配**页面
  正文，按命中词数排序。搜"保底"召回不了写成"概率上限"的条目——这是想上
  RAG 的根本动机。
- **Agent 工具**：`wiki_search`（关键词检索）/ `wiki_read`（读整页，质询员
  靠它核实 [P*] 条目真实性）/ `gdd_read`（按章节确定性读待评审 GDD）。
- **知识门控**：`knowledge_sufficiency()` 数反例/范例页面与条目数，不足则
  跳过缺陷/亮点维度，防止知识不足时编造。

### 已知债务（与 RAG 无关但同源，一并记录）

1. `run_distill()` 每次全量重跑，不比对内容哈希——10 份未变的 GDD 也重付
   10 次 LLM 提取费。
2. `_split_to_wiki_pages()` 每次整体覆写三个 wiki 页面——**人工修订会被
   后续 distill 冲掉**。修复方向：extract 加内容指纹门控；synthesize 只写
   drafts/，新增 promote 子命令经人工确认后落 wiki。

---

## 三、RAG 接入方案（已定稿）

### 3.1 核心原则

1. **蒸馏与 RAG 分层**：蒸馏是"理解层"（LLM 判断，产出带编号的标准/反例），
   RAG 是"检索层"（读时语义匹配）。RAG 索引的是**蒸馏产物（wiki 页面）**，
   不是原始 GDD。原始 GDD 直接入 RAG 会绕过编号体系与样本量纪律，质询员
   将失去核实锚点。
2. **embedding 与检索分离**：入库（花钱）收拢到独立的 `gdd-review embed`
   命令，人工触发；评审流程**只读**。Agent 工具面不暴露 add 能力，杜绝
   Agent 污染检索源。
3. **各内容去向**：

| 内容 | 处理方式 | Agent 读到什么 |
|------|---------|---------------|
| `raw_gdds/*.md`（评审语料） | 只进蒸馏，**不入 RAG** | — |
| `knowledge_wiki/*.md` | 蒸馏产物，`embed` 命令同步入 RAG | 带编号的标准/反例条目 |
| 竞品分析等事实参考 PDF | 直接 add（纯事实，无需蒸馏） | 原文片段，用于核对事实 |
| 待评审 GDD | 不入 RAG，走 `gdd_read` | 确定性全文（一致性检查不能有漏检） |

### 3.2 目标形态

```
更新 wiki 页面
    │  手动执行（唯一文档嵌入时机）
    ▼
gdd-review embed     ← 新命令：删集合 → 整库重嵌入（全量重建策略）
    ▼
向量库（本地 ChromaDB 落盘）
    │  评审时只读
    ▼
gdd-review review    ← WikiSearchTool 底层换向量检索
                       （每次检索仅嵌入问题文本，几十 token/次）
```

### 3.3 实施要点

**新增 `src/gdd_review/rag_sync.py`**：

```python
from crewai_tools.tools import RagTool

def build_rag_tool() -> RagTool:
    return RagTool(config={
        "vectordb": {"provider": "chromadb", "config": {"dir": "./kb_storage"}},
        "embedding_model": {
            "provider": "openai",
            "config": {
                "api_key": os.getenv("OPENAI_API_KEY"),
                "api_base": "https://open.bigmodel.cn/api/paas/v4",
                "model_name": "embedding-3",   # 智谱兼容端点
            },
        },
    })

def rebuild_index() -> None:
    """全量重建: 删集合 → 整库重嵌入。简单，永远干净。"""
    tool = build_rag_tool()
    tool.adapter._client.delete_collection(collection_name="gdd_wiki")
    tool.collection_name = tool.adapter.collection_name = "gdd_wiki"
    tool.add(directory_path="knowledge_wiki/")
```

**为什么选全量重建而非增量**：当前 wiki 仅数页、数千 token，整库重嵌入
每次几分钱；增量方案必须处理"改过的页面旧 chunk 删不掉"（见 1.5 的底层
缺陷），需按页分 collection，复杂度不值。wiki 长到几十页后再演进为
manifest 哈希门控 + 分页 collection。

**改造 `WikiSearchTool._run`**（gdd_tools.py）：底层换
`client.search(collection_name="gdd_wiki", query=..., limit=5,
score_threshold=0.5)`，返回片段 + 来源页面名。保持不变：`wiki_read`
（核实编号必须读原页）、`gdd_read`（确定性全文）、`knowledge_sufficiency`
门控（管"知识够不够"，与检索方式无关）。

**cli.py 新增 `embed` 分支**：调 `rag_sync.rebuild_index()`，打印页数与
耗时；重复执行安全（幂等重建）。

### 3.4 费用全景

| 动作 | 触发者 | embedding 费用 |
|------|--------|---------------|
| `gdd-review embed` | 人工 | **唯一文档嵌入费**：wiki 规模 × 每次更新 |
| review 中每次 wiki_search | Agent | 仅问题文本（≈几十 token/次，一次评审合计可忽略） |
| review 中 LLM 推理 | 自动 | 原有费用，不变 |
| 重复跑 review | 自动 | **文档零重复嵌入**（只读） |

### 3.5 遗留决策点

- [ ] `RagTool.summarize` 参数在默认 adapter 的 query 中未生效，检索返回
      原文 chunk 拼接——按无摘要预期使用即可。
- [ ] wiki 页面被 `embed` 后又被人工改动：以 embed 时刻为准，重跑 embed
      即可（全量重建无脏状态）。
- [ ] 未来若接 PDF 参考资料，注意大文件"不动就不 add"兜底（底层无 chunk
      级增量）。
