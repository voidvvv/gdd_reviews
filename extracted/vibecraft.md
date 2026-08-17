# VibeCraft GDD 事实盘点

## 基本信息
- **品类：** Real-Time Strategy / RPG Hybrid(实时战略+角色扮演混合)；目标分级 E10+;平台 PC(Windows / macOS / Linux)
- **引擎：** 自研 Elixir/OTP + OpenGL 3.3(经 SDL2 NIF),音频 SDL2_mixer,网络原生 TCP
- **预估规模(文档内可盘点的内容量)：** 2 阵营；10 种单位(4 地面 + 4 海军 + 2 空军)；2 英雄；4 法术；6 商店物品 + 1 条合成配方；2 建筑；5 种地块；5 种回放事件；27 个引擎模块；路线图 5 阶段(Phase 0–3 标记 ✓ Complete,Phase 4 标记 In Progress);开发定位为 "a small team on the BEAM"(具体团队人数未写)
- **总章节数：** 18 个编号章节 + 1 个附录 = 19 节
- **总字数级：** 约 3000 英文词量级(正文与 Markdown 表格混合，表格占比高)

## 章节清单

| 章节 | 包含要素(属性表/公式/流程说明/数值示例/边界条件) | 厚实还是单薄 |
|---|---|---|
| 1. Executive Summary | 纯概述文字 + 4 条差异点列表，无表格无数值 | 单薄 |
| 2. Vision & Design Pillars | 5 条设计支柱表(全定性描述，无数值) | 单薄 |
| 3. Core Gameplay Loop | 流程说明(循环图 + Gather→Expand 6 步)、胜利条件 1 条、tick 模拟一句话说明 | 单薄 |
| 4. Factions | 定性文字(两阵营各自优劣势描述) | 单薄 |
| 5. Units | 属性表 ×3(地面含 HP/攻击/视野/金/木/训练 tick;海军、空军仅 HP/攻击/视野)、采集数值示例(每趟 10 金/10 木)、移动边界条件(1 格/tick、基本方向) | 厚实 |
| 6. Buildings & Economy | 属性表 ×2(建筑 HP 与可训练单位；资源初始量)、训练队列边界条件(FIFO 上限 5) | 中等 |
| 7. Heroes & RPG Progression | 英雄属性表(HP/攻击/法力/视野)、升级数值示例(每级 +50HP/+2攻/+25法力，上限 9 级，满级 600/30/425) | 中等偏厚 |
| 8. Spells & Abilities | 法术属性表 ×4(法力消耗 + 效果数值) | 中等 |
| 9. Inventory, Loot & Crafting | 商店物品属性表(6 件含定价)、合成配方表(1 条)、掉落定性描述 | 中等 |
| 10. Map, Terrain & Environment | 地块类型表(通行性/资源)、昼夜相位表(600 ticks + 百分比区间)、高度图数值(0.0–1.0) | 厚实 |
| 11. Fog of War | 3 态迷雾表、视野数值(Manhattan 距离，地面 4 格、海军/空军/英雄 5–6 格) | 中等 |
| 12. Campaign & Missions | 任务 DSL 字段列表、英雄跨关持久化说明、编辑器功能列表，无示例代码无任务数量 | 单薄 |
| 13. Multiplayer | 协议细节(4 字节长度前缀、默认端口 4001)、Elo 参数表(1200/32/300)、5 段位区间表 | 厚实 |
| 14. AI Opponents | 4 条规则流程列表 + 未来迭代说明，无参数数值 | 单薄 |
| 15. Replay System | 回放事件表(5 种事件 + 数据字段)、变速回放一句话 | 中等 |
| 16. Audio & Visual Style | 定性描述(16×16 像素、SVG 源、SDL2_mixer),无曲目数/时长数值 | 单薄 |
| 17. Technical Architecture | 技术栈表、Why Elixir 4 条说明、27 模块完整模块图 | 厚实 |
| 18. Development Roadmap | 5 阶段表(目标 + 状态)，无日期无工期 | 单薄 |
| 附录 Comparable Titles | 定性对标描述 | 单薄 |

## 关键设计决策(带数值和章节号)

