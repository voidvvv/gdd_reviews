# GDD Review — 游戏设计文档评审框架

基于 CrewAI 的多 Agent GDD 评审框架。知识库采用 Karpathy LLM Wiki 模式(参考 `llm_wiki.md`):纯 markdown 页面 + index/log 双索引,无向量库、无嵌入成本。

## 功能

1. **蒸馏**: 把 `raw_gdds/` 下的真实 GDD(有好有坏,可选 `.notes` 人工标注)蒸馏成 wiki 知识库(标准/反例/范例三类页面)
2. **评审**: `gdd-review review <gdd路径>` 四维度评审,输出 markdown 报告到 `reports/`
   - 一致性检查(文档内部矛盾,不依赖知识库)
   - 深度检查(对照 wiki 标准 [S*][D*])
   - 缺陷检查(对照反例库 [P*],**知识不足自动跳过并在报告中说明**)
   - 亮点检查(对照范例 [G*],**知识不足自动跳过并在报告中说明**)
   - **对抗组**: 每个维度"审查员 → 质询员(红方)"两轮,指控须过质询才进正式结论
3. **Lint**: 知识库健康检查(孤儿页/无编号条目/超大页)

## 快速开始

```bash
# 1. 配置 key(.env 已建好,填入即可;兼容任意 OpenAI 协议端点)
echo 'OPENAI_API_KEY=你的key' >> .env

# 2. 蒸馏: 把真实GDD放进 raw_gdds/(可先 cp sample_gdds/* raw_gdds/ 试跑)
uv run gdd-review distill

# 3. 复核知识库(重要:LLM 蒸馏产物须人工过目)
#    编辑 knowledge_wiki/*.md → uv run gdd-review lint

# 4. 评审
uv run gdd-review review raw_gdds/sample_bad_gdd.md
# 报告输出: reports/*_评审报告_*.md
```

## 目录结构

```
gdd_review/
├── raw_gdds/            # 原始GDD语料(不可变);同名.notes=人工粗标注
├── extracted/           # 蒸馏中间产物(单文档盘点,审计链,勿删)
├── drafts/              # synthesize 草稿(人工复核对象)
├── knowledge_wiki/      # ★ 知识库(markdown,git管理)
│   ├── standards-gdd.md #   [S*][D*] 标准 "该有什么"
│   ├── pitfalls-gdd.md  #   [P*] 反例四元组 "见到什么拍桌子"
│   ├── exemplars-gdd.md #   [G*] 范例 "好成什么样"
│   ├── index.md         #   内容目录(自动)
│   └── log.md           #   操作日志(append-only)
├── reports/             # 评审报告输出
├── sample_gdds/         # 示例GDD(好/坏各一,含故意缺陷)
└── src/gdd_review/
    ├── cli.py           # 入口
    ├── wiki.py          # wiki层: 页面/检索/门控/index/log/lint
    ├── gdd_tools.py     # Agent工具: wiki_search/wiki_read/gdd_read
    ├── review.py        # 评审Crew(4维度×对抗组+主审)
    ├── distill.py       # 蒸馏Crew(extract→synthesize)
    └── llm.py           # LLM配置+预检
```

## 人工标注格式(可选但强烈建议)

`raw_gdds/<gdd名>.notes`,每行一条,10 分钟粗标即可:

```
3.2节 抽卡保底: 坏设计,当年被喷了
5.1节 经济产出表: 写得好,被别的项目抄了
第7章 技术边界: 缺,吃了大亏
```

蒸馏时这些判断被原样收录并展开为反例/范例条目——**人的判断是稀缺信号,AI 只做展开,不发明判断**。

## 知识门控规则

缺陷/亮点维度开跑前检查知识库: pitfall 页面≥2 且条目≥5(缺陷)、exemplar 页面≥2 且条目≥5(亮点)。不足则跳过该维度 Agent 评审,报告"知识库状态"一节**明确说明原因**并建议先蒸馏——不会用通用审美虚构发现。

## 调试

```bash
uv run gdd-review wiki           # 看知识库状态+门控结论(不调LLM)
uv run gdd-review wiki 抽卡 保底  # 试检索
```
