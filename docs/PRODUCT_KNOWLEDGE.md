# 猫狗品种、食物、用品与产品比较

更新：2026-10-11。此批采用本地规则与真实知识检索，无模型密钥可用；没有商品库、自动购买或实时价格抓取。

## 入口与实际流程

知识库按猫/狗、通用照护/品种/食物/用品筛选，另保留关键词、生命阶段、主题与收藏。档案的“品种”仍是用户原始文字；新“规范品种”必须用户选择确认，修改原文字或物种后需重新确认。泰迪提示贵宾候选，蓝猫/金渐层视为外观描述，柯基提示具体品种未明确，均不自动猜测。家猫、中华田园犬与混种入口明确其非注册品种性质。

知识库右上角进入 `/products`，选同一类别的1—3件产品，填写具体配方/型号及适用声明。手动粘贴标签可提取候选数值；上传图片可本地识别。用户先核对数字、单位、净含量、分析上下限和声明，再点击“核对并比较”。编辑任何资料后需重新确认，原预览失效。保存按钮才建立私有历史，重复请求不重复创建。切换宠物清空未保存草稿并切换历史，历史展示当时快照，重新比较按当前状态计算。

结论包括“不匹配、需谨慎、条件下可考虑、资料不足、需专业评估”。没有品牌总分、安全承诺或“WSAVA认证”。美国标签解释注明地域，厂家资料由用户提供并标明未经厂家核实。病史、过敏、专业饮食要求、营养风险及处方用途进入专业核对；品种不能决定诊断、食量或固定护理频率。成年犬推定门槛保守采用24个月，12—24个月需确认实际生命阶段，不能用体形或品种自动判断成长结束。

价格由用户填写并注明日期，不换汇。食品按净克重算每100g成本，热量单位完整时算每100kcal成本；每份必须填写克重。每日/30天成本只用用户确认的实际每日摄入。用品月摊销只用填写的预计寿命和耗材，寿命是输入假设。保证分析保留≥、≤、典型值，不推算精确质量排名。

保存食品后可单独明确确认“添加到营养资料”，只追加主粮/零食的标签资料，并清除原热量分配和零食确认；实际摄入留空。不会更改当前方案、任务或喂食量，进入营养页补充数据并重新预览。旧比较遇到宠物资料、体重或营养版本改变时返回409，需重新比较。保存使用事务、幂等键和用户上下文。

## 数据与接口

迁移 `20261011_products` 接续 `20261010_nutrition`：新增 `Breed`、`Pet.breed_id`、知识分类/品种关联/多来源与 `ProductAssessment`。原44篇ID、收藏、会话及所有业务记录保留；删除宠物同步清理关联比较。

| 方法与路径（`/api/v1`） | 用途 |
| --- | --- |
| GET `/breeds?species=cat&q=泰迪` | 品种列表与确认提示；物种不匹配不返回候选 |
| GET `/breeds/{id}` | 名称、分类、别名和指南关联 |
| GET `/knowledge?species=cat&content_kind=breed&breed_id=cat-ragdoll&life_stage=kitten` | 组合筛选；品种过滤保留适用通用资料 |
| GET `/products/ocr/status` | 安装、模型校验和启用状态 |
| POST `/products/ocr` | multipart `files`，返回原文、逐行置信度、候选字段；不保存图片 |
| POST `/products/label/parse` | `{raw_text}`，只提取明确单位及上下限候选 |
| POST `/products/assessments/preview` | `{pet_id?,species,category,products:[...]}`，产品必须 `label_confirmed:true` |
| POST `/products/assessments` | `{inputs,preview_token,confirm:true}` + `Idempotency-Key`，重新评估再保存 |
| GET `/products/assessments?pet_id=...` | 当前宠物私有历史；省略pet_id返回未绑定宠物的比较 |
| GET/DELETE `/products/assessments/{id}` | 私有快照读取/删除 |
| POST `/products/assessments/{id}/nutrition-food` | `{product_index,revision,confirm:true}` + 幂等键，食品标签资料交接 |

