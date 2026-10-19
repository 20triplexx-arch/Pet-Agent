# 资料与证据链候选交付

2026-10-20。当前构建`123df52bf238a4e066d541b0969c204928eb8428a784af8de57fd7cabd1eab20`。资料、重构代码及本批验收记录已形成候选；**质量和速度门槛未通过，未发布或导入实际业务库**。

| 交付 | 文件 |
|---|---|
| 实施、质量、耗时、费用与未达项 | [实施验收报告](EVIDENCE_REBUILD.md) |
| 95篇分类与17篇实质补深 | [分类清单](KNOWLEDGE_CLASSIFICATION.md)、[来源与缺口](KNOWLEDGE_GAPS.md) |
| 分类、条件、稳定ID、依赖及来源 | [独立注释](../backend/data/evidence/annotations.json) |
| 579块、修订、哈希和离线词项 | [证据索引](../backend/data/evidence/index.json) |
| 逐节与逐页核对 | [579节审阅](../backend/data/evidence/section_reviews.json)、[来源页定位](../backend/data/evidence/source_reviews.json) |
| 14次有输出实测及发布门槛 | [验收JSON](evidence-acceptance-20261019.json) |
| 30组真实配对＋本地1组＋新留出10组的具体结论与证据 | [逐结论审阅](evaluations/evidence-final-source-review.json) |
| 40题三配置与102个补深问法 | [离线逐例结果](evaluations/evidence-offline.json) |
| 后端607项与前端既有验证 | [工程记录](evaluations/evidence-engineering-checks.json) |
| 新冻结且未执行的10题 | [未来留出v8](../backend/evals/quality_holdout_v8.json) |
| 可回滚源码候选 | [候选ZIP](../artifacts/chongban-evidence-20261019-123df52bf238.zip) |
| 包SHA、大小与文件数 | [候选清单](../artifacts/chongban-evidence-20261019-123df52bf238.json) |
| 实施前Git `9520744`恢复包 | [baseline.zip](../artifacts/evidence-rebuild/baseline.zip) |

源码包保留代码、公共文章、审阅注释、索引、题集、测试、实际汇总和脱敏的合成来源审阅。排除凭据、运行storage、业务库、浏览器身份、原始wire抓取和历史截图。包内有逐文件SHA清单，生成后检查ZIP及每个文件；`releasable=false`、`activated=false`。旧构建包及失败文件保留，不能当作当前版本。

## 重建与复核

```powershell
cd backend
../.venv/Scripts/python.exe -m scripts.build_evidence --check
../.venv/Scripts/python.exe -m pytest -q
../.venv/Scripts/python.exe -m evals.evidence_compare --baseline-zip ../artifacts/evidence-rebuild/baseline.zip
../.venv/Scripts/python.exe -m scripts.check_evidence_release --acceptance-report ../docs/evidence-acceptance-20261019.json
```

最后一项当前应返回非零：质量改善和零退步、新留出、三项速度门槛失败，不能用工程测试通过替代。95篇来源及579节的编辑检查已完成，未再把“历史来源未核对”当作当前阻碍；仍未经兽医审核。v7原始输出未改、失败转回归；v8尚未调用，不算通过。

正文和来源改变后须重新编辑核对、修改相应审阅哈希并重建，不能直接改派生索引。批量编辑脚本只重现本批，不自动给新专业内容续签。新的正文、注释或校验会改变构建身份，旧模型成绩不沿用。

## 运行与回滚边界

本次未替换业务库、初始化用户数据、导入文章、切换运行服务或手工提升模型资格，现有ID及收藏关系保留，用户现在无需回滚。

未来达到门槛且决定发布时，先备份实际运行代码、公共资料和业务库，在独立目录验证准确构建。回退只恢复该次发布前代码及同版本公共资料；不覆盖storage、凭据、用户上传或用户后来修改的规范。注释、索引和文章正文一起恢复，不能混用版本。

若未来已经导入公共文章，先在业务库副本验证按原文章ID更新公共字段；保留收藏及其他关系，不删除重建文章。恢复后重新核对构建和模型资格，不手改旧资格为通过。

## 费用

本次续做142次调用均为百炼免费额度，新增现金0元，不以收费标价卡免费预算。仅充值的独立DeepSeek继续10元现金硬上限；原账本现金及未知责任5.625706元，余量4.374294元，41项未知预留保留。9.699048元历史参考总额不等于现金账单；此前0.300952元余量和免费不可用的停止说明已经失效。当前停止发布的原因是质量与速度未达标。详见[免费与充值规则](FREE_MODEL_POLICY.md)。
