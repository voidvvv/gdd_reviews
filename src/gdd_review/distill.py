"""蒸馏 Crew: 把 raw_gdds/ 下的真实GDD(有好有坏)蒸馏进 knowledge_wiki/.

两阶段(llm_wiki.md 之 Ingest 的GDD特化):
  extract   每份GDD一份事实盘点(只记录不评价)
  synthesize 跨文档归纳标准/反例/范例 → wiki页面(带编号与出处) → 人工复核

人工标注: 可选在 raw_gdds/<名>.notes 里逐条写 '章节 判断' 粗标注,
extract 阶段会展开为结构化判断依据。
"""

from __future__ import annotations

from pathlib import Path

from crewai import Agent, Crew, Task

from gdd_review import wiki
from gdd_review.llm import get_llm, preflight_llm_check

EXTRACT_TEMPLATE = """逐章盘点这份GDD,严格按模板输出,只记录事实、绝不评价好坏:

## 基本信息
品类 / 预估规模 / 总章节数 / 总字数级

## 章节清单
| 章节 | 包含要素(属性表/公式/流程说明/数值示例/边界条件) | 厚实还是单薄 |

## 关键设计决策(带数值和章节号)
- [系统名] 具体设计(数值) — 依据: 第X章

## 人工标注(评审人的真实判断,优先级最高,展开时不得违背)
{annotations}

## 含糊或缺失的部分(只描述现象,如'经济系统仅3行,无产出/回收表')

<gdd>
{content}
</gdd>"""


SYNTH_TEMPLATE = """基于以下{n}份GDD的盘点清单,产出评审知识草稿,按三节输出:

## standards(标准)
- [S1] <结构标准> | 等级:必须 | 依据: {n}份中{x}份(doc1,doc2...)
- [D1] <设计规范> | 等级:推荐 | 依据: ... | 注意: <例外情况>
样本量纪律: 全部文档都有→必须; 过半→推荐; 仅1份→可选方案并注明。
分歧不裁决,列入"待人工判断"。

## pitfalls(反例,四元组)
- [P1] 等级:禁令或反模式 | <坏设计>
  后果: <真实后果,来自人工标注或盘点中的事实,没有就写"后果未记录">
  检查动作: <见到什么关键词时必查什么>
反例来源只能是人工标注明确判为"坏"的设计,禁止自行发明。

## exemplars(亮点范式)
- [G1] <好设计/好写法> | 依据: doc名 | 可推广点: <为什么值得学>

## 待人工判断的分歧点
- <系统>: A方案(docs) vs B方案(docs), 分歧点<...>

<盘点清单们>
{extractions}
</盘点清单们>"""


def _load_annotations(gdd_path: Path) -> str:
    notes = gdd_path.with_suffix(".notes")
    if notes.exists():
        return notes.read_text(encoding="utf-8").strip()
    return "(无人工标注——仅做事实盘点,判断留给synthesize阶段结合其他文档)"


def extract_one(gdd_path: Path, extracted_dir: Path) -> Path:
    """单文档事实盘点(Map阶段)."""
    llm = get_llm()
    extractor = Agent(
        role="GDD 结构分析员",
        goal="客观盘点一份GDD包含什么",
        backstory=(
            "你是文档考古员,只记录事实、绝不评价好坏。"
            "记录设计决策必须带具体数值和章节号,模糊的标注'含糊'。"
            "人工标注是评审人的真实判断,原样收录并在synthesize阶段展开,不得改写其结论方向。"
        ),
        llm=llm,
    )
    content = gdd_path.read_text(encoding="utf-8")
    description = (
        EXTRACT_TEMPLATE.replace("{annotations}", _load_annotations(gdd_path))
        .replace("{content}", content)
    )
    task = Task(
        description=description,
        expected_output="按模板的markdown事实清单",
        agent=extractor,
    )
    result = Crew(agents=[extractor], tasks=[task]).kickoff()
    out = extracted_dir / f"{gdd_path.stem}.md"
    out.write_text(result.raw, encoding="utf-8")
    wiki.append_log("distill-extract", gdd_path.name, f"盘点: {out.name}")
    return out


