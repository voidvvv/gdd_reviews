# AGENTS.md — GDD Review 项目开发指南(AI 助手版)

本文件面向在此仓库工作的 AI 编码助手(Claude Code / Codex / Cursor 等)。
读完本文件即可理解项目全貌,无需重新逆向工程。

## 项目是什么

基于 CrewAI 的游戏设计文档(GDD)评审框架。核心循环:

1. **蒸馏**(`distill`): 把 `raw_gdds/` 下的真实 GDD(有好有坏,可带 `.notes` 人工标注)两阶段提炼成 wiki 知识库
2. **评审**(`review`): 对用户传入的 GDD 做 4 维度对抗式评审(一致性/深度/缺陷/亮点),输出 markdown 报告
3. **维护**(`lint`/`wiki`): 知识库健康检查与调试

知识库是 **Karpathy LLM Wiki 模式**: 纯 markdown 为唯一事实源;检索默认走派生语义索引(向量 RAG,可选),未配置 embedding 时降级关键词。wiki→向量的同步收拢在 `embed` 一个命令里,评审流程只读(设计依据见下"关键设计决策"与 docs/rag-integration-analysis.md)。

## 技术栈与运行

- Python >=3.10 <3.14, uv 管理依赖, 无测试框架(验证靠断言脚本)
- **CrewAI v1.15+**: `Agent`(role/goal/backstory) + `Task`(description/expected_output/context) + `Crew`(process=sequential) + `BaseTool`(name/description/args_schema/_run)
- LLM 走 OpenAI 兼容协议(`llm.py` 的 `get_llm()`),默认智谱 BigModel 编程端点,配置在 `.env`
- 常用命令:

```bash
uv sync                              # 安装
uv run gdd-review review <gdd路径>    # 评审 → reports/
uv run gdd-review distill            # 蒸馏 raw_gdds/ → knowledge_wiki/
uv run gdd-review embed              # 重建语义索引(需EMBEDDING_*;唯一文档嵌入时机)
uv run gdd-review lint               # 知识库健康检查
uv run gdd-review wiki [关键词]       # 调试: 看页面/门控/试检索(不调LLM)
```

## 代码地图(修改前必读)

```
src/gdd_review/
├── cli.py          # 入口 + load_dotenv;五个子命令路由(review/distill/embed/lint/wiki)
├── wiki.py         # 知识库层(无LLM依赖,可独立测试)
│   ├── WikiPage    #   frontmatter(title/tags/sources)+body;条目编号[S*][D*][P*][G*]
│   ├── load_pages/save_page/delete_page
│   ├── search()    #   关键词检索(逐词匹配+tag过滤+按命中数排序)
│   ├── knowledge_sufficiency(dim)  # ★ 门控: defect需pitfall页≥2且[P条目≥5;highlight需exemplar页≥2且条目≥5
│   ├── rebuild_index/append_log    # index.md(内容目录)/log.md(时序日志,"## [ts] op | target"前缀约定)
│   └── lint()      #   孤儿页/无编号条目/超大页(>20000字符)
├── rag_sync.py     # 语义索引层(独立于wiki.py,评审流程不依赖它运行)
│   ├── embedding_configured()   # EMBEDDING_*三项是否齐全(缺任一项=未启用)
│   ├── rebuild_index()  # ★ embed命令本体: 删集合→整库重嵌入(全量重建,幂等)
│   └── search()         # 只读语义检索(仅嵌入问题文本,几十token/次)
├── gdd_tools.py    # Agent工具(BaseTool子类)
│   ├── WikiSearchTool   # wiki_search(query,tag): 语义优先,未启用时降级关键词(tag过滤仅降级模式支持)
│   ├── WikiReadTool     # wiki_read(page) 读全文 —— 搜读分离,Agent多跳迭代
│   └── GddReadTool      # gdd_read(section?) 读待审GDD,按markdown标题切块过滤
│                        # ★ GDD路径从环境变量 GDD_UNDER_REVIEW 读取(cli在kickoff前设置)
├── review.py       # 评审Crew: build_review_crew()组装,run_review()执行
├── distill.py      # 蒸馏Crew: extract_one()(Map) + synthesize()(Reduce) + _split_to_wiki_pages()
└── llm.py          # get_llm()惰性构造 + preflight_llm_check()预检(把平台业务错误翻译成中文提示)
```

数据目录(均在项目根):

