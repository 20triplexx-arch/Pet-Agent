# 原批准计划的字段错误关联验收

原 F1–F4 已获 verdict ship 后，补齐计划中“表单错误关联对应字段”这一已知门槛。没有重选方向、新增素材或修改后端接口/数据库/实体类型。

- api.ts 的 ApiError 保留实际422中的loc与msg，不改变成功返回值；非字段或不可映射的错误仍显示总提示。
- 各可编辑控件添加与后端参数一致的name，包括 tasks.N.FIELD、foods.N.FIELD；SelectField透传名称。响应中的profile前缀按实际营养控件去除，单控件输入的列表子项可归到父控件。
- useAction记录本次触发控件所属form/panel，重试仍使用原闭包及幂等键。Feedback仅关联这个范围内的控件，React portal展示逐字段错误；aria-invalid、aria-describedby与原标签保持一致，定位首个问题字段。新请求/成功/卸载时恢复属性并清理提示。
- 验证稳定标签名称、错误可访问描述、焦点、多字段及嵌套营养字段、手动修改恢复、失败不误报成功、原请求重试键一致且无重复档案。
- 初轮4项失败：错误文字改变了getByLabel标签解析，及两项测试误写已有营养保存按钮名称。保留控件原标签名并纠正测试入口后4项通过（11.6秒），未减弱关联/可访问描述/幂等断言。
- 最终TypeScript/Vite构建通过，40项桌面/手机全量回归通过；含原24业务项、原4修复6项及本门槛4项。当前没有测试覆盖截图。
- 后续字段审查提出FV1（Chat侧栏分钟在提交form外），显式Chat共同控件范围修复后，真实后端422的桌面/手机两项通过（8.4秒）；field-validation-verdict.md评分ship、FV1 resolved，最终全量42项通过（2.0分钟）。前述40项为该后续修复前的中间记录。

证据：field-errors-pet-desktop.png、field-errors-pet-mobile.png、field-errors-nutrition-desktop.png、field-errors-nutrition-mobile.png。均1280×900或390×844固定视口，有主动错误定位后的真实滚动位置。其余页面与原四修复证据均由最终全量测试重新采集。

请核查此已知验收门槛的实现与4张原尺寸截图，确认字段对应、可读性、焦点及可访问性记录是否支持交付；保留此前F1–F4的已解决状态，不扩展新的润色清单。新增记录写 field-validation-review.md。能力边界：跨字段、服务端业务错误或不对应可编辑控件的路径仍保持总提示，不声称任意422路径都能映射。
