# PROPOSAL · REVISED 2026-10-02 · 仍未整体批准；入口查询部分已于 2026-10-02 实施并测试

**2026-10-02 奇迹位面实施更新（优先）：**用户要求完整解锁、升级及加成链。721–727按官方神格文明数量/大星总和、材料、等级前置和星级上限实施；728仍未开放但下发完整初始状态。离线升级在战斗/派遣属性计算前结算，加成按已有客户端文明技能表。客户端SpeedUpTimes默认5分钟已恢复，271费用为max(0,ceil剩余秒/300-1)，最后五分钟免费；此前待定的建筑光辉加速参数作废。拒绝顾客type2已实施持久化位置轮换且不扣资源。其他草案待定业务不由这些修复自动批准。


**2026-10-02 队列/顾客实施更新（优先）：**用户要求修复训练/派遣未解锁及普通上交失败。训练wire状态0锁/1空/2进行/3完成，派遣0锁/1空/2占用；容量仍受704/705星级约束。训练buildID是CollegeLevel行24401等，不能填建筑704。598普通上交type=1、599 alchemyType=2；真实扣订单材料并按Gold/熟练度售价结算，事务+持久化回执防重。暂保持同一普通顾客订单即时可再交易（每次重新扣料），已询问是否改为每日一次；不擅自加入轮换权重或恢复时点。加价/折价及特殊顾客仍待规则。596星能/光辉制造加速已实现，Energy恢复期从客户端ctor恢复为600秒。

**最新制作实施更正（优先）：**用户本轮要求修复制作，并明确批准每件领取产物增加1点配方经验。594制作、602领取、826一键领取已使用官方完整CollegeRecipe与持久化事务；官方GlobalParamString.Element01–06=1800秒已恢复，不再列入元素未知参数。701星级决定生产槽3–8，顾客固定5位；旧“顾客数随701星级”作废。取消返还、晶石制造加速、元素购买、交易仍未恢复/批准，维持13。具体证据与边界见white_night_planet.md最新节。

**同日升级实施更正（优先）：**旧 `final/*.json` 丢失 repeated int，成本/效果不可继续据此实现。权威数据改用 `src/x2server/data/college_upgrade_catalog.json` 完整向量，701 二级真实成本为 10000 金币+3 材料；前置包括主建筑等级。用户本轮已授权建筑正常升级及效果，普通建筑升级/升星/已恢复官方道具加速已实装，未知水晶计价、被动产出和其他业务参数仍待决策。详见 [本轮审计](../college_upgrade_audit_20261002.md)。

## 白夜行星 / College / GrowthBase 兼容经济草案（2026-09-27 初稿；2026-10-02 按客户端行数据修订）

**修订原则（用户 2026-10-02 决定）：兼容方案与客户端证据相悖时，以客户端为准。**
本版据此废弃与 2.4 静态表行数据冲突的自创规则；其余服务器下发类参数（原架构即如此）仍为 `REVIVAL_COMPATIBILITY`，逐项参数及三个档位见 [`college_compatibility_draft.json`](../../../analysis/white_night_planet/compatibility/college_compatibility_draft.json) 与 [`parameter_review.csv`](../../../analysis/white_night_planet/compatibility/parameter_review.csv)。注意：这两个 JSON/CSV 与 [`simulate_college_economy.py`](../../../analysis/white_night_planet/compatibility/simulate_college_economy.py) 生成于初稿，其中建筑成本/时长部分已被本修订取代，只能继续用作星能子集压力测试。静态行数据级证据（新）：仓库外 `D:/demo/x2/college_tables/final/`（9 张表 + FunctionOpen/Gift 解码行，待迁入 evidence/derived）。

## 官方约束和新增线索（2026-10-02 行数据核实）