```
raw_gdds/         蒸馏输入(不可变);<名>.notes=人工粗标注(每行"章节 判断")
extracted/        单文档盘点中间产物(审计链,勿删)
drafts/           synthesize草稿(人工复核对象)
knowledge_wiki/   知识库;index.md/log.md是特殊文件,load_pages会跳过
kb_storage/       语义索引落盘(gitignore;由embed命令生成,可随时删除重建)
reports/          评审报告输出(gitignore)
sample_gdds/      示例GDD: bad(埋了矛盾+含糊+无上限付费)/good(规范)各一
```

## 关键设计决策(改代码前先理解"为什么")

### 1. Wiki 为事实源 + 派生语义索引(而非向量库做主存储)
评审知识是小而精的人工把关语料。反例四元组(设计+后果+检查动作)是原子单位,向量切块会切碎;markdown 即知识,人工可复核可 git,改完即生效。因此 wiki markdown 是唯一事实源,向量索引只是只读投影。已按 docs/rag-integration-analysis.md 落地三条铁律:
- **嵌入与评审分离**: 文档 embedding 只发生在 `gdd-review embed`(手动触发);评审流程只读。Agent 工具面不暴露 add 能力,杜绝污染检索源
- **全量重建而非增量**: crewAI 底层"文档更新后旧 chunk 残留"缺陷(见分析文档1.5节)使增量更新无法清理旧版本;wiki 规模小,删集合→重嵌入最便宜且永远干净
- **优雅降级**: EMBEDDING_*未配置时 WikiSearchTool 自动降级关键词检索,框架开箱即用。降级判定在运行时(embedding_configured()),**不要**缓存到模块级(同门控坑)

### 2. 知识充分性门控(knowledge_sufficiency)
缺陷/亮点维度在知识不足时**跳过整个维度的 Agent 评审**(不是降级执行),主审报告"知识库状态"一节原文说明原因。目的: 防止 Agent 在无依据时用通用审美虚构发现。
**★ 踩过的坑: 门控必须在 `build_review_crew()` 函数体内实时求值。** 第一版写成模块级常量 `DEFECT_GATE = wiki.knowledge_sufficiency(...)`,导致同进程内"先蒸馏建库→再评审"时门控不翻转(满库仍 5 任务)。已修复——新增类似门控时同样不要缓存到模块级。

### 3. 对抗组(审查员+质询员红方)
每个维度两个 Agent: 审查员举证提出发现(一致性须给两处原文位置;缺陷须引[P*]编号;亮点须说明超出哪条基线),质询员逐条挑战并输出 `[推翻+理由]` 或 `[确认+补强]`(禁止和稀泥)。主审只采纳[确认]项,被推翻的进"已排除指控"一节。质询任务通过 `context=[前一任务]` 拿到审查产物。
新增维度必须遵循此两段式——只有审查员没有质询员的维度会破坏报告可信度。

### 4. 两阶段蒸馏(extract → synthesize)
- extract: 每份 GDD 一个 Task,**只记录事实禁止评价**;人工 `.notes` 标注原样收录(人的判断是稀缺信号)
- synthesize: 读全部盘点(非原始GDD),样本量纪律: 全有→必须/过半→推荐/仅1份→可选;**反例只能来自人工标注判"坏"的设计**,后果查不到写"后果未记录"禁止编造;分歧列"待人工判断"不裁决
- 拆两阶段的另一原因: 调 synthesize 提示词不重付 extract 的 LLM 费用
- Task description 用 `.replace()` 拼接而非 kickoff(inputs)——GDD 正文里的 `{花括号}` 会让 str.format 崩溃,**不要改回模板插值**

### 5. GDD 文档不经 kickoff inputs
待评审 GDD 通过环境变量 `GDD_UNDER_REVIEW` 传递,Agent 用 `gdd_read` 工具按章节拉取(长文档防上下文溢出)。同样因为花括号问题。

### 6. 报告结构由主审 Task description 硬编码
"报告怎么读/知识库状态/确认的发现(四小节)/已排除的指控/总评/通俗总结"结构写在 `t_report` 的 description 里。改报告结构=改这段提示词。
**可读性是硬性要求**(用户明确要求): 每条发现必须先一句大白话(如"第X章X.Y节与第M章M.N节相违背"),报告末尾必须附"通俗总结"逐条翻译成大白话——读者是不懂评审术语的人类团队成员。修改此处不得移除这两项。