结构、长度、有限数值和权限由 `product_schemas.py`、`product_routes.py` 校验。完整请求定义可在本机 `/docs` 查看。预览不写库；比较、营养交接失败不会显示成功，重试复用幂等键。并发同键写入经SQLite事务协调。

Agent新增只读工具 `get_breed_knowledge`、`assess_pet_products`，总计12个。前者读取当前已确认品种或本次明确询问对象，后者重新评估当前用户/宠物最近一次明确保存的比较；尚无比较时给录入入口。模型不自行生成产品数值、价格或新标签事实。对话写入仍由原授权机制控制；标签和知识只作资料，不授予工具权限。系统提示在 `backend/app/agent_system.txt`，导出工具在 `backend/data/tool_definitions.json`。

## 可选本地 OCR

首次安装联网下载依赖，之后识别仅在本机：

```powershell
./scripts/setup.ps1 -WithOCR
# 已有开发环境只补装可选依赖
.venv/Scripts/python.exe -m pip install -r backend/requirements-ocr.txt
```

锁定 RapidOCR3.10.0、ONNX Runtime CPU1.31.0及增量依赖，要求Python3.13兼容平台。模型使用RapidOCR wheel内置三份，不在运行时自动下载；版本、文件与SHA256在 `backend/data/ocr_models.json`，每次进程首次使用校验，换模型需更新清单与验收。运行时CPU、单服务进程、同一时刻一个识别任务；多worker部署不共享此锁，首版本地运行建议一个worker。

支持静态JPEG/PNG/WebP真实格式解码，1—3张，每张≤5MB、≤2000万像素，请求总量≤16MB。去除EXIF、纠正方向、最长边缩至2000后送独立子进程；默认总处理30秒，超时终止子进程。进程禁用网络连接，图片只在内存中处理，不入数据库、日志或模型上下文；仅文本可由用户确认后保存为比较资料。损坏、动画/其他格式、超限拒绝；空结果、低置信行、失败、繁忙、超时都需用户重新拍摄、手动修正或重试。识别置信度不能证明标签真实。

`OCR_ENABLED=false` 或未安装/版本与模型校验不匹配时只提供手动入口；`OCR_TIMEOUT_SECONDS=30`。Docker默认不装OCR，需 `docker build --build-arg WITH_OCR=true -t chongban .`。本轮WindowsCPU真实识别验收包含原创中文/英文标签、180度旋转、模糊、小数、百分比，测试不代表所有真实商业包装识别率。模糊或字号太小应重新拍摄；字段确认不可跳过。

## 来源、许可证与维护

原44篇复用保留，新增24篇指南及21篇选购文章，另复用原食品储存篇补深，共89篇。8猫12犬为注册品种资料；另4个非注册分类。CFA/AKC只用于名称、外形与品种倾向，健康另核对Cornell、AVMA、AAHA、AWC等专业来源。每条多来源的 `supports` 明确作用，版本与核对日期分别保存；无原发布日期不推测。全部 `editorial_summary_unreviewed`，不复制整篇原文或图表。

构建器 `backend/scripts/build_product_knowledge.py` 是本项目人工编写的中文清单生成器，不联网爬取、不调用模型。更改后先逐篇核对来源和适用条件，再运行并执行初始化upsert；不要把篇幅/字段测试当专业审核。新增来源清单及现有44篇见 [KNOWLEDGE.md](KNOWLEDGE.md)。OCR依赖和模型的版权/校验见 [OCR_LICENSES.md](OCR_LICENSES.md) 与 `docs/licenses/`。源码包不含本机数据、密钥、环境、依赖或模型权重；安装器从原分发下载依赖。

最终验收：后端106项、桌面/手机浏览器32项及生产构建通过；已有SQLite运行库备份并增量升级，原业务记录与签名密钥保留。具体场景和未验证范围见 [../TEST_RESULTS.md](../TEST_RESULTS.md)。
