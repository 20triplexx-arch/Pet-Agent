# 知识库维护与本轮扩充

更新日期：2026-10-13（Asia/Shanghai）。资料文件是随源码交付的编辑内容，不依赖外部模型或实时网络搜索。

2026-10-19新增[资料入库、切分与检索规范](KNOWLEDGE_INGESTION.md)及[编辑模板](templates/knowledge-evidence.md)。95篇分类、来源编辑核对、结构化证据块和检索改造已形成隔离候选；实际质量、速度及发布门槛见[实施与验收记录](EVIDENCE_REBUILD.md)，不把离线检索改善直接当作真实提速。

分类先按[资料分类规范](KNOWLEDGE_TAXONOMY.md)执行：先分公共知识、厂家事实、私有记录和实时服务，再用“物种 → 通用照护/品种/食物/用品”与阶段、条件、地域、用途等独立标签组织。候选已完成95篇批量分类和独立证据索引，尚未导入实际业务库或切换运行版。

## 实施前运行版覆盖（2026-10-13）

当前95篇独立文章、正文55406字符（JSON body长度，不等同汉字计数），最短365、最长992，猫狗各可用64篇。分类为通用照护49、品种24、食物12、用品10。保留原44个ID，2026-10-11新增45篇；2026-10-12补深11篇旧文章；2026-10-13新增6篇复盘/记录/低压力护理等指南、补深3篇旧文，没有增加重复ID。食品储存复用原 `food-storage` 补深并归入食物；选购资料聚焦厂家、分析上下限和适配比较。

首批8猫品种：英短、美短、布偶、暹罗、缅因、波斯、异短、苏格兰折耳；12犬品种：金毛、拉布拉多、贵宾、比熊、博美、柴犬、彭布罗克柯基、边牧、哈士奇、萨摩耶、法斗、巴哥。另设家猫、中华田园犬、混种猫/犬，明确非注册品种性质。各指南包含名称误区、个体差异、生活/互动、毛发护理、健康观察、食物/用品、时间预算及清单。品种标准来自CFA/AKC，健康另据专业资料，具体来源支持范围在每篇 `references` 中记录。

食物12主题：完整/补充性、阶段、标签、热量、干湿粮、零食、冻干/生食、谷物/过敏、自制/补充剂、换粮、储存、预算。用品10类：食水器具、猫砂/砂盆、航空箱/笼箱、窝垫、抓挠攀爬、互动/啃咬玩具、牵引/胸背、梳洗、口腔、环境清洁。选择条件、维护、替换风险及持续成本均有操作要点；不按品牌、配料排序、价格或营销词作整体质量结论。

下表保留2026-10-10原44篇的主题统计；新增条目与多来源见 [SOURCE_CATALOG.md](SOURCE_CATALOG.md)，产品流程及接口见 [PRODUCT_KNOWLEDGE.md](PRODUCT_KNOWLEDGE.md)。

| 主题 | 篇数 |
| --- | ---: |
| 养宠前准备 | 3 |
| 新宠到家 | 3 |
| 饮食与体重 | 8 |
| 居住与清洁 | 6 |
| 互动与训练 | 6 |
| 生命阶段 | 5 |
| 误区与危险 | 3 |
| 健康与就医 | 10 |

新增专篇涵盖多猫介绍、抓挠、互动信号、梳毛、口腔、疫苗资料、拒食与呕吐观察、航空箱适应、幼犬如厕与社会化、笼箱、独处压力、成长训练、季节照护、食品储存和出行。原有营养篇补全单位换算、适用条件、食物分配、零食、体况与肌肉风险、标签解读和就医资料准备。

## 如何组织一篇有用的资料

每篇至少包含适用条件、实际步骤或观察清单、应记录的信息、误区或专业评估边界。专业事实基于下表公开资料，应用任务与记录清单为本项目原创整理；这些操作清单不是原机构正式逐字译文，也没有获原机构背书。