## 扩展手册(常见任务怎么做)

### 加一个评审维度(如"商业化合规")
1. `review.py`: 按 consistency/depth 组的模式复制——审查员 Agent + 质询员 Agent + 两个 Task(第二个 `context=[第一个]`)
2. 需要门控: 在 `wiki.py` 的 `knowledge_sufficiency()` 的 `tag_map` 注册维度→(tag,编号前缀)映射,然后 `build_review_crew()` 里 `if xxx_gate["sufficient"]:` 包住两个 Task
3. 主审报告模板(`t_report` description)加对应小节
4. 验证: 空库/满库各断言一次任务数(参考"验证模式")

### 加一个 Agent 工具
`gdd_tools.py` 新增 `BaseTool` 子类: `name`/`description`(写清何时用,Agent 靠它决定调用)/`args_schema`(Pydantic,字段带 description)/`_run()`(错误直接 raise,信息会回到 Agent 上下文促其重试)。挂到相关 Agent 的 `tools`。

### 加一类知识
新建 wiki 页面 `tags: [新tag]`,条目用新前缀编号(如 `[C1]`);需要门控就同步改 `knowledge_sufficiency`。检索无需改动(search 按全文关键词)。

### 改 LLM / Embedding 供应商
`.env` 两组独立变量,任何 OpenAI 兼容端点,代码无需改:
- Agent 模型: OPENAI_API_KEY/OPENAI_BASE_URL/OPENAI_MODEL(必填)
- Embedding: EMBEDDING_API_KEY/EMBEDDING_BASE_URL/EMBEDDING_MODEL(可选,缺省=关键词检索)

模板见 `.env.example`(git管理,只讲配置方法不含真实值);用户真实配置写 `.env`(gitignore)。注意 `llm.py` 的 `preflight_llm_check` 已处理"平台业务错误返回 HTTP 200+空 choices"的情况(智谱特性)。换 embedding 模型后必须重跑 `gdd-review embed`(维度不同会维度不匹配)。

## 验证模式(本项目无 pytest,用断言脚本)

改完代码跑这三段(不调 LLM,零成本):

```bash
# 1. wiki层: 门控翻转+检索+lint
uv run python -c "
from gdd_review import wiki
g = wiki.knowledge_sufficiency('defect'); assert not g['sufficient']
wiki.save_page(wiki.WikiPage(name='t1', title='t', tags=['pitfall'], sources=['x'], body='- [P1] a\n- [P2] b\n- [P3] c'))
wiki.save_page(wiki.WikiPage(name='t2', title='t', tags=['pitfall'], sources=['x'], body='- [P4] d\n- [P5] e'))
assert wiki.knowledge_sufficiency('defect')['sufficient']
assert wiki.search('a') ; wiki.delete_page('t1'); wiki.delete_page('t2')"

# 2. Crew组装: 门控生效(空库5任务/满库9任务)
uv run python -c "
import os; os.environ['GDD_UNDER_REVIEW']='sample_gdds/sample_bad_gdd.md'
from gdd_review.review import build_review_crew
assert len(build_review_crew().tasks) == 5"

# 3. CLI冒烟(含embed未配置时的降级提示)
uv run gdd-review lint && uv run gdd-review wiki
uv run gdd-review embed; [ $? -eq 1 ] && echo "embed未配置保护 OK"
```

调 LLM 的真链路(蒸馏/评审)需要有效 key 和真实 token 消耗,由用户手动跑。

## 约定与红线

- **中文注释与提示词**: 所有 Agent role/goal/backstory、任务描述、用户可见输出均为中文;代码注释中文为主
- **知识条目编号稳定**: `[S*][D*][P*][G*]` 编号会被评审报告引用,页面合并/重排时保留编号,废弃条目删除而非复用编号
- **index.md/log.md 自动维护**: 不要手编;写页面一律走 `wiki.save_page()`(自动刷 index+log)
- **extracted/ 与 drafts/ 勿删**: 蒸馏审计链,报告引用的编号要能追溯回原始文档
- **distill 产物必须人工复核**: 框架设计上就把 drafts/ 留给人工把关,不要"优化"掉这个环节
- **不可变输入**: `raw_gdds/` 只增不改;改知识=改 `knowledge_wiki/` 后重跑对应评审
- 提交信息格式: `feat|fix|refactor|docs|chore: <描述>`