| 事实 | 等级 | 经济含义 |
|---|---|---|
| `CollegeBuilding` 16 行：普通 701–708（708 上限 25/5星，其余 30/6星）、奇迹 721–728（35/6星）；**仅 728 泰姬陵缺 `BuildingOpen`**（枚举 E_No/E_Yes，其余全 1）→ 判定未开放 | OFFICIAL_CONSTRAINT | 保留官方初始等级/上限/前置 |
| **升级成本/时长/前置是官方静态值**：完整 CollegeLevel repeated 列表；普通建筑消耗金币/装备经验及材料，前置=账号等级或主建筑等级。701：2级=600s+10000金币+3×1237801；奇迹721：2级=3600s+5×1237801 | OFFICIAL_CONSTRAINT（取代 scalar 导出的“无金币”结论） | 不采用自创金币曲线；建造队列1+1 |
| `CollegeStarLevel` 95 行：升级消耗有值；星级效果=槽位/解锁（704 数量 1–6、707 配方 29210–29319、奇迹技能 26101–26806 等） | OFFICIAL_CONSTRAINT（枚举→玩法映射待消费者确认） | 槽位不再 DEFER，按表实现后再实机核对 |
| `CollegeExplore` live 版（Reward 761001–761015）：`Conditon`=**战力门槛** 300–32000、`PowerConsume` 6–72、`WaitTimes` 3–36h、`Num1/2/3`=三档难度人数 4/6/8、`Exp`=遗迹经验 12–96、效果3链=派遣点逐级解锁。APK 内另有 900301 版本，live 判定需一次实机预览 | OFFICIAL_CONSTRAINT | 派遣时间/消耗/门槛/奖励候选直接可用；服务器产速及随机规则未知 |
| 训练：`L2C_StartTrain` 回 `trainTime/trainEndTime/starEnergy`；客户端 `GetHeroTrainTime/GetHeroTrainExp/GetHeroMaxNum/GetExploreNum/GetEnergyRecovery/GetEnergyMaxEnergy/GetElementSpeed` 全部读 `TableMgr.GetIntGlobalParam` 键 **7/8/6/1/4/5/16**；APK 无数值型 GlobalParam 资源（配合 `LoadWebGameConfig`/`OnServerParamaChange`） | OFFICIAL_CONSTRAINT（架构）+ 数值 SERVER_ONLY | 训练时长/经验、槽位、星能产速/上限、元素恢复=服务器下发参数；Revival 应实现参数通道下发保持 UI 一致；数值仍按本草案 compat 候选 |
| `CollegeRecipe` 60 行全字段有值：RecipeType=991–996（每类 RecipeLevel 1–10 + 逐级 Exp）、材料/产物/数量/等待、`Gold` 2400–25920、`Pay` 5–39 | OFFICIAL_CONSTRAINT（数值）；`Gold`=售价仍为用户兼容决定；`Pay` 语义 UNKNOWN | 配方解锁/经验阈值可直接用静态值 |
| `CollegeCustomer` 42 行：38 神格 + 4 NPC（38201–38204）；**`Like`=单元素偏好 992–996**；**`ChatChance/ChatParam` 全为 0**；`L2C_SingleCustomerInfo(593)` 带 **transactionNum/transactionLastRecoverTime**（顾客交易次数上限+恢复，初稿未覆盖） | OFFICIAL_CONSTRAINT | 初稿“Like 两个偏好类别”“ChatChance 五格 [400,300,0,300,0]”**作废**；交易次数上限需新增兼容参数 |
| `CollegeEquibReset` 5 档：材料含 **1237805/06/07**；行结构（单材料侧）与 anchors 记载的三材料结构不同 | OFFICIAL_CONSTRAINT，以 live 变体重核 | 洗炼成本按 live 行数据实现 |
| 祈祷：完整repeated字段为 `PrayItem=[1237901,1237840]`、`PrayItemNum=[3000,1]`、`PrayWaitTimes=28800s` | OFFICIAL_CONSTRAINT | 旧导出只留末项，“无金币”结论作废；碎片×5仍为用户决定 |
| 建筑加速卡 1237831–1237835（600/3600/7200/14400/28800 秒）；请求 234/367 带 itemId+itemNum；**624 派遣加速无消耗字段** | OFFICIAL_CONSTRAINT | 建筑/祈祷加速用卡；派遣加速计费需决策 |
| 错误码：`GameLogicErrCode` 细分（14 MAX_LEVEL/22 NO_ITEM/27 NO_EQUIP/35 LIMIT_GOLD/38 NO_ENOUGH_POWER 等） | OFFICIAL_CONSTRAINT | 取代“细分不可用则一律 13” |