正文支持 `## 标题`、空行分段、`1. `形式的顺序步骤。前端以React文本节点渲染h2、p和ol，避免将知识正文作为HTML执行；其他Markdown功能未实现。列表只展示首段摘要，详情保留全部章节与来源卡。切换宠物后列表物种随之切换，仍允许用户手选猫狗查询。

实施前检索使用本地词典最长匹配、中文二元词及同义词扩展，按整篇文章做BM25排序，再按章节匹配，保留物种/阶段/主题/品种/分类筛选。关键词直接匹配优先，泛化的“宠物”不单独构成有效匹配。当时每个子问题先取最多三篇并筛选，按排名交错合并，独立文章数上限为max(6, 子问题数)；来源ID、相关章节和子问题关联保留。这些数字不是新规范的最优参数结论。候选现对受管理公共资料采用块BM25、问题映射和显式必选依赖，不自动附带首节与全部边界章节；自定义资料保留兼容路径。实际质量、限制与未启用状态以实施报告为准。KeywordRetriever别名保持兼容，检索协议保留向量实现接口。

演示模式按深度提供结论、相关章节步骤、本地数值和最重要的缺失信息，不再套用420/220字符的固定摘录限制。真实模型取得相同证据并组织分析，引用只允许当前检索条目及真实章节；前端章节点进知识详情。紧急规则在检索和模型调用前执行。没有实时联网问答或向量数据库。接口、会话资料及摘要边界见 [DEEP_CHAT.md](DEEP_CHAT.md)。

## 2026-10-12 十类专题补深

| 专题 | 保留的文章ID | 新增内容重点 |
| --- | --- | --- |
| 新宠适应 | cat-home、dog-home | 原习惯、安全区域、按反应推进、可比较的观察 |
| 食品标签 | food-labels | 配方身份、适用声明、上下限、厂家问题和预算条件 |
| 营养与体重观察 | nutrition-energy | 记录日期、体况与肌肉、估算条件、复评而非自动改量 |
| 换粮 | food-transition | 换粮原因、变量控制、耐受与拒食观察 |
| 抓挠与啃咬 | cat-scratching、dog-home | 替代设施、监督、环境调整与记录 |
| 独处 | dog-alone | 录像、时间线、触发条件、减少超出耐受的离开 |
| 多宠相处 | cat-multi | 分区资源、气味与接触递进、停止条件 |
| 口腔护理 | dog-dental | 可观察表现、工具适配、合作步骤与专业检查 |
| 异常观察 | cat-appetite | 实际吃下量、伴随表现、时间线、及时联系兽医 |
| 就医准备 | visit-preparation | 有日期的事实、专业要求、包装与检查问题 |

`backend/scripts/deepen_knowledge.py`为可重复执行的原创编辑补充脚本，不联网、不调用模型。来源支持范围在各条references；checked_at仅对本次实际打开核对的AAHA、Cornell、WSAVA、AVMA和FelineVMA资料更新。cat-home历史PMC主链接本次遭遇验证码，未宣称重新核对；新增实际查阅的FelineVMA介绍指南作为适应与分隔接触依据。不要将收录日期、核对日期写成原文发表日期，也不要把旧来源全部改为当天已验证。

## 审核与地域边界

