# 第一批 Agent 接口与规则

所有接口位于 `/api/v1`，需要当前登录用户 Bearer token。用户ID来自服务端，用户不能通过载荷指定它。所有宠物接口先校验所有权；越权返回404。写入必需 `Idempotency-Key`，同键同请求复用已提交结果，同键不同请求409。失败事务回滚，没有成功记录。

| 方法与路径 | 请求及行为 |
| --- | --- |
| GET `/pets/{id}/nutrition/profile` | 返回profile、revision、active_plan_id、needs_reassessment |
| PUT `/pets/{id}/nutrition/profile` | `{profile, revision}`，显式保存资料，不创建任务 |
| POST `/pets/{id}/nutrition/preview` | NutritionInput，只读取，不持久化草稿；status为ready/needs_info/professional_required |
| POST `/pets/{id}/nutrition/plans` | `{profile,revision,preview_token,daily_target_kcal,planned_treat_kcal,meal_times}`，重新校验与计算，事务替换旧营养方案 |
| POST `/hospitals/search` | 城市/区县或成对经纬度、coordinate_system（默认wgs84）、radius_km（5/10/20）、可选pet_id；位置只在该请求使用 |
| GET `/hospitals/usage` | 全应用上海时区计数及日/月上限；不返回密钥，不代表供应商余额 |
| POST `/pets/{id}/visit-summary/preview` | `{started_at,observation,medicines_as_reported}`；时间带时区，不允许未来，输出真实资料文本/来源/urgent |

完整验证结构由 `app/care_schemas.py` 与在线 `/docs` 提供；extra字段拒绝，数值拒绝负值及非有限值，摄入量可为0但主粮总摄入0不能计算分配。体况1—9、餐次最多6个且时间不重复，食物最多15种。

示例营养输入（仅演示字段与单位；健康/体况必须按当前宠物实际情况填写）：

```json
{
  "life_stage": "adult", "bcs": 5, "muscle": "normal",
  "assessed_on": "2026-10-01", "assessor": "owner",
  "activity_level": "normal", "health_status": "healthy", "pregnancy_lactation": "no",
  "weight_confirmed": true, "treats_confirmed": true, "food_shares_confirmed": true,
  "foods": [{"name":"测试主粮（非商品推荐）", "kind":"main", "complete_adult_food":true,
    "energy":400, "energy_unit":"kcal_100g", "daily_grams":60}]
}
```

预览返回规则版本`aaha-2021-maintenance-v1`、evidence_digest、preview_token、revision、input_snapshot、sources、questions、warnings、calculation及food换算。指纹绑定用户、宠物、档案、体重、近30天记录、营养输入、已保存资料版本、知识内容与规则版本。服务端重新计算指纹；变更后保存409。客户端不可提供可信克数或修改计算输入后继续沿用旧token。

普通活动维持系数：绝育猫1.2—1.4/未绝育猫1.4—1.6，绝育犬1.4—1.6/未绝育犬1.6—1.8；低活动猫1.0/犬1.0—1.2。资料充分、健康成年、BCS4—5且肌肉正常才估算；非成人、未知资料和营养风险不会推导固定数量。范围只是起始参考，全部在后端由规则与检索资料计算。混合主粮按已确认现有热量份额，零食按现有零食热量份额换算，用户零食目标为0时相应换算为0。

保存方案会增加PetNutritionProfile版本并关联CarePlan；来源元数据包含kind=nutrition、完整计算输入、真实来源、用户目标、后端克数。旧营养提醒暂停，不删除完成历史；通用计划编辑不能修改营养数量。原方案被替换或证据变化后不能直接恢复，需重新评估。

Pydantic AI注册的工具（JSON Schema见 `backend/data/tool_definitions.json`）：

- 原5个：get_pet_profile、search_pet_knowledge、save_care_plan、create_reminder、record_care_log。
- 新5个：get_care_history、get_current_care_plans、assess_nutrition、search_nearby_hospitals、build_vet_visit_summary。

新增读取工具均无可由模型指定的用户/宠物ID；读取范围由当前会话上下文绑定。assess_nutrition只读取已保存营养资料，数值由后端给出。search_nearby_hospitals返回医院查询入口；模型不接收精确位置、不代为申请定位，真实搜索由独立POST执行。build_vet_visit_summary生成事实摘要，模型工具文本最多12000字符并明确标记截断，完整内容从页面获取。营养资料/方案保存通过明确页面操作及后端事务执行，避免模型创造任意数量或借知识正文授予写入权限。

医院接口模式external/map_link、状态ok/empty/unavailable。外部超时或额度失败返回明确不可用状态与搜索入口，不伪造医院。坐标转换与检索分别计数并独立提交，不因外层请求失败而丢失计数；并发上限通过条件更新控制。钥匙只从服务端环境读取，固定供应商主机/路径，不允许模型指定外部URL。营业信息未经现场核实，急诊/接诊/资质均待核实；不展示高德评分作为医疗质量。

就医摘要使用用户维护档案、带日期的近期记录、本次观察和用户原文建议。缺失项留为“未知/未填写”，不把旧资料创建日期冒充更新日期。文本可编辑/复制/下载，应用不发送给医院；页面草稿切宠物即清除。
