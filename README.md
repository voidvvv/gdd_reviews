# GDD Review — 游戏设计文档评审框架

基于 [CrewAI](https://crewai.com) 的多智能体 GDD（Game Design Document）评审框架。

给它一份游戏设计文档，它会从**一致性、深度、缺陷、亮点**四个维度进行评审——每个维度都配备"审查员 + 质询员（红方）"对抗组，指控必须经受有理有据的质询才能进入正式结论——最终输出一份 markdown 评审报告。

评审所依据的知识库采用 **Karpathy LLM Wiki 模式**（参考 [llm_wiki.md](https://github.com/karpathy/llm.c) 思想）：纯 markdown 页面 + 关键词检索，无向量库、无嵌入成本，人工可直接阅读和修订。框架还内置**蒸馏流水线**，可把你手里的真实 GDD（有好有坏）提炼成标准/反例/范例三类知识页面。

## 核心特性

| 特性 | 说明 |
|------|------|
| 四维度评审 | 一致性（文档内部矛盾）· 深度（对照标准）· 缺陷（对照反例库）· 亮点（对照范例） |
| 对抗组 | 每个维度"审查员 → 质询员（红方）"两轮制，逐条 `[推翻+理由]` 或 `[确认+补强]`，主审只采纳确认项 |
| 人话报告 | 每条发现先一句大白话（"第x章与第y章相违背"式），报告末尾必附"通俗总结"逐条翻译，非评审背景的团队成员也能读懂 |
| 知识充分性门控 | 缺陷/亮点维度在知识库不足时**自动跳过**，并在报告"知识库状态"一节明确说明——拒绝用通用审美虚构发现 |
| Wiki 知识库 | markdown 页面 + `[S*][D*][P*][G*]` 稳定编号 + index/log 双索引 + lint 健康检查 |
| 两阶段蒸馏 | extract（逐份事实盘点）→ synthesize（跨文档归纳），支持 `.notes` 人工标注注入 |
| 模型无关 | OpenAI 兼容协议接入（默认智谱 BigModel 编程端点），换供应商只改 `.env` |

## 快速开始

### 1. 安装与配置

```bash
cd gdd_review
uv sync                     # 安装依赖(需 Python >=3.10 <3.14, uv 包管理)

# 配置大模型(默认智谱 BigModel;也可换任何 OpenAI 兼容端点)
echo 'OPENAI_API_KEY=你的key' >> .env
```

`.env` 可配置项：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `OPENAI_API_KEY` | （空，必填） | API Key，智谱获取：https://open.bigmodel.cn/usercenter/apikeys |
| `OPENAI_BASE_URL` | `https://open.bigmodel.cn/api/coding/paas/v4` | OpenAI 兼容端点 |
| `OPENAI_MODEL` | `GLM-5.2` | 模型名（区分大小写） |

### 2. 蒸馏：把真实 GDD 变成知识库

```bash
# 把你的真实 GDD(markdown)放进 raw_gdds/
cp /path/to/你的GDD.md raw_gdds/

# 可选但强烈建议: 加人工粗标注(10分钟/份,显著提升蒸馏质量)
cat > raw_gdds/你的GDD.md.notes <<'EOF'
3.2节 抽卡保底: 坏设计,当年被喷了
5.1节 经济产出表: 写得好,被别的项目抄了
第7章 技术边界: 缺,吃了大亏
EOF

uv run gdd-review distill
```

蒸馏产物（**务必人工复核后再用于评审**）：

```
knowledge_wiki/
├── standards-gdd.md    # [S*][D*] 结构标准与设计规范 —— "该有什么"
├── pitfalls-gdd.md     # [P*] 反例四元组 —— "见到什么拍桌子"
├── exemplars-gdd.md    # [G*] 亮点范式 —— "好成什么样"
├── index.md            # 内容目录(自动维护)
└── log.md              # 操作日志(append-only)
extracted/              # 单文档盘点(审计链,勿删)
drafts/synthesize_draft.md   # 合成草稿(人工复核对象)
```

蒸馏纪律（已内置于提示词）：全部文档都有的设计 → "必须"级标准；过半 → "推荐"；仅一份 → "可选方案"；反例只能来自人工标注判"坏"的设计，AI 只展开判断、不发明判断。

> 试跑参考：用 `sample_gdds/` 两份示例蒸馏出的知识库含 [S1]-[S6]（必须级标准）、[D1]-[D7]（可选方案）、[P1]-[P7]（反模式）、[G1]-[G6]（亮点范式）共 26 条——可直接 `cp sample_gdds/*.md raw_gdds/ && uv run gdd-review distill` 复现。

### 3. 评审

```bash
uv run gdd-review review /path/to/待评审GDD.md
# 报告输出: reports/<文档名>_评审报告_<时间戳>.md
```

报告结构：

```markdown
# GDD 评审报告
## 报告怎么读          ← 三行大白话: 整体结论/最要命的问题/先做什么
## 知识库状态          ← 门控结论;被跳过的维度附一句"这对读者意味着什么"
## 确认的发现
### 错误(一致性)       ← 每条先一句大白话(如"第x章与第y章相违背"),再: 位置/严重度/证据/依据编号/修改建议
### 不足(深度)
### 缺陷(反例命中)     ← 引用 [P*] 编号,注明禁令/反模式档位
### 亮点               ← 说明超出哪条基线;无真材实料则明说"无突出亮点"
## 已排除的指控        ← 每条一句话: 原以为是什么问题、为什么其实不是
## 总评与优先级建议
## 通俗总结            ← 末节必写: 全部发现逐条大白话,只读这节也能懂
```

### 4. 知识库维护

```bash
uv run gdd-review lint           # 健康检查: 孤儿页/无编号条目/超大页
uv run gdd-review wiki           # 查看页面数与门控结论(不调LLM)
uv run gdd-review wiki 抽卡 保底  # 试检索,看关键词命中(不调LLM)
```

直接编辑 `knowledge_wiki/*.md` 即可修订知识——保存即生效，无需重建任何索引。

## 工作原理

### 评审流水线（CrewAI Crew，顺序执行）

```
待评审GDD (gdd_read 按章节读取)
   │
   ├─ ① 一致性审查员 → ①' 一致性质询员(红方)      [始终执行,不依赖知识库]
   ├─ ② 深度审查员   → ②' 深度质询员(红方)        [始终执行,检索 standards]
   ├─ ③ 缺陷审查员   → ③' 缺陷质询员(红方)        [门控: pitfall页面≥2 且 [P条目≥5]
   ├─ ④ 亮点识别员   → ④' 亮点质询员(红方)        [门控: exemplar页面≥2 且条目≥5]
   │
   └─ ⑤ 主审: 只采纳质询后[确认]的发现 → 评审报告
```

- 空知识库时 Crew 为 5 个任务（2 维度 + 报告），知识充分时 9 个任务
- 每个审查员/质询员是独立的 CrewAI `Agent`（role/goal/backstory 定义对抗职责），挂载 `wiki_search`/`wiki_read`/`gdd_read` 工具
- 质询员的举证责任：一致性质询查"矛盾双方是否不同语境"；缺陷质询用 `wiki_read` 核实 `[P*]` 条目真实存在；亮点质询剔除"仅达标"与主观偏好

### Agent 工具（`src/gdd_review/gdd_tools.py`）

| 工具 | 作用 |
|------|------|
| `wiki_search(query, tag)` | 关键词检索知识库，返回命中页面名+片段；支持 tag 过滤（pitfall/standard/exemplar） |
| `wiki_read(page)` | 读取页面全文（完整条目+检查动作） |
| `gdd_read(section?)` | 读取待评审 GDD；传 section 按标题关键词只读某章（长文档分章读，防上下文溢出） |

### 为什么用 Wiki 而不是向量 RAG

评审知识是**小而精的人工把关语料**（几十页以内），不是海量原文：

- 反例四元组（设计+后果+检查动作）是原子单位——向量切块会把它切碎，检索到"这是反模式"却丢了"该查什么"
- markdown 即知识：人工复核、修订、git 版本管理都是原生能力，改完即生效
- 零基建：不需要 embedder 配置、建库脚本、向量库落盘运维
- 检索是关键词匹配，Agent 靠"换同义词重试 + 搜读分离"多跳迭代弥补语义缺口

## 目录结构

```
gdd_review/
├── raw_gdds/                # 原始GDD语料(蒸馏输入,不可变);同名.notes=人工标注
├── extracted/               # 蒸馏中间产物(单文档盘点,审计链)
├── drafts/                  # synthesize 草稿(人工复核对象)
├── knowledge_wiki/          # ★ 知识库(markdown,git管理)
├── reports/                 # 评审报告输出
├── sample_gdds/             # 示例GDD(坏文档含故意缺陷/好文档各一,可试跑)
└── src/gdd_review/
    ├── cli.py               # CLI入口: review/distill/lint/wiki
    ├── wiki.py              # wiki层: 页面/检索/门控/index/log/lint
    ├── gdd_tools.py         # Agent工具: wiki_search/wiki_read/gdd_read
    ├── review.py            # 评审Crew: 4维度×对抗组+主审
    ├── distill.py           # 蒸馏Crew: extract→synthesize
    └── llm.py               # LLM配置+连通性预检
```

## 功能扩展指南

框架各层解耦，常见扩展点：

**加一个评审维度**（如"商业化合规"）：在 `review.py` 按"审查员+质询员+两个 Task（第二个 `context=[第一个]`）"的模式复制一组，需要门控就用 `wiki.knowledge_sufficiency()` 包一层，并把新维度追加进 `tasks` 列表与主审报告模板。

**加一个 Agent 工具**（如查数值库）：在 `gdd_tools.py` 按 `BaseTool` + `args_schema` 模式新增，挂到相关 Agent 的 `tools` 列表。

**加一类知识**（如"品类检查清单"）：新建带 `tags: [checklist]` 的 wiki 页面，条目沿用稳定编号（如 `[C1]`），必要时在 `wiki.py` 的 `knowledge_sufficiency` 注册新维度的门控规则。

**换 LLM 供应商**：改 `.env` 三个变量即可，任何 OpenAI 兼容端点（OpenAI 官方/DeepSeek/Moonshot/vLLM 自托管）无需改代码。

**做成长驻服务**：把 `build_review_crew()` 的结果做成单例（每个 GDD 评审设置 `GDD_UNDER_REVIEW` 环境变量后 kickoff），避免重复组装。

## 常见问题

- **启动报 `OPENAI_API_KEY 未设置`** → 填 `.env`；若 shell 残留旧环境变量会优先于 `.env`，先 `unset OPENAI_API_KEY`
- **评审报告里缺陷/亮点维度显示"跳过"** → 知识库不足门控阈值，先跑 `distill` 并复核 `pitfalls-gdd.md`/`exemplars-gdd.md`
- **Agent 检索不到明明有的知识** → 关键词匹配的固有短板：写页面时把同义词写进正文（如"关键词: 保底/抽卡补偿/概率"），或让页面标题更贴近评审时的提问用词
- **蒸馏质量不稳** → 检查 `.notes` 标注是否提供了足够信号；无标注的文档 AI 只能做事实盘点，判断质量取决于 synthesize 阶段的跨文档对比

## 诚实的边界

- 蒸馏产物必须人工复核——LLM 只展开你的判断，不发明判断；`drafts/` 就是为此保留的
- 亮点识别天然对抗 LLM 谄媚倾向（提示词已加"允许交白卷"许可），但仍建议对亮点结论保持审慎
- 一致性检查最可靠（只依赖文档自身交叉核对），缺陷/亮点检查的质量上限 = 你的知识库质量上限

## 技术栈

- [CrewAI](https://github.com/crewAIInc/crewAI) v1.15+ — Agent/Crew/Task/Tool 抽象
- Pydantic — 工具入参 schema 与配置校验
- PyYAML — wiki 页面 frontmatter 解析
- uv — 包管理与虚拟环境
