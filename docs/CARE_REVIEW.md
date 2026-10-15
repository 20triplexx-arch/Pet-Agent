# 照护复盘、多项记录与来源核对

更新：2026-10-13。此批补齐记录→复盘→核对→重新预览的日常流程，复盘在本地计算，不调用模型、地图或付费服务。没有增加一级导航或首页大卡片。

## 用户流程

在照护记录页添加一条记录，或展开“多项一起记录”。可以同时填写体重、饮食、活动、护理、观察，每类最多一条；只保存非空项，不把未知补成正常。发生时间按用户IANA时区转换，核对宠物与时间并勾选确认后，整批事务保存。失败不部分写入，原请求重试复用幂等键。

选择7天或30天复盘，窗口包含用户当地的今天，今天只统计已发生部分。显示记录覆盖天数、无记录日期、各类型数量、窗口内打卡次数、当前到期待办，以及窗口内不同时间的两次有效称重之差。当前待办不等于窗口内所有历史漏做；未记录不等于未照护，因此不生成历史任务漏做率或健康评分。暂停或旧任务的实际完成历史仍可统计，按打卡发生时间归入窗口。

有新饮食、体重或观察记录时，可提示核对当前营养方案。记录文字不自动写入营养档案，复盘不直接更改食量、计划或任务，仍需在原营养/计划页面重新预览和明确保存。观察不是诊断，体重差不推定脂肪、肌肉或疾病。7/30天是应用管理窗口，不是医学复查或称重频率。

仅对最近24小时观察记录展示已有风险规则命中的紧急线索，保留观察时间，并说明历史不能确认当前是否解决；正在发生时优先联系兽医。旧观察不自动当成当前急症，也不推断已经恢复。规则属启发式，未命中不代表安全。

可下载复盘TXT，包含统计时间、事实、建议、边界与实际检索来源。不会自动发给医院或其他人员。聊天输入“照护复盘/照护周报/照护月报”可直接读取当前宠物事实并进入记录页，没有模型调用；切换宠物后清空草稿、重新读取相应记录。

## 接口与Agent

| 接口（`/api/v1`） | 行为 |
| --- | --- |
| GET `/pets/{id}/care-review?days=7` | 只读；days仅7或30，按当前登录用户的时区统计 |
| POST `/pets/{id}/logs/batch` | `{entries: [LogInput...], confirm:true}`，1—5条不同类型；要求Idempotency-Key，整批事务提交 |

复盘返回`period`、`summary`、`counts`、`daily`、`weight`、`observations`、`alerts`、`plans`、`suggestions`、`record_ids`、`completion_ids`、`sources`、`limitations`、`generated_at`、`rule_version`及TXT用的`text`。最新20条观察附总数；事实与统计边界一起返回，所有记录和任务均按服务端用户/宠物权限筛选。

Agent新增只读`get_care_review(days=7)`，共13个工具。模型不能指定user_id或pet_id；工具版省略每日数组和全量记录ID，只给称重端点与最近5条观察的有界文本，保持上下文成本可控。显式询问其他物种或品种时不能拿当前宠物记录替代；复盘工具不具写入权限。

知识来源增加`evidence`：由服务器从实际知识章节提取的最多3段、每段最多400字符，可能是完整段落的前部；完整内容仍从章节链接查看。模型的`citation_sections`可选`evidence_text`，提供时必须是该真实章节的原文片段（忽略空白差异），否则502且不保存回答，已消耗的供应商用量仍依原机制保留。这是出处与原文核对，不是自动语义审核，不保证每个模型论断被来源支持。

## 内容与来源维护

保留既有89个ID及收藏，新增6篇，合计95篇：记录质量、照护复盘、喂食执行、狗的恐惧支持、猫的低压力护理、照护交接。另补深`cat-grooming`、`cat-dental`、`dog-alone`，明确固定护理时机、未核对用品材质和固定观察期限的证据边界。

| 实际查阅的资料 | 支持范围 |
| --- | --- |
| [AAHA 2021营养指南执行摘要](https://www.aaha.org/trends-magazine/publications/nutritional-guidelines/) | 营养史、持续评估、个体与环境资料、反馈；应用7/30天窗口和统计方法为本项目设计 |
| [WSAVA饮食史表](https://wsava.org/wp-content/uploads/2020/01/Diet-History-Form.pdf) | 全部食品、份量、频率、起始时间、量具及补充剂；不能推测杯罐克重 |
| [VCA脱敏与反条件作用](https://vcahospitals.com/vetco/know-your-pet/overcoming-fears-with-desensitization-and-counterconditioning) | 降低刺激、正向配对、按反应推进及惩罚风险；不支持统一改善期限 |
| [FelineVMA尊重式猫互动](https://catvets.com/resource/2019-respectful-handling-to-prevent-fear-and-pain-position-statement/) | 理解身体与压力信号、减少恐惧和疼痛；不授予主人临床保定或镇静操作能力 |
| [Cornell猫牙齿疾病](https://www.vet.cornell.edu/departments-centers-and-institutes/cornell-feline-health-center/health-information/feline-health-topics/feline-dental-disease) | 猫用牙刷与渐进适应，明显牙龈问题先核对疼痛与专业意见 |
| [CDC宠物应急准备](https://www.cdc.gov/healthy-pets/emergency-preparedness/index.html) | 身份、医疗/疫苗记录和联系人；美国应急背景，不解释中国医疗或商家制度 |
| [Cornell猫下泌尿道疾病](https://www.vet.cornell.edu/departments-centers-and-institutes/cornell-feline-health-center/health-information/feline-health-topics/feline-lower-urinary-tract-disease) | 无法排尿/尿道阻塞的紧急风险；原猫规则增加三个中文同义表达，不套到其他物种 |

编辑器`python -m scripts.update_care_knowledge`保留其他条目并按稳定ID更新6篇及3篇补充段落，不联网、不调用模型。它只编辑种子文件；之后执行初始化/知识导入才更新数据库。每条references区分专业依据与应用整理，全部未经兽医审核。最初尝试的旧AVMA PDF当前404，交接篇改用已查阅的CDC页面，未将失效链接保存为新依据。

## 验证与限制

后端190项、桌面/手机68项、100场景离线评测及构建通过。覆盖DST窗口、事务回滚/并发/重试、权限、病例日期、体重来源、复评不改计划、原文片段拒绝、物种隔离和真实本地OCR等已有流程。测试默认预算与开发者.env隔离，不改实际配置。截图使用隔离数据，不写用户业务记录。

本机运行库已备份并升级到既有`20261012_deep_chat`，此批复盘复用现有实体，没有再增加表。15张旧业务表逐行保留、配置/签名密钥/阶段测试预算账本未改变。8000运行新代码，输入上限12000、95篇知识、复盘和批量记录可用。当前配置为真实模型模式，本轮未发起真实模型调用，整合版真人质量、兽医审核、Docker/PostgreSQL实机、地图和原生Safari仍未验证。多成员协作、自动推送、收费会员及支付没有在本批实现。
