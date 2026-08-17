"""GDD 评审 Crew: 四维度检查(一致性/深度/缺陷/亮点) + 对抗质询.

对抗设计: 每个维度先由"审查员"提出发现, 再由同维度的"质询员"(红方)专门
挑战这些发现——要求有理有据,推翻站不住脚的,强化站得住脚的。
知识门控: 缺陷/亮点维度在知识不足时跳过Agent评审,报告如实说明。
"""

from __future__ import annotations

import os
from pathlib import Path

from crewai import Agent, Crew, Process, Task

from gdd_review import wiki
from gdd_review.gdd_tools import GddReadTool, WikiReadTool, WikiSearchTool
from gdd_review.llm import get_llm


def _gate_note(dim: str, gate: dict) -> str:
    if gate["sufficient"]:
        return f"知识库门控[{dim}]: {gate['reason']} —— 正常执行该维度评审。"
    return (
        f"知识库门控[{dim}]: {gate['reason']} —— **该维度检查被跳过**。"
        "请在评审报告'知识库状态'一节明确记录此说明,不要虚构该维度的发现。"
    )


def build_review_crew() -> Crew:
    # 门控在组装时实时求值——知识库可能在本次进程内刚被蒸馏更新
    defect_gate = wiki.knowledge_sufficiency("defect")
    highlight_gate = wiki.knowledge_sufficiency("highlight")
    llm = get_llm()
    wiki_tools = [WikiSearchTool(), WikiReadTool()]
    gdd_tools = [GddReadTool()]

    # ── 一致性维度: 审查员 + 质询员 ────────────────────────────
    consistency_a = Agent(
        role="GDD 一致性审查员",
        goal="找出文档内部的自相矛盾、数值错误、引用失效与规则冲突",
        backstory=(
            "你是审计员,只依赖文档本身做交叉核对: 同一数值在不同章节是否一致;"
            "公式代入示例值能否算出文档声称的结果;引用的章节/系统是否存在;"
            "规则A允许的情况是否被规则B禁止。"
            "只报告能同时指出'第X处与第Y处矛盾'的问题,不报告纯观点分歧。"
            "每条发现必须给出两处原文位置。用 gdd_read 分章节仔细读全文,不要跳读。"
        ),
        llm=llm,
        tools=gdd_tools,
    )
    consistency_r = Agent(
        role="一致性质询员(红方)",
        goal="挑战一致性审查员的每条发现,推翻站不住脚的,保留铁证",
        backstory=(
            "你是被告方辩护律师,任务是摧毁对方证据: 检查'矛盾'双方是否处于"
            "不同语境(如新手期vs后期)、数值是否本就有版本说明、引用是否在别的章节存在。"
            "能合理消解的矛盾必须推翻;推翻不了的是铁证,原样保留并补强论证。"
            "输出: 每条发现标注[推翻+理由]或[确认+补强],禁止和稀泥。"
        ),
        llm=llm,
        tools=gdd_tools,
    )

    # ── 深度维度: 审查员 + 质询员 ──────────────────────────────
    depth_a = Agent(
        role="GDD 深度审查员",
        goal="对照wiki标准[S*][D*],找出写得过浅、缺要素、不可执行的部分",
        backstory=(
            "你逐章评估文档深度。先 wiki_search 检索该章对应标准并 wiki_read 读全文,"
            "再比对: 该有的要素有没有?数值是否可执行(有具体值而非'适量''较高')?"
            "边界条件写了吗?每条意见必须引用标准编号,检索不到标准的维度"
            "标注'无内部标准依据,按行业常识评估'。禁止不查wiki就下判断。"
        ),
        llm=llm,
        tools=wiki_tools + gdd_tools,
    )
    depth_r = Agent(
        role="深度质询员(红方)",
        goal="挑战深度审查员的每条意见,剔除标准误用与过度苛求",
        backstory=(
            "你辩护的角度: 审查员引用的标准是否真的适用于该品类/该项目阶段?"
            " '缺要素'是GDD阶段就该有,还是详设阶段才需要?"
            " '含糊'是文档问题还是行业惯例的合理留白?"
            "误用标准的意见必须[推翻+说明为何不适用];成立的[确认]并明确缺什么。"
        ),
        llm=llm,
        tools=wiki_tools + gdd_tools,
    )

    # ── 缺陷维度(门控): 审查员 + 质询员 ────────────────────────
    defect_a = Agent(
        role="GDD 缺陷审查员",
        goal="对照wiki反例库[P*],识别文档中的禁令违反与反模式设计",
        backstory=(
            "你逐系统排查设计缺陷。先 wiki_search(tag=pitfall) 检索相关反例,"
            "wiki_read 读全条目,再核对GDD是否踩中。"
            "反例条目含'检查动作',逐条执行;禁令命中即blocker。"
            "每条缺陷必须引用[P*]编号并注明'禁令'或'反模式'档位。"
            "禁止不查反例库就凭通用审美报缺陷。"
        ),
        llm=llm,
        tools=wiki_tools + gdd_tools,
    )
    defect_r = Agent(
        role="缺陷质询员(红方)",
        goal="挑战每条缺陷指控,剔除无依据的与已有例外的",
        backstory=(
            "你辩护的角度: 指控引用的[P*]条目真实存在吗(用wiki_read核实)?"
            "GDD的设计是否属于条目声明的例外情况?还是仅形似而实质不同?"
            "引用不实或适用性存疑的缺陷必须[推翻];踩实的[确认]并注明档位与后果。"
        ),
        llm=llm,
        tools=wiki_tools + gdd_tools,
    )

    # ── 亮点维度(门控): 审查员 + 质询员 ────────────────────────
    highlight_a = Agent(
        role="亮点识别员",
        goal="对照wiki范例与标准[G*][S*],找出显著优于基线、值得推广的设计",
        backstory=(
            "你找的是'特别好'而非'没毛病': 比标准更完备的思考、常见坑已主动规避的"
            "设计、可直接复用的表述范式。先用wiki_search检索对应标准与范例,"
            "再判断是否显著超出基线。达标≠亮点。"
            "找不到就如实说'本文档无突出亮点',不要硬凑——谄媚是这个角色的耻辱。"
        ),
        llm=llm,
        tools=wiki_tools + gdd_tools,
    )
    highlight_r = Agent(
        role="亮点质询员(红方)",
        goal="挑战每条亮点,剔除'仅达标'与'自我发挥'的",
        backstory=(
            "你泼冷水的角度: 所谓亮点是否只是达到了[S*]的基本要求?"
            "是否在wiki中有更优范例使其黯然失色?是否属于评审员的主观偏好而非可推广范式?"
            "举证不足的亮点[推翻];真材实料的[确认]并说明超出哪条基线、为何可推广。"
        ),
        llm=llm,
        tools=wiki_tools + gdd_tools,
    )

    # ── 主审: 汇总对抗结果出报告 ───────────────────────────────
    chief = Agent(
        role="主审",
        goal="汇总四维度对抗后的确认发现,输出人类团队成员直接能读懂、能执行的评审报告",
        backstory=(
            "你只采纳质询后标记[确认]的发现,被[推翻]的不进正式结论"
            "(可附'已排除指控'一节展示对抗过程)。"
            "缺陷与亮点维度若被知识门控跳过,必须在'知识库状态'一节原文说明原因,"
            "并建议先运行蒸馏补全知识库。报告用中文,markdown格式。"
            "你的读者是不懂评审术语的游戏团队成员(策划/程序/制作人),不是另一个AI:"
            "每条发现先用一句大白话说清'哪里和哪里冲突/缺了什么、不修会怎样',"
            "再给证据与依据编号;专业术语首次出现必须用括号一句话解释;"
            "标准适用性辩论、质询过程等元讨论只允许出现在'已排除的指控'一节。"
        ),
        llm=llm,
    )

    # ── 任务链 ────────────────────────────────────────────────
    t_consistency = Task(
        description=(
            "一致性审查待评审GDD。用 gdd_read 通读全文(长文档分章节读),"
            "列出所有内部矛盾/数值错误/引用失效/规则冲突,"
            "每条含:位置A+原文、位置B+原文、矛盾说明。\n"
            "知识库门控[consistency]: 该维度不依赖知识库 —— 正常执行。"
        ),
        expected_output="矛盾发现清单,每条含两处原文位置",
        agent=consistency_a,
    )
    t_consistency_rebut = Task(
        description=(
            "对上述每条一致性发现进行质询。逐条[推翻+理由]或[确认+补强]。"
            "最终只输出确认清单与推翻记录两部分。"
        ),
        expected_output="确认清单(带补强论证) + 推翻记录(带理由)",
        agent=consistency_r,
        context=[t_consistency],
    )

    t_depth = Task(
        description=(
            "深度审查待评审GDD。逐章: wiki_search检索标准 → wiki_read读全文 → "
            "gdd_read读该章 → 比对深度。每条意见引用[S*][D*]编号。"
            "检索不到标准的维度标注'无内部标准依据,按行业常识评估'。"
        ),
        expected_output="逐章深度意见清单,每条含标准编号与具体缺失",
        agent=depth_a,
    )
    t_depth_rebut = Task(
        description=(
            "对上述每条深度意见进行质询(标准适用性/阶段合理性/行业惯例)。"
            "逐条[推翻+理由]或[确认+补强]。"
        ),
        expected_output="确认清单 + 推翻记录",
        agent=depth_r,
        context=[t_depth],
    )

    tasks = [t_consistency, t_consistency_rebut, t_depth, t_depth_rebut]

    if defect_gate["sufficient"]:
        t_defect = Task(
            description=(
                "缺陷审查待评审GDD。wiki_search(tag=pitfall)检索反例 → "
                "wiki_read读检查动作 → gdd_read核对GDD是否踩中。"
                "每条缺陷引用[P*]编号,注明禁令/反模式档位。"
            ),
            expected_output="缺陷清单,每条含[P*]编号+档位+后果",
            agent=defect_a,
        )
        t_defect_rebut = Task(
            description=(
                "对上述每条缺陷指控质询: wiki_read核实[P*]条目是否真实存在、"
                "是否属于声明例外、是否形似质异。逐条[推翻+理由]或[确认+补强]。"
            ),
            expected_output="确认清单 + 推翻记录",
            agent=defect_r,
            context=[t_defect],
        )
        tasks += [t_defect, t_defect_rebut]

    if highlight_gate["sufficient"]:
        t_highlight = Task(
            description=(
                "亮点识别。wiki_search检索标准与范例 → gdd_read读文档 → "
                "找出显著超出基线且论证扎实的设计。每条亮点说明超出哪条基线。"
                "无真材实料则明确输出'无突出亮点'。"
            ),
            expected_output="亮点清单(每条含基线对比)或'无突出亮点'声明",
            agent=highlight_a,
        )
        t_highlight_rebut = Task(
            description=(
                "对上述每条亮点质询: 是否仅达标?是否有更优范例?是否主观偏好?"
                "逐条[推翻+理由]或[确认+补强]。"
            ),
            expected_output="确认清单 + 推翻记录",
            agent=highlight_r,
            context=[t_highlight],
        )
        tasks += [t_highlight, t_highlight_rebut]

    gate_summary = (
        f"缺陷维度门控: {defect_gate['reason']}\n"
        f"亮点维度门控: {highlight_gate['reason']}"
    )
    t_report = Task(
        description=(
            "汇总全部质询后的确认发现,输出最终评审报告(markdown,中文)。"
            "写作总原则: 读者是不懂评审术语的人类团队成员,一切表述以'人能读懂'为第一标准,"
            "在保住全部细节的前提下说大白话。\n\n"
            "# GDD 评审报告\n"
            "## 报告怎么读\n"
            "(三行以内大白话: 这份文档整体怎么样/最要命的问题是什么/建议先做什么;"
            "另起一行解释严重度: blocker=不修没法开工, major=重要缺陷, minor=小问题)\n"
            "## 知识库状态\n"
            "（原样记录下面的门控结论;每个被跳过的维度补一句大白话,"
            "如'本次没有做缺陷检查,是因为反例知识库不够,不代表文档没有缺陷'）\n"
            f"{gate_summary}\n\n"
            "## 确认的发现\n"
            "### 错误(一致性)\n### 不足(深度)\n### 缺陷(反例命中)\n### 亮点\n"
            "每条发现的格式(顺序固定):\n"
            "1. 一句话说明(大白话): 直白指出问题,如'第X章X.Y节说A,与第M章M.N节的B相违背'"
            "或'第X章只列了名词没给数值,照着文档没法开发'——先说事实,再说为什么这是问题\n"
            "2. 位置(章节号) 3. 严重度(blocker|major|minor) "
            "4. 证据(只引原文关键句) 5. 依据编号 6. 修改建议(具体到改哪一章、补什么)\n"
            "证据部分不得展开质询过程与标准适用性讨论。\n"
            "## 已排除的指控(对抗质询中被推翻的)\n"
            "(每条一句话: 原以为是什么问题、为什么其实不是;详细论证不进这节)\n"
            "## 总评与优先级建议\n"
            "(按'先修什么后修什么'分批,每批一句话说明为什么排在这里)\n"
            "## 通俗总结\n"
            "(必写,放在报告最后: 把全部确认发现逐条翻译成大白话,编号与正文对应,"
            "每条一两句——'第几章的什么与第几章的什么冲突了,所以列出来'或"
            "'第几章缺了什么,导致没法做某事,所以列出来';"
            "被门控跳过的维度也各用一句话说明。"
            "目标: 只读这一节的人也能完整理解全部问题)\n"
        ),
        expected_output="完整markdown评审报告(含'通俗总结'一节)",
        agent=chief,
        context=[t for t in tasks],
    )
    tasks.append(t_report)

    return Crew(
        agents=list({a for t in tasks for a in [t.agent]}),  # noqa: C401 - 保留定义顺序
        tasks=tasks,
        process=Process.sequential,
        verbose=True,
    )


