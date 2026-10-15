import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import {
  Utensils,
  Plus,
  Trash2,
  MapPin,
  Navigation,
  Phone,
  FileText,
  ArrowUpRight,
} from "./icons";
import { useApp } from "./App";
import { api, dateText, type Plan } from "./api";
import type {
  NutritionData,
  NutritionProfile,
  NutritionPreview,
  Food,
  HospitalResult,
  MapUsage,
  VisitSummary,
  Region,
} from "./care-api";
import { RegionInput, HospitalMap } from "./hospital-search";
import { useRemote, useAction } from "./hooks";
import {
  PageTitle,
  Panel,
  State,
  Feedback,
  Sources,
  PetPortrait,
  Empty,
} from "./components";
import { Button } from "./components/ui/button";

const unknown = { unknown: "未知 / 待补充" };
function numberValue(value: string) {
  return value === "" ? null : Number(value);
}
const fmt = (value: number) =>
  value.toLocaleString("zh-CN", { maximumFractionDigits: 1 });
function SelectField({
  name,
  label,
  value,
  choices,
  change,
}: {
  name: string;
  label: string;
  value: string;
  choices: Record<string, string>;
  change: (v: string) => void;
}) {
  return (
    <label>
      {label}
      <select
        name={name}
        aria-label={label}
        value={value}
        onChange={(e) => change(e.target.value)}
      >
        {Object.entries(choices).map(([v, t]) => (
          <option key={v} value={v}>
            {t}
          </option>
        ))}
      </select>
    </label>
  );
}
function NeedPet() {
  return (
    <Empty>
      请先选择宠物，再补充它的资料。
      <Link to="/pets">
        去宠物档案 <ArrowUpRight size={14} />
      </Link>
    </Empty>
  );
}