def synthesize(extracted_dir: Path) -> list[Path]:
    """跨文档归纳(Reduce阶段) → 写入wiki页面,返回新建页面路径."""
    llm = get_llm()
    synthesizer = Agent(
        role="评审标准制定人",
        goal="跨文档归纳出可执行、带出处的GDD评审标准",
        backstory=(
            "你只声明证据支持的结论。样本量纪律: 全部文档都有写成'必须',"
            "过半写成'推荐',仅1份写成'可选方案'。"
            "反例只能来自人工标注判为'坏'的设计,后果查不到就写'后果未记录',"
            "禁止编造。分歧不裁决,列成'待人工判断'。"
            "每条标准带编号[S*][D*][P*][G*]和依据文档清单。"
        ),
        llm=llm,
    )
    files = sorted(extracted_dir.glob("*.md"))
    if not files:
        raise SystemExit(f"✗ {extracted_dir} 下没有盘点文件,先运行 extract")
    extractions = "\n\n---\n\n".join(
        f"### {p.stem}\n{p.read_text(encoding='utf-8')}" for p in files
    )
    description = (
        SYNTH_TEMPLATE.replace("{n}", str(len(files))).replace(
            "{extractions}", extractions
        )
    )
    task = Task(
        description=description,
        expected_output="按standards/pitfalls/exemplars/分歧四节的markdown草稿",
        agent=synthesizer,
    )
    result = Crew(agents=[synthesizer], tasks=[task]).kickoff()

    # 草稿落盘供人工复核
    drafts_dir = extracted_dir.parent / "drafts"
    drafts_dir.mkdir(exist_ok=True)
    draft = drafts_dir / "synthesize_draft.md"
    draft.write_text(result.raw, encoding="utf-8")

    # 同时直接产出wiki页面(人工复核后可删改)
    pages = _split_to_wiki_pages(result.raw, files)
    wiki.append_log(
        "distill-synthesize",
        f"{len(files)}份盘点",
        f"草稿: {draft.name} → 生成{len(pages)}个wiki页面",
    )
    return pages


def _split_to_wiki_pages(draft: str, files: list[Path]) -> list[Path]:
    """把合成草稿按节拆成 wiki 页面(standards/pitfalls/exemplars)."""
    sections = {"standards": "", "pitfalls": "", "exemplars": ""}
    current: str | None = None
    for line in draft.splitlines():
        stripped = line.strip().lower()
        if stripped.startswith("## standards"):
            current = "standards"
            continue
        if stripped.startswith("## pitfalls"):
            current = "pitfalls"
            continue
        if stripped.startswith("## exemplars"):
            current = "exemplars"
            continue
        if stripped.startswith("## ") and current:
            current = None  # 进入分歧等其他节
            continue
        if current:
            sections[current] += line + "\n"

    sources = [f.stem for f in files]
    spec = [
        ("standards-gdd", "GDD评审标准", ["standard"], "standards"),
        ("pitfalls-gdd", "GDD反例库", ["pitfall"], "pitfalls"),
        ("exemplars-gdd", "GDD亮点范例", ["exemplar"], "exemplars"),
    ]
    written: list[Path] = []
    for name, title, tags, key in spec:
        body = sections[key].strip()
        if not body:
            continue
        page = wiki.WikiPage(name=name, title=title, tags=tags, sources=sources, body=body)
        wiki.save_page(page)
        written.append(page.path)
    wiki.rebuild_index()
    return written


def run_distill() -> None:
    """蒸馏入口: extract全部 → synthesize → wiki."""
    preflight_llm_check()
    raw_dir = wiki.RAW_DIR
    gdds = sorted(
        p for p in raw_dir.glob("*.md") if not p.name.endswith(".notes.md")
    )
    # 同时接受 .notes 同名约定外的标注文件不进语料
    gdds = [p for p in gdds if not p.with_suffix(".notes").exists() or True]
    if not gdds:
        raise SystemExit(
            f"✗ {raw_dir} 下没有GDD文档。\n"
            "  请把真实GDD(markdown)放入 raw_gdds/ 目录后重试。\n"
            "  可选: 同名 .notes 文件写人工粗标注,格式每行 '3.2节 抽卡: 坏设计,被喷了'"
        )

    print(f"待蒸馏GDD: {len(gdds)} 份")
    extracted_dir = raw_dir.parent / "extracted"
    extracted_dir.mkdir(exist_ok=True)

    for g in gdds:
        print(f"  extract: {g.name} ...")
        extract_one(g, extracted_dir)

    print("  synthesize ...")
    pages = synthesize(extracted_dir)
    print(f"\n✓ 蒸馏完成,生成wiki页面:")
    for p in pages:
        print(f"  - {p.name}")
    print("\n下一步: 人工复核 knowledge_wiki/ 下新页面与 drafts/synthesize_draft.md,")
    print("修正后运行 gdd-review lint 检查知识库健康度。")