- [移动系统] 所有单位占 1 格，每 tick 沿基本方向(N/S/E/W)移动 1 格 — 依据：第 5 章
- [地面兵种数值] Footman 60HP/6 攻/135 金/60 tick vs Grunt 60HP/8 攻/100 金/60 tick;Peasant 与 Peon 完全相同(30HP/3 攻/75 金/45 tick) — 依据：第 5 章
- [采集产出] 工人每趟产出 10 金或 10 木，存入最近 Town Hall — 依据：第 5 章
- [建筑训练队列] 单建筑 FIFO 队列上限 5 项，仅队首倒计时，完成单位在相邻空格出生 — 依据：第 6 章
- [建筑数值] Town Hall 1200HP(训练工人)、Barracks 800HP(训练步兵) — 依据：第 6 章
- [初始经济] 金 500 / 木 200,两阵营共用 — 依据：第 6 章
- [英雄成长] 每级 +50HP / +2 攻击 / +25 法力，等级上限 9;满级 Paladin 600HP / 30 攻 / 425 法力 — 依据：第 7 章
- [法术数值] Holy Light 65 蓝回 200HP;Resurrect 100 蓝；Death Coil 50 蓝 100 伤；Animate Dead 100 蓝 — 依据：第 8 章
- [背包] 英雄物品栏上限 6 件 — 依据：第 9 章
- [商店定价] 药水 50/75/150 金，装备 200/200/400 金；唯一合成配方：Sword of Light + Shield of Iron → Ring of Power — 依据：第 9 章
- [昼夜循环] 600 ticks 一循环；相位区间 Dawn 0–24% / Day 25–74% / Dusk 75–87% / Night 88–99% — 依据：第 10 章
- [地形] 逻辑层 2D 格网 + 视觉层连续高度图(0.0–1.0)+ 自动法线 — 依据：第 10 章
- [视野规则] Manhattan 距离；多数地面单位 4 格，海军/空军/英雄 5–6 格 — 依据：第 11 章
- [迷雾状态机] Hidden / Explored / Visible 三态 — 依据：第 11 章
- [网络协议] TCP 客户端/服务器，4 字节长度前缀二进制帧承载 Erlang 编码 term,GenServer 默认端口 4001 — 依据：第 13 章
- [天梯参数] Elo 初始 1200、K 因子 32、最大匹配分差 300;5 段位(Bronze<1300 / Silver 1300–1499 / Gold 1500–1699 / Platinum 1700–1899 / Diamond≥1900) — 依据：第 13 章
- [胜利条件] 歼灭所有敌方单位与建筑(全文仅此 1 条) — 依据：第 3 章
- [模拟模型] 确定性 tick 模拟，每 tick 同时推进移动/战斗/训练队列/法力回复/昼夜 — 依据：第 3 章
- [美术规格] 全部原创 16×16 像素画，源文件为 SVG,构建期栅格化 — 依据：第 16 章
- [AI 行为] 4 条固定规则：经济(练工人采集)→军事(有资源练 Grunt)→进攻(向最近已知敌位移动)→战斗(攻击相邻敌人) — 依据：第 14 章

## 人工标注(评审人的真实判断，优先级最高，展开时不得违背)

(无人工标注——仅做事实盘点，判断留给 synthesize 阶段结合其他文档)

## 含糊或缺失的部分(只描述现象)

- **XP 阈值无任何数值**：第 7 章仅写 "XP thresholds increase with each level",未给出任一等级的具体门槛
- **法力回复速率无数值**：第 7 章 "Mana regenerates passively over time",无每 tick/每秒回复量
- **海军/空军单位缺造价与训练时间**：第 5 章两张表无 Gold/Lumber/Train 列(仅地面单位表有)
- **建筑无造价/建造时间/科技前置**：第 6 章建筑表仅含 HP 与可训练单位两列；第 5 章 "Workers can also construct buildings (planned)" 标注为未实现
- **经济系统无产出/回收汇总**：无采集速率表、无金矿/树木储量与枯竭规则；Gold Mine 作为地块类型存在(第 10 章)但无储量定义
- **物品效果全部无数值**：Health Potion "Restore HP"、Sword of Light "Increase Attack"、Elixir of Speed "Increase Movement Speed" 等均无具体回复量/加成数值 — 第 9 章
- **掉落系统无掉率表**：第 9 章仅一句 "may drop random items",无掉落权重、无宝物表
- **合成系统仅 1 条配方**：第 9 章配方表只有 Sword+Shield→Ring 一行，无配方树扩展
- **Defense 属性无定义**：Shield of Iron / Ring of Power 效果写 "Increase Defense"(第 9 章)，但单位属性表(第 5 章)无 Defense 列，全文无防御/伤害计算公式
- **攻击无攻速/冷却/DPS 定义**：第 5 章仅 Attack 单值，无攻击间隔；Elixir of Speed 提升移速但移动规则固定为 1 格/tick,无移速属性列 — 第 5/9 章
- **石油资源出现单位但未入经济表**：海军单位 Oil Tanker(第 5 章)存在，但第 6 章资源表仅定义金/木两种
- **Transport 装载上限未定义** — 第 5 章
- **复活类法术无细则**：Resurrect / Animate Dead 复活单位的属性、存在时长、可复活时限均未定义 — 第 8 章
- **战役任务数量/章节数/剧情量未说明**：第 12 章仅给出 DSL 字段名，无示例代码、无任务清单
- **AI 无难度分级参数、无行为阈值数值** — 第 14 章(自述 "Future iterations will add difficulty levels")
- **回放无文件格式/存储规格说明** — 第 15 章
- **多人房间人数上限、对战地图尺寸、tick 率(ticks/秒)均未说明** — 第 13 章(第 3 章定义 tick 但无速率)
- **夜晚视野缩减无具体数值**：第 10 章 "reduced visibility" 为定性描述
- **音频无曲目数/时长/文件格式规格** — 第 16 章
- **路线图无日期/工期/人力配置**：第 18 章 5 阶段仅目标 + 状态两列
- **第 4 章阵营优劣势为纯定性文字**(“Lower raw damage output” 等)，数值支撑仅 Grunt 攻击力一项落在第 5 章
- **地图默认尺寸未说明**：第 10 章只写 "2-D tile grid",无格数规格