export function Nutrition() {
  const { pet, user } = useApp();
  const remote = useRemote<NutritionProfile>(
    pet ? `/pets/${pet.id}/nutrition/profile` : null,
  );
  const plans = useRemote<Plan[]>(pet ? `/pets/${pet.id}/plans` : null);
  const action = useAction();
  const [profile, setProfile] = useState<NutritionData | null>(null);
  const [preview, setPreview] = useState<NutritionPreview | null>(null);
  const [target, setTarget] = useState("");
  const [treatTarget, setTreatTarget] = useState("0");
  const [times, setTimes] = useState("08:00,18:00");
  const [saved, setSaved] = useState<Plan | null>(null);
  useEffect(() => {
    if (remote.data) setProfile(remote.data.profile);
  }, [remote.data]);
  const change = <K extends keyof NutritionData>(
    key: K,
    value: NutritionData[K],
  ) => {
    setProfile((p) => (p ? { ...p, [key]: value } : p));
    setPreview(null);
    setSaved(null);
  };
  const foodChange = (index: number, values: Partial<Food>) =>
    profile &&
    change(
      "foods",
      profile.foods.map((f, i) => (i === index ? { ...f, ...values } : f)),
    );
  const currentPlan = plans.data?.find(
    (p) => p.id === remote.data?.active_plan_id,
  );
  return (
    <>
      <PageTitle
        title="把喂食安排得更合适"
        desc={
          pet
            ? `${pet.name}的营养资料与方案 · 本地计算`
            : "从当前食物和真实记录开始。"
        }
      >
        {pet && <PetPortrait species={pet.species} />}
      </PageTitle>
      <Feedback action={action} />
      {!pet ? (
        <NeedPet />
      ) : (
        <>
          <State {...remote} retry={remote.reload} />
          {remote.data?.needs_reassessment && (
            <div className="note" role="status">
              有新的档案、记录或营养资料，请重新评估。原方案不会自动改变。
            </div>
          )}
          {currentPlan && (
            <div className="care-current">
              <span>
                当前方案：{currentPlan.title} ·{" "}
                {currentPlan.status === "active" ? "执行中" : "已暂停 / 完成"}
              </span>
              <Link to="/plans">
                查看任务与打卡 <ArrowUpRight size={14} />
              </Link>
            </div>
          )}
          {profile && (
            <div className="care-workspace">
              <Panel className="nutrition-form">
                <div className="section-heading">
                  <h2>
                    <Utensils size={20} /> 本次营养资料
                  </h2>
                  <span className="badge quiet">未知项可留空</span>
                </div>
                <fieldset disabled={action.busy} className="care-fieldset">
                  <details open className="care-details">
                    <summary>身体与健康状态</summary>
                    <div className="form-grid">
                      <SelectField
                        name="life_stage"
                        label="生命阶段"
                        value={profile.life_stage}
                        choices={{
                          ...unknown,
                          adult: "成年（已确认）",
                          growing: "成长阶段",
                          senior: "老年阶段",
                        }}
                        change={(v) =>
                          change("life_stage", v as NutritionData["life_stage"])
                        }
                      />
                      <label>
                        体况评分 BCS（1—9）
                        <input
                          name="bcs"
                          type="number"
                          min={1}
                          max={9}
                          step={1}
                          value={profile.bcs ?? ""}
                          onChange={(e) =>
                            change("bcs", numberValue(e.target.value))
                          }
                        />
                      </label>
                      <SelectField
                        name="muscle"
                        label="肌肉状况"
                        value={profile.muscle}
                        choices={{
                          ...unknown,
                          normal: "正常（已评估）",
                          loss: "存在肌肉损失",
                        }}
                        change={(v) =>
                          change("muscle", v as NutritionData["muscle"])
                        }
                      />
                      <label>
                        体况评估日期
                        <input
                          name="assessed_on"
                          type="date"
                          value={profile.assessed_on ?? ""}
                          onChange={(e) =>
                            change("assessed_on", e.target.value || null)
                          }
                        />
                      </label>
                      <SelectField
                        name="assessor"
                        label="体况填写者"
                        value={profile.assessor}
                        choices={{
                          ...unknown,
                          owner: "用户自评",
                          vet: "用户录入兽医评估",
                        }}
                        change={(v) =>
                          change("assessor", v as NutritionData["assessor"])
                        }
                      />
                      <SelectField
                        name="activity_level"
                        label="活动水平"
                        value={profile.activity_level}
                        choices={{
                          ...unknown,
                          low: "活动较少",
                          normal: "普通日常活动",
                          high: "高强度活动",
                        }}
                        change={(v) =>
                          change(
                            "activity_level",
                            v as NutritionData["activity_level"],
                          )
                        }
                      />
                      <SelectField
                        name="health_status"
                        label="当前健康状态"
                        value={profile.health_status}
                        choices={{
                          ...unknown,
                          healthy: "未报告当前健康问题",
                          unwell: "有健康问题",
                        }}
                        change={(v) =>
                          change(
                            "health_status",
                            v as NutritionData["health_status"],
                          )
                        }
                      />
                      <SelectField
                        name="pregnancy_lactation"
                        label="孕期 / 哺乳期"
                        value={profile.pregnancy_lactation}
                        choices={{
                          ...unknown,
                          no: "不处于孕哺期",
                          yes: "处于孕期或哺乳期",
                        }}
                        change={(v) =>
                          change(
                            "pregnancy_lactation",
                            v as NutritionData["pregnancy_lactation"],
                          )
                        }
                      />
                    </div>
                    <p className="small muted">
                      最新体重：
                      {pet.weight === null
                        ? "尚无记录"
                        : `${pet.weight} kg · ${dateText(pet.weight_date!, user.timezone)}`}{" "}
                      <Link to="/logs">记录体重</Link>
                    </p>
                    <label className="care-check">
                      <input
                        name="weight_confirmed"
                        type="checkbox"
                        checked={profile.weight_confirmed}
                        onChange={(e) =>
                          change("weight_confirmed", e.target.checked)
                        }
                      />
                      我已核对最新体重及日期，适用于本次评估
                    </label>
                    <label>
                      饮食限制 / 兽医要求
                      <textarea
                        name="diet_restrictions"
                        value={profile.diet_restrictions}
                        maxLength={2000}
                        onChange={(e) =>
                          change("diet_restrictions", e.target.value)
                        }
                        placeholder="请保留原意；不知道可以留空"
                      />
                    </label>
                    <label>
                      当前异常观察
                      <textarea
                        name="current_symptoms"
                        value={profile.current_symptoms}
                        maxLength={2000}
                        onChange={(e) =>
                          change("current_symptoms", e.target.value)
                        }
                        placeholder="填写观察到的事实"
                      />
                    </label>
                    <p className="small muted">
                      体况需结合触摸与观察；自评不会被标为兽医评估。犬只成年时间需结合个体情况确认。
                    </p>
                  </details>
                  <div className="care-food-heading">
                    <h3>现在吃些什么</h3>
                    <Button
                      type="button"
                      onClick={() =>
                        change("foods", [
                          ...profile.foods,
                          {
                            name: "",
                            kind: "main",
                            complete_adult_food: null,
                            energy: null,
                            energy_unit: "kcal_100g",
                            portion_grams: null,
                            daily_grams: null,
                            label_note: "用户抄录包装，未经应用核实",
                          },
                        ])
                      }
                      disabled={profile.foods.length >= 15}
                    >
                      <Plus size={15} />
                      添加食物
                    </Button>
                  </div>
                  {!profile.foods.length && (
                    <p className="muted">添加当前主粮；有零食时也请列入。</p>
                  )}
                  {profile.foods.map((food, i) => (
                    <fieldset className="food-entry" key={i}>
                      <legend>食物 {i + 1}</legend>
                      <div className="form-grid">
                        <label>
                          食物名称
                          <input
                            name={`foods.${i}.name`}
                            value={food.name}
                            maxLength={100}
                            onChange={(e) =>
                              foodChange(i, { name: e.target.value })
                            }
                          />
                        </label>
                        <SelectField
                          name={`foods.${i}.kind`}
                          label="食物类型"
                          value={food.kind}
                          choices={{ main: "主粮", treat: "零食 / 其他食物" }}
                          change={(v) =>
                            foodChange(i, { kind: v as Food["kind"] })
                          }
                        />
                        <label>
                          包装热量
                          <input
                            name={`foods.${i}.energy`}
                            type="number"
                            min="0.0001"
                            step="any"
                            value={food.energy ?? ""}
                            onChange={(e) =>
                              foodChange(i, {
                                energy: numberValue(e.target.value),
                              })
                            }
                          />
                        </label>
                        <SelectField
                          name={`foods.${i}.energy_unit`}
                          label="热量单位"
                          value={food.energy_unit}
                          choices={{
                            kcal_100g: "kcal / 100 g",
                            kcal_kg: "kcal / kg",
                            kj_100g: "kJ / 100 g",
                            kj_kg: "kJ / kg",
                            kcal_portion: "kcal / 份",
                            kj_portion: "kJ / 份",
                          }}
                          change={(v) =>
                            foodChange(i, {
                              energy_unit: v as Food["energy_unit"],
                            })
                          }
                        />
                        {food.energy_unit.endsWith("portion") && (
                          <label>
                            每份重量（g）
                            <input
                              name={`foods.${i}.portion_grams`}
                              type="number"
                              min="0.0001"
                              step="any"
                              value={food.portion_grams ?? ""}
                              onChange={(e) =>
                                foodChange(i, {
                                  portion_grams: numberValue(e.target.value),
                                })
                              }
                            />
                          </label>
                        )}
                        <label>
                          当前每日摄入（g）
                          <input
                            name={`foods.${i}.daily_grams`}
                            type="number"
                            min={0}
                            step="any"
                            value={food.daily_grams ?? ""}
                            onChange={(e) =>
                              foodChange(i, {
                                daily_grams: numberValue(e.target.value),
                              })
                            }
                          />
                        </label>
                        {food.kind === "main" && (
                          <SelectField
                            name={`foods.${i}.complete_adult_food`}
                            label="全价主粮确认"
                            value={
                              food.complete_adult_food === null
                                ? "unknown"
                                : String(food.complete_adult_food)
                            }
                            choices={{
                              ...unknown,
                              true: "包装确认适用该物种成年阶段",
                              false: "未确认 / 不是全价主粮",
                            }}
                            change={(v) =>
                              foodChange(i, {
                                complete_adult_food:
                                  v === "unknown" ? null : v === "true",
                              })
                            }
                          />
                        )}
                      </div>
                      <label>
                        标签来源 / 备注
                        <input
                          name={`foods.${i}.label_note`}
                          value={food.label_note}
                          maxLength={500}
                          onChange={(e) =>
                            foodChange(i, { label_note: e.target.value })
                          }
                        />
                      </label>
                      <Button
                        type="button"
                        className="danger-text"
                        onClick={() =>
                          change(
                            "foods",
                            profile.foods.filter((_, n) => n !== i),
                          )
                        }
                      >
                        <Trash2 size={14} />
                        移除此食物
                      </Button>
                    </fieldset>
                  ))}
                  <label className="care-check">
                    <input
                      name="treats_confirmed"
                      type="checkbox"
                      checked={profile.treats_confirmed}
                      onChange={(e) =>
                        change("treats_confirmed", e.target.checked)
                      }
                    />
                    所有零食已列入；没有零食也已确认
                  </label>
                  <label className="care-check">
                    <input
                      name="food_shares_confirmed"
                      type="checkbox"
                      checked={profile.food_shares_confirmed}
                      onChange={(e) =>
                        change("food_shares_confirmed", e.target.checked)
                      }
                    />
                    确认按当前主粮热量比例分配，不生成新食谱
                  </label>
                  <div className="button-row care-primary-actions">
                    <Button
                      className="primary"
                      onClick={() => {
                        const snapshot = structuredClone(profile);
                        action.run(async () => {
                          const p = await api<NutritionPreview>(
                            `/pets/${pet.id}/nutrition/preview`,
                            "POST",
                            snapshot,
                          );
                          setPreview(p);
                          setTarget("");
                          setTreatTarget(
                            String(p.calculation?.current_treat_kcal ?? 0),
                          );
                          setSaved(null);
                        }, "评估已返回，尚未保存方案");
                      }}
                    >
                      评估并预览方案
                    </Button>
                    <Button
                      onClick={() => {
                        const payload = {
                          profile: structuredClone(profile),
                          revision: remote.data!.revision,
                        };
                        action.run(async (key) => {
                          await api(
                            `/pets/${pet.id}/nutrition/profile`,
                            "PUT",
                            payload,
                            key,
                          );
                          remote.reload();
                          setPreview(null);
                        }, "营养资料已保存");
                      }}
                    >
                      只保存资料
                    </Button>
                  </div>
                </fieldset>
              </Panel>
              <div className="care-results">
                <Panel className="nutrition-result">
                  <h2>
                    {preview
                      ? preview.status === "ready"
                        ? "你的喂食参考"
                        : preview.status === "professional_required"
                          ? "先做专业评估"
                          : "还需要这些资料"
                      : "先了解它，再安排喂食"}
                  </h2>
                  {!preview && (
                    <>
                      <p className="muted">
                        填入真实状态和包装信息，查看当前摄入与个体参考。
                      </p>
                      <p className="small muted">
                        仅为健康成年猫狗提供维持体重的起始估算。成长、疾病、孕哺与体况异常需要专业评估。
                      </p>
                    </>
                  )}
                  {preview && (
                    <>
                      {preview.urgent && (
                        <div className="alert" role="alert">
                          请立即联系兽医或宠物急诊，暂不保存营养方案。
                          <Link to="/hospitals">找医院</Link>
                        </div>
                      )}
                      {preview.warnings.map((w) => (
                        <p className="note" key={w}>
                          {w}
                        </p>
                      ))}
                      {preview.questions.length > 0 && (
                        <>
                          <ul className="care-questions">
                            {preview.questions.slice(0, 3).map((q) => (
                              <li key={q}>{q}</li>
                            ))}
                          </ul>
                          {preview.questions.length > 3 && (
                            <details className="care-details">
                              <summary>其他待补充信息</summary>
                              <ul>
                                {preview.questions.slice(3).map((q) => (
                                  <li key={q}>{q}</li>
                                ))}
                              </ul>
                            </details>
                          )}
                        </>
                      )}
                      {preview.calculation && (
                        <>
                          <dl className="nutrition-numbers">
                            <dt>当前每日摄入</dt>
                            <dd>
                              {fmt(preview.calculation.current_kcal)} kcal
                            </dd>
                            <dt>维持热量起始范围</dt>
                            <dd>
                              {preview.calculation.daily_kcal_range
                                .map(fmt)
                                .join("—")}{" "}
                              kcal / 天
                            </dd>
                          </dl>
                          <div className="care-food-results">
                            {preview.foods
                              .filter((f) => f.kind === "main")
                              .map((f, i) => (
                                <div key={i}>
                                  <strong>{f.name}</strong>
                                  <span>
                                    热量占比 {fmt((f.calorie_share ?? 0) * 100)}
                                    %
                                  </span>
                                  <p>
                                    约{" "}
                                    {f.reference_grams_range
                                      ?.map(fmt)
                                      .join("—")}{" "}
                                    g / 天
                                  </p>
                                </div>
                              ))}
                          </div>
                          <p className="small muted">
                            克数参考扣除了当前零食热量；保存时按你确认的目标重新计算。范围不代表固定需求。
                          </p>
                          <label>
                            确认每日总热量目标（kcal）
                            <input
                              name="daily_target_kcal"
                              type="number"
                              step="any"
                              min={preview.calculation.daily_kcal_range[0]}
                              max={preview.calculation.daily_kcal_range[1]}
                              value={target}
                              onChange={(e) => setTarget(e.target.value)}
                              placeholder="请在参考范围内明确选择"
                            />
                          </label>
                          <label>
                            确认每日零食目标（kcal）
                            <input
                              name="planned_treat_kcal"
                              type="number"
                              step="any"
                              min={0}
                              value={treatTarget}
                              onChange={(e) => setTreatTarget(e.target.value)}
                            />
                          </label>
                        </>
                      )}
                      <label>
                        餐次时间（逗号分隔）
                        <input
                          name="meal_times"
                          value={times}
                          onChange={(e) => setTimes(e.target.value)}
                          placeholder="08:00,18:00"
                        />
                      </label>
                      <p className="small muted">
                        账户时区 {user.timezone}；时间由你安排，可在保存前修改。
                      </p>
                      <Button
                        className="primary wide"
                        disabled={
                          action.busy ||
                          preview.urgent ||
                          (preview.status === "ready" && !target)
                        }
                        onClick={() => {
                          const payload = {
                            profile: structuredClone(profile),
                            revision: preview.revision,
                            preview_token: preview.preview_token,
                            daily_target_kcal:
                              preview.status === "ready"
                                ? Number(target)
                                : null,
                            planned_treat_kcal:
                              preview.status === "ready"
                                ? Number(treatTarget)
                                : 0,
                            meal_times: times.split(/[,，\s]+/).filter(Boolean),
                          };
                          action.run(async (key) => {
                            const result = await api<Plan>(
                              `/pets/${pet.id}/nutrition/plans`,
                              "POST",
                              payload,
                              key,
                            );
                            setSaved(result);
                            setPreview(null);
                            remote.reload();
                            plans.reload();
                          }, "资料与方案已保存，任务已加入站内提醒");
                        }}
                      >
                        {preview.status === "ready"
                          ? "保存资料与营养方案"
                          : "保存资料与非量化观察方案"}
                      </Button>
                      <details className="care-details">
                        <summary>计算依据与适用条件</summary>
                        <p>{preview.conditions}</p>
                        {preview.calculation && (
                          <p>
                            {preview.calculation.formula}；系数{" "}
                            {preview.calculation.factor_range.join("—")}。
                          </p>
                        )}
                        <p>
                          体重 {preview.weight ?? "未知"} kg，记录日期{" "}
                          {preview.weight_date
                            ? dateText(preview.weight_date, user.timezone)
                            : "未知"}
                          ；BCS {profile.bcs ?? "未知"}/9，肌肉状态{" "}
                          {profile.muscle === "normal"
                            ? "用户确认为正常"
                            : profile.muscle === "loss"
                              ? "有损失"
                              : "未知"}
                          ；评估 {profile.assessed_on ?? "未填写"}。
                        </p>
                        {preview.foods.map((f, i) => (
                          <p key={i}>
                            {f.name}：{fmt(f.kcal_per_gram)} kcal/g × 当前{" "}
                            {fmt(f.current_daily_grams)} g ={" "}
                            {fmt(f.current_kcal)} kcal；
                            {f.kind === "main" ? "主粮" : "零食"}。
                          </p>
                        ))}
                        <Sources items={preview.sources} />
                        <p className="small muted">
                          中文摘要未经兽医审核；食品标签和体况由用户填写。
                        </p>
                      </details>
                    </>
                  )}
                  {saved && (
                    <div className="care-saved">
                      <strong>{saved.title}</strong>
                      {saved.provenance?.amounts?.map((f, i) => (
                        <p key={i}>
                          {f.name}：每日约 {fmt(f.daily_grams)} g，每餐约{" "}
                          {fmt(f.per_meal_grams)} g
                        </p>
                      ))}
                      <Link to="/plans">
                        查看计划与打卡 <ArrowUpRight size={14} />
                      </Link>
                    </div>
                  )}
                </Panel>
                <div className="care-link-row">
                  <Link to="/hospitals#visit-summary">
                    <FileText size={17} />
                    准备就医资料
                  </Link>
                  <Link to="/knowledge?topic=饮食与体重">
                    了解营养知识 <ArrowUpRight size={14} />
                  </Link>
                </div>
              </div>
            </div>
          )}
        </>
      )}
    </>
  );
}