所有条目均为 `editorial_summary_unreviewed`，只作编辑核对，不是“兽医已审核”。原文发布时间与版本分开记录，页面未标发布日期则保持published_at为空；本轮核对日期不是原文发布日期。来源较旧的行为资料只采用环境改善、身体观察和非惩罚互动要点，不照抄喷水、惊吓等旧建议；训练方式结合AVSAB的奖励式训练立场：[专业立场声明](https://avsab.org/resources/position-statements/)。

疫苗、幼犬社会化、出行篇只整理一般原则和专业沟通清单，不将美国产品、接种程序或法规当作中国要求。猫生病篇不以“等满若干小时”作统一安全门槛，不作诊断、不催吐、不强制喂食、不提供药物剂量。食品与护理频率根据标签、实际情况与个体专业要求判断，不添加未经依据的统一数值。猫狗营养计算规则与风险门控未因本轮内容扩充而改变。

资料范围仍不是完整百科；体况评估与疾病、行为个案需要专业支持。兔、豚鼠、具体仓鼠、鸟、龟、鱼的专属资料与规则尚未上线，不能套用本库猫狗内容。后续扩展需独立完成专业来源核对、具体物种能力登记、适用条件和代表性检索验收。

## 导入与保存已有数据

五个JSON文件按稳定ID进行upsert：`knowledge.json`（16篇）、`knowledge_nutrition.json`（8篇）、`knowledge_care.json`（26篇，含复用的食品储存及6篇照护反馈指南）、`knowledge_breeds.json`（24篇）、`knowledge_products.json`（21篇）。初始化先执行增量迁移并登记24个品种，再导入全部五份；重复执行不重复创建，已有收藏ID保留。本批结构迁移 `20261011_products` 保留已有账户、档案、记录、会话、计划、打卡及收藏。

```powershell
cd backend
../.venv/Scripts/python.exe -m scripts.init_db
# 单独更新照护扩展资料
../.venv/Scripts/python.exe -m scripts.import_knowledge data/knowledge_care.json
```

新内容导入仍校验字段、HTTPS来源、具体物种和审核状态；整批验证后提交。开发者应在导入前逐篇检查来源有效性与正文内容，不能把字段校验或篇幅测试当作专业审核。运行中的服务若修改了Agent源码需重启；已有库、签名密钥与环境配置应保留。

2026-10-11原目录导入前通过 `python -m scripts.backup_migrate` 使用SQLite backup API备份，并单独保留密钥；目录 `backend/storage/backups/20261011-160309-products/`。该次导入后知识44→89，24个品种；14张既有业务表按原列逐行比较一致，密钥未改变，外键检查通过。2026-10-10历史备份也仍保留。2026-10-12仅在当前worktree独立示例库导入89篇最新内容，未改原目录库。备份、密钥和本机数据库不进源码包。升级已有运行服务前停止目标服务，执行备份/迁移后重新启动。

## 逐条专业来源清单

下表链接为实际核对的公开来源。内容不复制整篇文章、受保护图片或图表。没有日期的条目不推测；来源更新仍需后续编辑维护。

| 条目ID | 物种 | 主题 | 正文题目与原始专业资料 | 版本记录 |
| --- | --- | --- | --- | --- |
| cat-prepare | 猫 | 养宠前准备 | [养猫前：先评估生活和预算](https://www.merckvetmanual.com/cat-owners/selecting-and-providing-a-home-for-a-cat/selecting-a-cat) | July 2025 / v102055183 |
| dog-prepare | 狗 | 养宠前准备 | [养狗前：留出每天的照护时间](https://avma.org/resources/pet-owners/petcare/selecting-pet-dog) | 网页收录版本 |
| cat-home | 猫 | 新宠到家 | [新猫到家：提供安全的退避空间](https://pmc.ncbi.nlm.nih.gov/articles/PMC11383066/) | 2013 环境需求指南 |
| dog-home | 狗 | 新宠到家 | [幼犬到家：安全空间与一致的规则](https://www.aaha.org/resources/what-to-do-before-you-bring-home-a-new-puppy/) | 网页 2026-06-05 |
| cat-food | 猫 | 饮食与体重 | [猫的饮食：先看生命阶段与体况](https://www.vet.cornell.edu/departments-centers-and-institutes/cornell-feline-health-center/health-information/feline-health-topics/feeding-your-cat) | 网页更新 2026-04-30 |
| dog-food | 狗 | 饮食与体重 | [犬的饮食与体重：根据个体调整](https://www.aaha.org/resources/2021-aaha-nutrition-and-weight-management-guidelines/feeding-plans-for-healthy-appropriate-weight-cats-and-dogs/) | 2021 营养与体重管理指南 |
| cat-clean | 猫 | 居住与清洁 | [猫砂与清洁：观察排泄的日常窗口](https://www.vet.cornell.edu/departments-centers-and-institutes/cornell-feline-health-center/health-information/feline-health-topics/feline-lower-urinary-tract-disease) | 网页更新 October 2016 |
| dog-clean | 狗 | 居住与清洁 | [犬的居住环境与日常状态观察](https://www.aaha.org/resources/life-stage-canine-2019/life-stage-checklist/) | 2019 犬生命阶段检查清单 |
| cat-play | 猫 | 互动与训练 | [猫的互动：保留捕猎与探索机会](https://pmc.ncbi.nlm.nih.gov/articles/PMC11383066/) | 2013 环境需求指南 |
| dog-play | 狗 | 互动与训练 | [犬的活动：配合年龄和健康状态](https://www.aaha.org/resources/life-stage-canine-2019/life-stage-checklist/) | 2019 犬生命阶段检查清单 |
| cat-stage | 猫 | 生命阶段 | [老年猫：按状态调整照护](https://www.vet.cornell.edu/sites/default/files/WhatToExpect_Updated_2022.pdf) | 2022 What to Expect |
| dog-stage | 狗 | 生命阶段 | [犬的生命阶段与预防护理准备](https://www.aaha.org/resources/how-often-should-my-dog-go-to-the-vet-a-dog-life-stage-guide/) | 网页 2025-06-18 |
| cat-lily | 猫 | 误区与危险 | [危险物品：猫与真百合的接触](https://www.petpoisonhelpline.com/pet-owners/basics/top-10-plants-poisonous-to-pets/) | 网页收录版本 |
| first-aid | 猫、狗 | 健康与就医 | [急症识别与就医准备](https://ebusiness.avma.org/files/ProductDownloads/mcm-client-brochures-pet-first-aid-2025.pdf) | Pet First Aid 2025 |
| cat-life-stages | 猫 | 生命阶段 | [猫的生命阶段：年龄与照护讨论](https://www.aaha.org/resources/2021-aaha-aafp-feline-life-stage-guidelines/feline-life-stage-definitions/) | 2021 Feline Life Stage Definitions |
| dog-hazards | 狗 | 误区与危险 | [犬的误食风险与危险物品管理](https://ebusiness.avma.org/files/ProductDownloads/mcm-client-brochures-pet-first-aid-2025.pdf) | Pet First Aid 2025 |
| nutrition-energy | 猫、狗 | 饮食与体重 | [健康成年猫狗：维持热量的起始估算](https://www.aaha.org/resources/2021-aaha-nutrition-and-weight-management-guidelines/weight-reduction-in-the-obese-pet/0/) | 2021 AAHA Nutrition and Weight Management Guidelines / Box 1 |
| nutrition-risk | 猫、狗 | 健康与就医 | [哪些营养风险需要专业评估](https://www.aaha.org/resources/2021-aaha-nutrition-and-weight-management-guidelines/nutritional-risk-factors/) | 2021 AAHA / Nutritional Risk Factors |
| nutrition-feeding | 猫、狗 | 饮食与体重 | [把主粮、零食和实际摄入一起计算](https://www.aaha.org/resources/2021-aaha-nutrition-and-weight-management-guidelines/feeding-plans-for-healthy-appropriate-weight-cats-and-dogs/) | 2021 AAHA / Feeding Plans for Healthy, Appropriate Weight Cats and Dogs |
| nutrition-cat-bcs | 猫 | 饮食与体重 | [猫的体况：体重之外还要看脂肪分布](https://wsava.org/wp-content/uploads/2025/06/WSAVA_BCSCat_BCSCat_Nutrition_250612.pdf) | WSAVA feline BCS chart 2025-06 |
| nutrition-dog-bcs | 狗 | 饮食与体重 | [犬的体况：记录肋骨、腰线和腹部变化](https://wsava.org/wp-content/uploads/2025/06/WSAVA_BCSCat_BCSDog_Nutrition_250612.pdf) | WSAVA canine BCS chart 2025-06 |
| nutrition-muscle | 猫、狗 | 健康与就医 | [肌肉状况与体况评分分别记录](https://wsava.org/global-guidelines/global-nutrition-guidelines/) | Global Nutrition Guidelines / Muscle condition score tools |
| nutrition-label | 猫、狗 | 饮食与体重 | [填写包装热量与计量单位](https://wsava.org/global-guidelines/global-nutrition-guidelines/) | Global Nutrition Guidelines / Food Label Guides and Selecting a Pet Food |
| visit-preparation | 猫、狗 | 健康与就医 | [紧急就医前准备联系信息与观察记录](https://ebusiness.avma.org/files/productdownloads/mcm-client-brochures-pet-first-aid-2023.pdf) | AVMA Pet First Aid brochure 2023 |
| cat-multi | 猫 | 新宠到家 | [多猫家庭：循序介绍新猫，识别相处压力](https://catvets.com/wp-content/uploads/2026/07/FelineVMA-Step-by-Step-Guide-How-to-Introduce.pdf) | 2024多猫紧张指南配套照护者手册；网页PDF核对2026-10-10 |
| cat-scratching | 猫 | 互动与训练 | [猫抓沙发：提供合适的抓挠选择](https://www.vet.cornell.edu/departments-centers-and-institutes/cornell-feline-health-center/health-information/feline-health-topics/feline-behavior-problems-destructive-behavior) | 2026-10-10网页核对版；原页未标发布日期 |
| cat-body-language | 猫 | 互动与训练 | [猫突然咬人：先读懂互动信号](https://www.vet.cornell.edu/departments-centers-and-institutes/cornell-feline-health-center/health-information/feline-health-topics/feline-behavior-problems-aggression) | 原页更新2016-12；2026-10-10核对（仅采用非惩罚互动与观察内容） |
| cat-grooming | 猫 | 居住与清洁 | [猫的梳毛与指甲护理：从愿意配合开始](https://www.vet.cornell.edu/departments-centers-and-institutes/cornell-feline-health-center/health-information/feline-health-topics/choosing-and-caring-your-new-cat) | 2026-10-10网页核对版；原页未标发布日期 |
| cat-dental | 猫 | 健康与就医 | [猫的口腔护理：观察、适应与专业检查](https://www.vet.cornell.edu/departments-centers-and-institutes/cornell-feline-health-center/health-information/feline-health-topics/feline-dental-disease) | 2026-10-10网页核对版；原页未标发布日期 |
| cat-vaccination | 猫 | 健康与就医 | [猫的疫苗资料：怎样和兽医确认预防计划](https://www.vet.cornell.edu/departments-centers-and-institutes/cornell-feline-health-center/health-information/feline-health-topics/feline-vaccines-benefits-and-risks) | 原页更新2022-07；2026-10-10核对 |
| cat-appetite | 猫 | 健康与就医 | [猫不吃东西：记录变化，尽快联系兽医](https://www.vet.cornell.edu/departments-centers-and-institutes/cornell-feline-health-center/health-information/feline-health-topics/anorexia) | 2026-10-10网页核对版；原页未标发布日期 |
| cat-vomiting | 猫 | 健康与就医 | [猫呕吐：区分观察事实与猜测原因](https://www.vet.cornell.edu/departments-centers-and-institutes/cornell-feline-health-center/health-information/feline-health-topics/vomiting) | 2026-10-10网页核对版；原页未标发布日期 |
| cat-carrier | 猫 | 健康与就医 | [猫的航空箱适应：让就医出发更平静](https://catvets.com/wp-content/uploads/2024/12/FelineVMA_VisitingYourVet_Web.4.pdf) | FelineVMA照护者手册 ©2024 |
| dog-toilet | 狗 | 互动与训练 | [幼犬如厕：靠机会、监督和及时奖励](https://www.merckvetmanual.com/dog-owners/behavior-of-dogs/behavior-problems-in-dogs) | 2026-10-10网页核对版；原页未标发布日期 |
| dog-socialization | 狗 | 生命阶段 | [幼犬社会化：建立安全、正向的新体验](https://avsab.org/wp-content/uploads/2024/12/Puppy-Socialization-Position-Statement-FINAL.pdf) | AVSAB Puppy Socialization Position Statement ©2008；2026-10-10核对 |
| dog-crate | 狗 | 居住与清洁 | [狗的笼箱适应：安全休息空间怎样建立](https://www.vet.cornell.edu/departments-centers-and-institutes/riney-canine-health-center/canine-health-topics/dog-crates-when-use-them-and-how-pick-one) | 2026-10-10网页核对版；原页未标发布日期 |
| dog-alone | 狗 | 互动与训练 | [狗独处时叫喊或破坏：先记录，再评估压力](https://www.vet.cornell.edu/departments-centers-and-institutes/riney-canine-health-center/canine-health-topics/anxious-behavior-how-help-your-dog-cope-unsettling-situations) | 原页更新2025-12-23；2026-10-10核对 |
| dog-grooming | 狗 | 居住与清洁 | [狗的皮肤、毛发与耳部：日常检查清单](https://www.merckvetmanual.com/dog-owners/routine-care-of-dogs/routine-health-care-of-dogs) | 原页2025-07版；2026-10-10核对 |
| dog-dental | 狗 | 健康与就医 | [狗的家庭口腔护理：循序练习，观察疼痛](https://www.vet.cornell.edu/departments-centers-and-institutes/riney-canine-health-center/canine-health-information/dental-disease-and-home-dental-care) | 2026-10-10网页核对版；原页未标发布日期 |
| dog-adolescent | 狗 | 生命阶段 | [成长中的狗：调整环境与训练难度](https://www.vet.cornell.edu/departments-centers-and-institutes/riney-canine-health-center/canine-health-topics/teenage-years-puppy-proofing-and-training-tips) | 2026-10-10网页核对版；原页未标发布日期 |
| dog-winter | 狗 | 居住与清洁 | [冬季照护：看耐寒差异，也检查脚下环境](https://www.vet.cornell.edu/departments-centers-and-institutes/riney-canine-health-center/canine-health-topics/winter-safety-tips) | 2026-10-10网页核对版；原页未标发布日期 |
| heat-safety | 猫、狗 | 误区与危险 | [炎热天气：避免车内滞留，调整日常活动](https://avma.org/resources/pet-owners/petcare/warm-weather-pet-safety) | 2026-10-10网页核对版；原页未标发布日期 |
| food-storage | 猫、狗 | 饮食与体重 | [宠物食品储存与清洁：保留标签，减少污染](https://www.fda.gov/animal-veterinary/animal-health-literacy/tips-safe-handling-pet-food-and-treats) | 2026-10-10网页核对版；原页未标发布日期 |
| pet-travel | 猫、狗 | 养宠前准备 | [带猫狗出行：行前资料与安全运输清单](https://www.fda.gov/animal-veterinary/animal-health-literacy/travel-training-you-and-your-pets) | 2026-10-10网页核对版；原页未标发布日期 |

## 验证与后续维护

深度问答新增30条质量问法，检查多主题覆盖、证据与章节、操作步骤、资料利用和边界，不以字数作为唯一标准。原有八主题、跨物种、品种/阶段/分类、审核元数据和upsert保留收藏仍回归；浏览器验证长回答、数值表格、章节链接与宠物切换。实际执行记录见根目录TEST_RESULTS.md。这些是工程验收，不是专业兽医审核，也不代表真实服务商生成质量已通过。

后续更新应先选用户实际问题，再找适用的专业资料，写独立中文摘要及清单，更新版本与核对日期，验证代表性检索和专业边界，再导入本机并同步README。不要仅以条目数量或文字长度证明知识可靠性。

## 2026-10-13 照护反馈资料

新增六篇及三篇补深的逐条来源、具体支持范围、失效链接处理、管理窗口和医学频率区别见 [CARE_REVIEW.md](CARE_REVIEW.md)。生成器只编辑现有knowledge_care.json，按IDupsert保留收藏。原目录备份后已导入95篇，15张旧业务表逐行保留，签名密钥与实际配置不变；之前未迁移原库的说明属于2026-10-12历史阶段。