横向锚点（金币本 2130101–2130105 扫荡约 2078/4678/9356/14552/20788 金币）保留作参照；升级改用官方材料成本后，College 金币净流出大幅低于初稿模拟值。

## 按域设计（修订后）

### A–B 建筑与奇迹升级（官方数据驱动）

- 成本/时长/前置：**使用完整 CollegeLevel/CollegeStarLevel repeated 向量**（金币/装备经验、材料、账号或主建筑等级、WaitTimes）。服务器校验 `LevelLimited/StarLimited/LimitLevel/PreconditionType/Value`。
- 加速：仅接受 1237831–35，扣卡减固定秒数，多余秒数不入账；取消退还原材料（加速卡不退）——维持初稿决定。
- 队列：建造 1+1（wire 证实）；完成/取消/加速错误码用细分枚举。

### C–H 星能、仓库、加速、队列（服务器参数，仍待批准）

维持初稿推荐：产速 2/小时（键4）、上限 96（键5）、离线最多结算 24h；实现时经服务器参数通道下发（客户端 UI 读取同一键位）。派遣/训练槽基值来自键 1/6，星级效果按 CollegeStarLevel 叠加（映射待消费者确认后实装）。

### I–M 派遣、奖励、占用、训练

- 派遣：官方 15 项 WaitTimes/PowerConsume/Reward(761xxx)/Conditon(战力)/Num(人数)；门槛用 `ExploreData.fightCapacity` 对照；奖励只解析指定 Gift 一次（权重合计 1000，需先让发奖器归一化）；取消未发奖前返还 100% 星能。
- 派遣加速 624：客户端无消耗字段 → 兼容决策：候选=免费即时 / 消耗加速卡（需协议核实）/ 消耗星能；实施前标 DEFER。
- 训练：时长=键7（服务器参数）；经验=键8 或用户已决定的“下一级所需 25%”——二者取一登记为 REVIVAL_COMPAT；完成只发一次、取消不发；与派遣共用英雄占用账本（HeroStatus：IDLE/PRAY/EXPLORE/TRAIN）。

### N–Q 炼金与顾客

- 生产：直接用 CollegeRecipe（材料/产物/等待/RecipeLevel/Exp 阈值）；收取与出售分别记账，`Gold` 为基础售价（用户决定），`Pay` 仍 DEFER。
- 顾客订单：顾客按单元素偏好（Like）从对应 RecipeType 抽产物——**替代初稿“两类偏好抽两个不同产物”**；具体生成权重仍 compat（等概率候选）。**新增：**每位顾客维护 transactionNum 与恢复时间（周期 compat 候选：每日重置或 N 小时恢复，需决策）。
- 交互：加价/建议/打折维持用户决定（22/4 星能、×1.2/×0.5、好感+8）；**闲聊：ChatChance/ChatParam 全 0，无静态依据 → 不实现闲聊扣费与奖励**（按钮置灰或回细分错误码），初稿五格数值作废。
- 特殊顾客（4 NPC / E_Superbuy/E_PriceBuff/E_MakeBuff 各 1 行）：映射仍待证据，DEFER。

### R–U 祈祷、洗炼、协助

- 祈祷：官方3000金币+1237840×1+8h；基础奖励所选守护者碎片×5（用户决定），不选守护者时同源流已开放神格等概率抽取（Revival兼容）；献祭一枚碎片收益×2（Language13102257）。二星祈神/三星守护者/四星献祭、每日5次、05:00重置及取消返还祈神符均已按客户端实现。金币与献祭碎片不返还，已用加速卡不退。
- 洗炼：成本按 CollegeEquibReset live 行（含 1237807）；重抽规则维持用户决定（移除选中副词条后按 EquibAttrib 权重池重抽）；日次数与强化加成结转仍待核实/决策。
- 社交协助 879–882：维持 OUT_OF_SCOPE（2026-09-27 用户决定）。