export function Hospitals() {
  const { pet } = useApp();
  const location = useLocation();
  const usage = useRemote<MapUsage>("/hospitals/usage");
  const regionsEnabled = usage.data?.region_enabled ?? usage.data?.enabled ?? false;
  const amapUsage = usage.data?.providers?.find(row => row.provider === "amap");
  const mapAvailable = amapUsage ? amapUsage.enabled && amapUsage.day_requests < amapUsage.day_limit && amapUsage.month_requests < amapUsage.month_limit : regionsEnabled;
  const action = useAction();
  const [city, setCity] = useState("");
  const [district, setDistrict] = useState("");
  const [cityRegion, setCityRegion] = useState<Region | null>(null);
  const [districtRegion, setDistrictRegion] = useState<Region | null>(null);
  const [street, setStreet] = useState("");
  const [addressDetail, setAddressDetail] = useState("");
  const [radius, setRadius] = useState(1);
  const [coords, setCoords] = useState<{
    longitude: number;
    latitude: number;
  } | null>(null);
  const [locationError, setLocationError] = useState("");
  const [locating, setLocating] = useState(false);
  const [result, setResult] = useState<HospitalResult | null>(null);
  const clearQuery = () => { setCoords(null); setResult(null); setLocationError(""); action.clear(); };
  const clearSmaller = () => { setStreet(""); setAddressDetail(""); };
  const locate = () => {
    action.clear();
    setLocationError("");
    setLocating(true);
    setCoords(null);
    setResult(null);
    if (!navigator.geolocation) {
      setLocationError("浏览器不支持定位，请输入城市和区县。");
      setLocating(false);
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (p) => {
        clearSmaller();
        setCoords({
          longitude: p.coords.longitude,
          latitude: p.coords.latitude,
        });
        setLocating(false);
      },
      () => {
        setLocationError("未取得定位，可输入城市和区县继续查询。");
        setLocating(false);
      },
      { enableHighAccuracy: false, timeout: 8000, maximumAge: 0 },
    );
  };
  return (
    <>
      <PageTitle
        title="医院查询"
        desc="中国大陆医院查询 · 自动综合可用地图资料"
      />
      {location.state?.urgent && (
        <div className="alert" role="alert">
          请立即联系兽医或宠物急诊，不要等待地图查询或资料完善。
        </div>
      )}
      <div className="care-hospital-layout">
        <Panel>
          <h2>
            <MapPin size={20} />
            你想在哪里找
          </h2>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              if (!coords && /省$|自治区$/.test(city.trim()) && !cityRegion) {
                setLocationError("请选择下方的具体城市，再查询医院。");
                return;
              }
              setLocationError("");
              const payload = {
                city,
                district,
                street,
                address_detail: addressDetail,
                region_adcode: districtRegion?.adcode ?? cityRegion?.adcode ?? null,
                ...coords,
                radius_km: radius,
                pet_id: pet?.id ?? null,
              };
              action.run(async () => {
                setResult(null);
                setResult(
                  await api<HospitalResult>(
                    "/hospitals/search",
                    "POST",
                    payload,
                  ),
                );
                usage.reload();
              }, "查询状态已返回，请查看结果");
            }}
          >
            <fieldset
              disabled={action.busy || locating}
              className="care-fieldset"
            >
              <div className="form-grid">
                <RegionInput label="城市" value={city} required={!coords} enabled={regionsEnabled}
                  onChange={value => { setCity(value); setCityRegion(null); setDistrict(""); setDistrictRegion(null); clearSmaller(); clearQuery(); }}
                  onSelect={region => { setCity(region.name); setCityRegion(region); setDistrict(""); setDistrictRegion(null); clearSmaller(); clearQuery(); }} />
                <RegionInput label="区县（可选）" value={district} city={city} parent={cityRegion} enabled={regionsEnabled}
                  onChange={value => { setDistrict(value); setDistrictRegion(null); clearSmaller(); clearQuery(); }}
                  onSelect={region => { setDistrict(region.name); setDistrictRegion(region); clearSmaller(); clearQuery(); }} />
                <RegionInput label="街道 / 乡镇（可选）" value={street} kind="street" city={district} parent={districtRegion} enabled={regionsEnabled && !!districtRegion}
                  onChange={value => { setStreet(value); setAddressDetail(""); clearQuery(); }}
                  onSelect={region => { setStreet(region.name); setAddressDetail(""); clearQuery(); }} />
                <div className="region-field">
                  <label htmlFor="hospital-address-detail">具体地点（可选）</label>
                  <input id="hospital-address-detail" name="address_detail" value={addressDetail} maxLength={160} placeholder="小区、路名或门牌，例如：XX路20号"
                    onChange={event => { setAddressDetail(event.target.value); clearQuery(); }} />
                  <p className="small muted region-hint">填写后查找此地点附近，不保存地址</p>
                </div>
              </div>
              <label>
                附近查询范围
                <select
                  name="radius_km"
                  aria-label="附近查询范围"
                  value={radius}
                  onChange={(e) => {
                    setRadius(Number(e.target.value));
                    setResult(null);
                    action.clear();
                  }}
                >
                  {[1, 3, 5, 10, 20].map((k) => (
                    <option key={k} value={k}>
                      {k} 公里
                    </option>
                  ))}
                </select>
              </label>
              <p className="small muted">选到区县仍是行政区查询；填写街道、具体地点或使用定位后，才按公里范围找附近医院。</p>
              <div className="button-row">
                <Button type="button" onClick={locate}>
                  <Navigation size={16} />
                  {locating ? "正在定位…" : "使用我的位置"}
                </Button>
                <Button className="primary" type="submit">
                  查询医院
                </Button>
              </div>
            </fieldset>
          </form>
          {coords && (
            <p className="small green-text">
              已取得定位；坐标仅用于本次查询，不保存。
            </p>
          )}
          {locationError && (
            <p role="alert" className="note">
              {locationError}
            </p>
          )}
          <Feedback action={action} />
          <State {...usage} retry={usage.reload} />
          {usage.data && !usage.data.enabled && (
            <p className="small muted">
              当前未启用地图接口。查询后可打开高德搜索，不会生成模拟医院。
            </p>
          )}
          <HospitalMap result={result} available={mapAvailable} onLoaded={usage.reload} />
          <p className="small muted">
            如有呼吸困难、昏倒或严重异常，请及时联系兽医；不要等待完善资料。
          </p>
        </Panel>
        <Panel className="hospital-results">
          <h2>{result?.items.length ? "查询到的医院候选" : "医院查询结果"}</h2>
          {!result && (
            <p className="muted">
              输入区域或授权定位后查询。电话、地址来自地图；急诊和具体物种接诊能力需要核实。
            </p>
          )}
          {result && (
            <>
              <p
                role="status"
                className={result.status === "unavailable" ? "note" : "muted"}
              >
                {result.message}
              </p>
              {result.mode === "external" && (
                <p className="small muted">
                  {result.provider_name ? `${result.provider_name}查询` : "外部地图查询"} ·{" "}
                  {new Date(result.queried_at).toLocaleString("zh-CN")}
                </p>
              )}
              {result.scope_label && <div className="hospital-search-scope"><p>查询范围：{result.scope_label}</p><p className="small muted">{result.scope_note}</p></div>}
              {result.agent_summary && <details className="care-details">
                <summary>综合依据与查询状态</summary>
                <p>{result.agent_summary.basis}</p>
                <p>确认合并 {result.agent_summary.merged_duplicates} 条重复登记；共取得 {result.agent_summary.unique_candidates} 家不同候选，本页最多展示 10 家。</p>
                {result.provider_results?.map(source => <p className="small muted" key={source.provider}>
                  {source.provider_name} · {source.status === "ok" ? `${source.item_count} 条候选` : source.status === "empty" ? "本次没有候选" : source.status === "skipped" ? "未调用" : "查询未完成"} · {source.message}
                  {source.scope_label && <> · {source.scope_label}</>}
                </p>)}
              </details>}
              {result.items.map((h, i) => (
                <article className="hospital-row" key={`${h.sources?.[0]?.provider || h.source}-${h.id || i}-${i}`}>
                  <div className="section-heading">
                    <h3>{h.map_number && <span className="hospital-map-number">{h.map_number}</span>}{h.name}</h3>
                    <span>
                      {h.distance_m === null
                        ? "距离未知"
                        : `${fmt(h.distance_m / 1000)} km（${h.distance_kind === "estimated" ? "坐标估算" : "地图距离"}）`}
                    </span>
                  </div>
                  <p>{h.address || "地址未提供"}</p>
                  <p className="small hospital-evidence">暂无可靠评分 <span>· {h.verification_status || "地图登记，未电话核实"}</span></p>
                  {h.sources && <p className="small muted">资料来自{h.sources.map(source => source.provider_name).join("、")}</p>}
                  {!!h.conflicts?.length && <p className="small note">登记信息存在差异，请展开核对各来源。</p>}
                  <p className="small muted">
                    {h.opening_hours || "营业时间未提供"} · {h.opening_status}
                  </p>
                  <p className="small muted">
                    急诊：{h.emergency} · 接诊物种：{h.species_capability} ·
                    资质：{h.qualification}
                  </p>
                  <div className="care-link-row">
                    {h.phone ? (
                      <a href={`tel:${h.phone}`}>
                        <Phone size={16} />
                        {h.phone}
                      </a>
                    ) : (
                      <span>电话未提供</span>
                    )}
                    <a href={h.navigation_url} target="_blank" rel="noreferrer">
                      <Navigation size={16} />
                      {h.navigation_label || "导航"}
                    </a>
                    <a href={h.map_url} target="_blank" rel="noreferrer">
                      查看地图
                    </a>
                  </div>
                  <details>
                    <summary>资料来源与匹配依据</summary>
                    <p>{h.match_reason}</p>
                    {h.registered_region && <p>登记区域：{h.registered_region}</p>}
                    {h.poi_type && <p>地图分类：{h.poi_type}</p>}
                    <p>{h.rating_note || "当前地图接口未提供可靠医院评分，不显示推测星级。"}</p>
                    <p>电话核实：当前是否营业并接诊、是否处理本次症状或接收急诊、接诊物种，以及收费项目、机构资质与医生执业信息。</p>
                    {h.sources ? h.sources.map((source, index) => <div key={`${source.provider}-${index}`}>
                      <p>{source.provider_name} · {new Date(source.queried_at).toLocaleString("zh-CN")}</p>
                      <p className="small muted">{source.address || "地址未提供"} · 电话：{source.phone || "未提供"} · 营业时间：{source.opening_hours || "未提供"}</p>
                      <a href={source.source_url} target="_blank" rel="noreferrer">{source.source}</a>
                    </div>) : <a href={h.source_url} target="_blank" rel="noreferrer">{h.source}</a>}
                    {h.conflicts?.map(conflict => <p className="small note" key={conflict}>{conflict}</p>)}
                  </details>
                </article>
              ))}
              <a
                className="care-map-link"
                href={result.search_url}
                target="_blank"
                rel="noreferrer"
              >
                {result.search_label || "打开高德搜索"} <ArrowUpRight size={16} />
              </a>
            </>
          )}
        </Panel>
      </div>
      <VisitEditor />
    </>
  );
}

