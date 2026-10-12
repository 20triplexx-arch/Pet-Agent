import type { NutritionData, Food } from "./care-api";

export type Supplement = {
  goal?: string; observations?: string; timeline?: string;
  diet_activity?: string; environment_changes?: string; professional_advice?: string;
  nutrition?: Partial<NutritionData>;
};

export function ChatSupplement({ value, change, busy }: { value: Supplement; change: (value: Supplement) => void; busy: boolean }) {
  const nutrition = value.nutrition || {};
  const editNutrition = (key: keyof NutritionData, field: NutritionData[keyof NutritionData]) => change({ ...value, nutrition: { ...nutrition, [key]: field } });
  const food: Food = nutrition.foods?.[0] || { name: "", kind: "main", complete_adult_food: null, energy: null, energy_unit: "kcal_100g", portion_grams: null, daily_grams: null, label_note: "用户本次核对的包装资料，未经厂家核实" };
  const editFood = (key: keyof Food, field: Food[keyof Food]) => change({ ...value, nutrition: { ...nutrition, foods: [{ ...food, [key]: field }], treats_confirmed: false, food_shares_confirmed: false } });
  const choices: [keyof NutritionData, string, [string, string][]][] = [
    ["life_stage", "生命阶段", [["unknown", "未知"], ["adult", "成年"], ["growing", "成长阶段"], ["senior", "老年"]]],
    ["health_status", "当前健康状态", [["unknown", "未知"], ["healthy", "健康"], ["unwell", "有健康问题"]]],
    ["muscle", "肌肉状况", [["unknown", "未知"], ["normal", "正常"], ["loss", "有肌肉损失"]]],
    ["activity_level", "活动水平", [["unknown", "未知"], ["low", "低"], ["normal", "一般"], ["high", "高强度"]]],
    ["pregnancy_lactation", "孕哺状态", [["unknown", "未知"], ["no", "非孕哺"], ["yes", "孕期或哺乳期"]]],
    ["assessor", "体况填写者", [["unknown", "未知"], ["owner", "饲养者"], ["vet", "兽医"]]],
  ];
  return <fieldset className="chat-supplement-fields" disabled={busy}>
    <legend>用户补充，仅用于本会话</legend>
    <p className="muted">未知可留空，注明发生时间与信息来源。发送会沿用在本会话中；档案、记录和喂食任务不会自动修改。</p>
    {([
      ["goal", "照护目标", "例如：改善独处安排，核对目前喂食是否合适"],
      ["observations", "本次观察", "描述看到的表现、频率、精神和食欲，避免自行下诊断"],
      ["timeline", "时间线", "何时开始，何时变化，观察了多少次"],
      ["diet_activity", "饮食与活动", "目前吃什么、吃多少、零食及活动安排"],
      ["environment_changes", "环境变化", "搬家、新宠、作息、清洁用品或近期接触物"],
      ["professional_advice", "用户提供的专业建议", "兽医原建议、日期与来源；不要省略适用条件"],
    ] as const).map(([key, label, placeholder]) => <label key={key}>{label}<textarea name={`context.${key}`} value={value[key] || ""} onChange={e => change({ ...value, [key]: e.target.value })} maxLength={key === "observations" || key === "professional_advice" || key === "diet_activity" ? 3000 : 2000} placeholder={placeholder} /></label>)}
    <details className="nutrition-supplement">
      <summary>补充营养数据（选填）</summary>
      <p className="muted">复用营养资料校验；未填写项沿用已保存资料。此处仅支持一款主粮，混合主粮或零食请在营养页面完整填写；新食品列表需要重新确认。</p>
      {choices.map(([key, label, options]) => <label key={key}>{label}<select name={`context.nutrition.${key}`} value={String(nutrition[key] ?? "unknown")} onChange={e => editNutrition(key, e.target.value as NutritionData[keyof NutritionData])}>{options.map(([id, title]) => <option key={id} value={id}>{title}</option>)}</select></label>)}
      <label>体况评分 BCS（1—9）<input name="context.nutrition.bcs" type="number" min={1} max={9} step={1} value={nutrition.bcs ?? ""} onChange={e => editNutrition("bcs", e.target.value === "" ? null : Number(e.target.value))} /></label>
      <label>体况评估日期<input name="context.nutrition.assessed_on" type="date" value={nutrition.assessed_on || ""} onChange={e => editNutrition("assessed_on", e.target.value || null)} /></label>
      <label>当前主粮名称<input name="context.nutrition.foods.0.name" maxLength={100} value={food.name} onChange={e => editFood("name", e.target.value)} /></label>
      <label>包装热量<input name="context.nutrition.foods.0.energy" type="number" min={0.001} max={100000} step="any" value={food.energy ?? ""} onChange={e => editFood("energy", e.target.value === "" ? null : Number(e.target.value))} /></label>
      <label>热量单位<select name="context.nutrition.foods.0.energy_unit" value={food.energy_unit} onChange={e => editFood("energy_unit", e.target.value as Food["energy_unit"])}>{["kcal_100g", "kcal_kg", "kj_100g", "kj_kg", "kcal_portion", "kj_portion"].map(unit => <option value={unit} key={unit}>{unit.replace("_", " / ").replace("portion", "份")}</option>)}</select></label>
      <label>每份克重（按份热量必填）<input name="context.nutrition.foods.0.portion_grams" type="number" min={0.001} step="any" value={food.portion_grams ?? ""} onChange={e => editFood("portion_grams", e.target.value === "" ? null : Number(e.target.value))} /></label>
      <label>实际每日主粮克数<input name="context.nutrition.foods.0.daily_grams" type="number" min={0} max={10000} step="any" value={food.daily_grams ?? ""} onChange={e => editFood("daily_grams", e.target.value === "" ? null : Number(e.target.value))} /></label>
      <label className="care-check"><input type="checkbox" checked={food.complete_adult_food === true} onChange={e => editFood("complete_adult_food", e.target.checked)} />已核对适用于当前物种成年阶段的全价主粮声明</label>
      {([ ["weight_confirmed", "已核对档案显示的体重与日期"], ["treats_confirmed", "本次新填食品没有遗漏零食；此处新填主粮时须确认没有零食"], ["food_shares_confirmed", "已确认本次完整主粮列表及热量分配"] ] as const).map(([key, label]) => <label key={key} className="care-check"><input type="checkbox" checked={nutrition[key] === true} onChange={e => editNutrition(key, e.target.checked)} />{label}</label>)}
    </details>
  </fieldset>;
}