### “收益/结果待定”更正

| 子玩法 | 依据变化 |
|---|---|
| Training | 经验公式=服务器参数键8（官方值缺失）或用户 25% 规则，二选一登记；时长=键7 |
| Alchemy | 配方数值全部官方化；`Pay`、配方外消耗仍未知 |
| Customer | 单元素偏好；新增交易次数机制；闲聊无据、不实现 |
| Pray | 完整官方成本含3000金币；碎片×5为用户决定，献祭双倍为客户端文案约束 |
| Washing | 成本按 live 行数据（含 1237807）；其余维持 |

### V–W 日切、错误与事务

- 日切：维持 UTC+8 00:00 候选（非官方结论）。
- 错误：**优先使用 GameLogicErrCode 细分码**（14/22/27/35/38 等），无对应细分时回 13；不把失败回成功。
- 事务边界：维持 `validate → calculate → debit → mutate → reward/refund → receipt → commit → response` 原子序。

## 模拟与风险（部分过时）

`simulate_college_economy.py` 的 36 组模拟基于初稿自创升级曲线，**建筑成本结论已被官方行数据取代**；星能产速/仓库配平结论（2/h 配平派遣 2/h、96 上限防囤积）仍可参考。实施防线不变：Gift 权重 1000 需归一化、Gift 只掷一次、取消不退加速卡且不发奖、收益凭证唯一、炼金产物先持有后出售。

## 用户审核表（2026-10-02 状态更新）

| # | Domain | Rule | 现状 |
|---|---|---|---|
| 1 | Preset | 总体节奏 | 星能子集仍待确认；建筑曲线已由官方数据取代 |
| 2 | Building/Wonder | ~~金币与材料曲线~~ | **已关闭**：官方 CollegeLevel/StarLevel 行数据 |
| 3 | Star Energy | 产速/仓库/离线 | 待确认（服务器参数键 4/5） |
| 4 | Build Time | ~~普通/奇迹上限~~ | **已关闭**：官方 WaitTimes |
| 5 | Acceleration | 消耗加速卡 | 维持（官方卡 1237831–35）；派遣加速 624 计费待决策 |
| 6 | Cancellation | 退费 | 待确认（原材料 100%/加速卡不退） |
| 7 | Queues | 并发 | 建造 1+1 已证实；派遣/训练槽=键1/6+星级效果 |
| 8 | Explore | 奖励 | 只解析指定 Gift 一次；维持待确认 |
| 9 | Washing | 每日次数 | 待确认；成本行数据待 live 变体重核 |
| 10 | Daily Reset | 结算边界 | 待确认（UTC+8 00:00 候选） |
| 11 | Assist | 社交协助 | 已决定：OUT_OF_SCOPE |
| 12 | Training | 训练经验 | 官方值=键8 缺失；用户 25% 规则与官方键位二选一登记 |
| 13 | Alchemy | `Gold` 字段 | 售价（用户决定）维持；`Pay` 待证据 |
| 14 | Customer | 订单及交互 | **修订**：单元素偏好；闲聊不实现；**新增交易次数上限/恢复参数待决策** |
| 15 | Pray | 祈祷奖励 | 碎片×5维持，完整官方成本含3000金币（更正旧导出丢失列表项）；献祭双倍 |
| 16 | Washing | 词条变化 | 维持；成本行数据更新 |
| 17 | Server Params | 7 键下发 | **新增**：实现服务器参数通道（键 1/4/5/6/7/8/16），数值待批准 |

**未来替换条件：**出现原服非空 584/591/623、玩法报文，或原服参数值被证实（例如原服抓包）时，逐域替换 config/policy；不得把本草案数值回写为官方事实。