function VisitEditor() {
  const { pet } = useApp();
  const location = useLocation();
  const action = useAction();
  const [open, setOpen] = useState(location.hash === "#visit-summary");
  const [observation, setObservation] = useState("");
  const [started, setStarted] = useState("");
  const [medicine, setMedicine] = useState("");
  const [summary, setSummary] = useState<VisitSummary | null>(null);
  const [text, setText] = useState("");
  const [copyStatus, setCopyStatus] = useState("");
  return (
    <Panel className="visit-panel">
      <details
        id="visit-summary"
        open={open}
        onToggle={(e) => setOpen(e.currentTarget.open)}
      >
        <summary>
          <FileText size={19} />
          准备就医资料
        </summary>
        {!pet ? (
          <NeedPet />
        ) : (
          <>
            <p className="muted">
              整理{pet.name}
              的档案与最近30天记录。先联系兽医，资料整理不应延迟就医。
            </p>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                const payload = {
                  observation,
                  started_at: started ? new Date(started).toISOString() : null,
                  medicines_as_reported: medicine,
                };
                action.run(async () => {
                  const s = await api<VisitSummary>(
                    `/pets/${pet.id}/visit-summary/preview`,
                    "POST",
                    payload,
                  );
                  setSummary(s);
                  setText(s.text);
                  setCopyStatus("");
                }, "摘要已生成，可编辑后复制或下载");
              }}
            >
              <fieldset disabled={action.busy} className="care-fieldset">
                <div className="form-grid">
                  <label>
                    症状开始时间（此设备当地时间）
                    <input
                      name="started_at"
                      type="datetime-local"
                      value={started}
                      onChange={(e) => setStarted(e.target.value)}
                    />
                  </label>
                  <label>
                    已用药信息（原样填写）
                    <input
                      name="medicines_as_reported"
                      value={medicine}
                      onChange={(e) => setMedicine(e.target.value)}
                      maxLength={2000}
                    />
                  </label>
                </div>
                <label>
                  本次观察
                  <textarea
                    name="observation"
                    value={observation}
                    onChange={(e) => setObservation(e.target.value)}
                    placeholder="例如起始、频率、精神、食欲和排泄变化；不知道可留空"
                    maxLength={3000}
                  />
                </label>
                <Button className="primary" type="submit">
                  生成就医摘要
                </Button>
              </fieldset>
            </form>
            <Feedback action={action} />
            {summary && (
              <>
                {summary.urgent && (
                  <div className="alert" role="alert">
                    请立即联系兽医或宠物急诊，不要等待资料完善。
                  </div>
                )}
                <label>
                  就医摘要（可编辑）
                  <textarea
                    name="text"
                    className="visit-summary-text"
                    value={text}
                    onChange={(e) => setText(e.target.value)}
                  />
                </label>
                <div className="button-row">
                  <Button
                    onClick={async () => {
                      try {
                        await navigator.clipboard.writeText(text);
                        setCopyStatus("已复制");
                      } catch {
                        setCopyStatus("复制失败，请选中摘要手动复制。");
                      }
                    }}
                  >
                    复制摘要
                  </Button>
                  <Button
                    onClick={() => {
                      const url = URL.createObjectURL(
                        new Blob([text], { type: "text/plain;charset=utf-8" }),
                      );
                      const a = document.createElement("a");
                      a.href = url;
                      a.download = "宠伴-就医摘要.txt";
                      a.click();
                      setTimeout(() => URL.revokeObjectURL(url), 1000);
                    }}
                  >
                    下载 TXT
                  </Button>
                </div>
                <p className="small" role="status">
                  {copyStatus}
                </p>
                <Sources items={summary.sources} />
                <p className="small muted">
                  未发送给医院。文本由本机生成，缺失信息不会被补造。
                </p>
              </>
            )}
          </>
        )}
      </details>
    </Panel>
  );
}