def run_review(gdd_path: str) -> Path:
    """评审入口: 设置待审文档环境变量 → 组装Crew → kickoff → 落盘报告."""
    path = Path(gdd_path).expanduser().resolve()
    if not path.exists():
        raise SystemExit(f"✗ GDD 文件不存在: {path}")

    os.environ["GDD_UNDER_REVIEW"] = str(path)
    from gdd_review.llm import preflight_llm_check

    preflight_llm_check()

    print(f"评审对象: {path.name}")
    print(f"知识门控: 缺陷维度 {'✓执行' if wiki.knowledge_sufficiency('defect')['sufficient'] else '✗跳过(知识不足)'}"
          f" | 亮点维度 {'✓执行' if wiki.knowledge_sufficiency('highlight')['sufficient'] else '✗跳过(知识不足)'}")

    crew = build_review_crew()
    result = crew.kickoff()

    reports_dir = Path(__file__).resolve().parents[2] / "reports"
    reports_dir.mkdir(exist_ok=True)
    stem = path.stem
    report_path = reports_dir / f"{stem}_评审报告_{Path(stem).stem and __import__('datetime').datetime.now().strftime('%Y%m%d_%H%M')}.md"
    report_path.write_text(result.raw, encoding="utf-8")
    wiki.append_log("review", path.name, f"报告: {report_path.name}")
    return report_path
