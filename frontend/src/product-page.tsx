import {useEffect, useRef, useState} from "react";
import {Link, useNavigate} from "react-router-dom";
import {ArrowUpRight, Plus, Trash2, ScanText} from "lucide-react";
import {useApp} from "./App";
import {api, dateText} from "./api";
import {useAction, useRemote} from "./hooks";
import {Button} from "./components/ui/button";
import {Panel, PageTitle, State, Feedback, Sources, Empty} from "./components";
import {blankProduct, categories, recognizePackaging, type Product, type OCRStatus, type OCRResult, type Assessment, type AssessmentInputs, type SavedAssessment, type AssessmentHistory} from "./product-api";

const units:Record<string,string>={kcal_100g:"kcal / 100g",kcal_kg:"kcal / kg",kj_100g:"kJ / 100g",kj_kg:"kJ / kg",kcal_portion:"kcal / 份",kj_portion:"kJ / 份"};
const foodCategories=["main","complement","treat"];
function ProductEditor({product:p,index,food,ocr,onChange,onRemove,busy,onProcessing}:{product:Product;index:number;food:boolean;ocr:OCRStatus|null;onChange:(patch:Partial<Product>)=>void;onRemove:()=>void;busy:boolean;onProcessing:(busy:boolean)=>void}){
  const [ocrResult,setOCRResult]=useState<OCRResult|null>(null), [ocrError,setOCRError]=useState(""),[ocrBusy,setOCRBusy]=useState(false);
  const filesRef=useRef<File[]>([]), controller=useRef<AbortController|null>(null);
  const uploadRef=useRef<HTMLInputElement|null>(null),[selectedImages,setSelectedImages]=useState(0);
  useEffect(()=>()=>controller.current?.abort(),[]);
  const identify=async(files:File[])=>{
    if(!files.length)return;
    filesRef.current=files;setSelectedImages(files.length);setOCRError("");setOCRBusy(true);onProcessing(true);controller.current=new AbortController();
    try{
      if(files.length>3 || files.some(f=>f.size>5*1024*1024))throw new Error("每次最多3张，每张最多5 MB。");
      const result=await recognizePackaging(files,controller.current.signal);
      if(controller.current.signal.aborted)return;
      setOCRResult(result);onChange({...result.suggestions,raw_label:result.raw_text,origin:"ocr",label_confirmed:false});
      filesRef.current=[];
    }catch(e){if((e as Error).name!=="AbortError")setOCRError((e as Error).message || "识别连接失败，请重试或手动输入。");}
    finally{setOCRBusy(false);onProcessing(false);}
  };
  function text(key:keyof Product,label:string,required=false,area=false){return <label>{label}{area?<textarea required={required} value={String(p[key]??"")} maxLength={key==="raw_label"?12000:2000} onChange={e=>onChange({[key]:e.target.value})}/>:<input required={required} maxLength={160} value={String(p[key]??"")} onChange={e=>onChange({[key]:e.target.value})}/>}</label>;}
  function number(key:keyof Product,label:string,min=0,required=false){return <label>{label}<input type="number" step="any" min={min} required={required} value={p[key]===null?"":String(p[key])} onChange={e=>onChange({[key]:e.target.value===""?null:Number(e.target.value)})}/></label>;}
  return <fieldset className="product-editor" disabled={busy || ocrBusy}>
    <legend>产品 {index+1}{p.name ? " · "+p.name : ""}</legend>
    <div className="section-heading"><p className="muted small">按包装填写，未知内容留空。</p><Button type="button" onClick={onRemove}><Trash2 size={14}/>移除产品</Button></div>
    <div className="form-grid">{text("name","名称",true)}{text("brand","品牌")}{text("formula",food?"具体配方":"型号 / 规格")}{text("market_version","销售市场 / 标签版本")}</div>
    <div className="packaging-input">
      <div className="section-heading"><h3><ScanText size={18}/>包装资料</h3><span className="badge quiet">{p.origin === "ocr" ? "本地识别后核对" : "手动输入"}</span></div>
      <p className="small muted">可粘贴标签，也可上传清晰包装图片。图片用于当次本地识别，不写入照护记录。</p>
      {ocr?.available?<div className="upload-label"><p className="small">上传包装图片（最多3张）</p><div className="button-row"><Button type="button" onClick={()=>uploadRef.current?.click()}>选择包装图片</Button><span className="small muted" aria-live="polite">{selectedImages?"已选择 "+selectedImages+" 张图片":"尚未选择图片"}</span></div><input ref={uploadRef} hidden aria-label="上传包装图片（最多3张）" type="file" accept="image/jpeg,image/png,image/webp" multiple onChange={e=>{void identify(Array.from(e.target.files||[]));e.target.value="";}}/></div>:<p className="note">{ocr?.message || "正在检查本地识别…"} 手动输入仍可使用。</p>}
      {ocrBusy && <p role="status">正在本地识别，请稍候…</p>}
      {ocrError && <div className="alert" role="alert"><span>{ocrError}</span><Button type="button" disabled={ocrBusy} onClick={()=>void identify(filesRef.current)}>重试识别</Button></div>}
      {text("raw_label","包装文字（可粘贴或修正识别结果）",false,true)}
      <Button type="button" disabled={!p.raw_label.trim()} onClick={async()=>{onProcessing(true);setOCRBusy(true);try{const r=await api<{suggestions:Partial<Product>}>("/products/label/parse","POST",{raw_text:p.raw_label});onChange(r.suggestions);setOCRError("");}catch(e){setOCRError((e as Error).message);}finally{onProcessing(false);setOCRBusy(false);}}}>从文字提取候选数值</Button>
      {ocrResult && <details className="product-details"><summary>识别结果与置信度</summary><p>{ocrResult.message}</p>{ocrResult.images.map((frame,i)=><ul key={i}>{frame.lines.map((line,j)=><li key={j}>{line.text} · {Math.round(line.confidence*100)}%{line.needs_review ? " · 请重点核对" : ""}</li>)}</ul>)}</details>}
    </div>
    <h3>适用对象</h3>
    <div className="form-grid"><label>包装适用物种<select value={p.target_species.length===2?"both":p.target_species[0]||""} onChange={e=>onChange({target_species:e.target.value==="both"?["cat","dog"]:e.target.value?[e.target.value as "cat"|"dog"]:[]})}><option value="">未标明 / 待确认</option><option value="cat">猫</option><option value="dog">狗</option><option value="both">明确适用猫与狗</option></select></label>
      {food?<label>食品适用阶段<select value={p.life_stage} onChange={e=>onChange({life_stage:e.target.value as Product["life_stage"]})}><option value="unknown">未知</option><option value="adult">成年维持</option><option value="growing">成长</option><option value="senior">老年</option><option value="all">标签明确的全部阶段</option></select></label>:<label>尺寸或用途已实测确认<select value={p.size_confirmed===null?"":String(p.size_confirmed)} onChange={e=>onChange({size_confirmed:e.target.value===""?null:e.target.value==="true"})}><option value="">尚未确认</option><option value="true">已核对，匹配</option><option value="false">已核对，不匹配</option></select></label>}
    </div>
    {food?<>
      <div className="form-grid"><label>完整 / 补充性食品<select value={p.adequacy} onChange={e=>onChange({adequacy:e.target.value as Product["adequacy"]})}><option value="unknown">未知</option><option value="complete">包装声明完整食品</option><option value="complement">补充性食品</option></select></label><label>加工方式<select value={p.processing} onChange={e=>onChange({processing:e.target.value as Product["processing"]})}><option value="unknown">未知</option><option value="cooked">厂家标明熟制 / 加热</option><option value="raw">生食或生食冻干</option></select></label></div>
      {text("adequacy_statement","营养适用声明原文",false,true)}
      <div className="form-grid">{number("energy","包装热量",0.000001)}<label>热量单位<select value={p.energy_unit} onChange={e=>onChange({energy_unit:e.target.value as Product["energy_unit"]})}>{Object.entries(units).map(([key,label])=><option key={key} value={key}>{label}</option>)}</select></label>
      {p.energy_unit.endsWith("portion")&&number("portion_grams","每份克重（g）",0.000001)}{number("net_grams","净含量（g）",0.000001)}{number("daily_grams","已确认实际每日摄入（g，未知留空）")}</div>
      <details className="product-details"><summary>配料、保证分析与专业限制</summary>
        {text("ingredients","配料原文",false,true)}
        <h4>保证分析（保留最小 / 最大值）</h4>
        {p.analysis.map((a,i)=><div className="analysis-row" key={i}><label>营养项<input required value={a.nutrient} onChange={e=>onChange({analysis:p.analysis.map((v,j)=>j===i?{...v,nutrient:e.target.value}:v)})}/></label><label>性质<select value={a.qualifier} onChange={e=>onChange({analysis:p.analysis.map((v,j)=>j===i?{...v,qualifier:e.target.value as typeof v.qualifier}:v)})}><option value="min">最小值 ≥</option><option value="max">最大值 ≤</option><option value="typical">厂家典型值</option></select></label><label>百分比<input required type="number" min={0} max={100} step="any" value={a.value??""} onChange={e=>onChange({analysis:p.analysis.map((v,j)=>j===i?{...v,value:e.target.value===""?null:Number(e.target.value)}:v)})}/></label><Button type="button" onClick={()=>onChange({analysis:p.analysis.filter((_,j)=>j!==i)})}>移除此项</Button></div>)}
        <Button type="button" disabled={p.analysis.length>=12} onClick={()=>onChange({analysis:[...p.analysis,{nutrient:"",qualifier:"min",unit:"percent",value:null}]})}>添加营养项</Button>
        <label className="care-check"><input type="checkbox" checked={p.therapeutic} onChange={e=>onChange({therapeutic:e.target.checked})}/>处方 / 治疗用途，需专业核对</label>
      </details>
    </>:<div className="form-grid">{text("material","材料标注")}{text("dimensions","尺寸 / 承重 / 用途规格")}{text("cleaning_method","清洁方法",false,true)}{text("warnings","使用警示",false,true)}</div>}
    <details className="product-details"><summary>价格、持续成本与资料来源</summary><div className="form-grid">{number("price","实际价格",0.000001)}<label>币种<select value={p.currency} onChange={e=>onChange({currency:e.target.value as Product["currency"]})}>{["CNY","USD","EUR","HKD"].map(c=><option key={c}>{c}</option>)}</select></label><label>价格日期<input type="date" value={p.price_date||""} onChange={e=>onChange({price_date:e.target.value||null})}/></label>
      {!food && <>{number("expected_lifetime_months","预计使用寿命（月，仅为假设）",0.000001)}{number("monthly_consumables","预计每月耗材支出")}</>}</div>{text("manufacturer_evidence","厂家配方、质量控制或研究资料（可附来源）",false,true)}{text("source_note","资料出处与未核实信息",false,true)}</details>
    <label className="care-check product-confirm"><input type="checkbox" checked={p.label_confirmed} onChange={e=>onChange({label_confirmed:e.target.checked})}/>我已核对产品资料，尤其是数值、单位、净含量和适用声明；未知项已留空</label>
    <p className="small muted">用户确认不等于厂家资料已核实。</p>
  </fieldset>;
}

export function Products(){
  const {pet,user}=useApp(), navigate=useNavigate(), action=useAction();
  const [species,setSpecies]=useState<"cat"|"dog">(pet?.species === "dog"?"dog":"cat"),[category,setCategory]=useState("main"),[products,setProducts]=useState<Product[]>([blankProduct()]);
  const [preview,setPreview]=useState<Assessment|null>(null),[saved,setSaved]=useState<SavedAssessment|null>(null),[readOnly,setReadOnly]=useState(false);
  const [processing,setProcessing]=useState(false);
  const busy=action.busy || processing;
  const ocr=useRemote<OCRStatus>("/products/ocr/status"),history=useRemote<AssessmentHistory[]>("/products/assessments"+(pet?"?pet_id="+pet.id:""));
  const supported=!pet || ["cat","dog"].includes(pet.species);
  const clearResult=()=>{setPreview(null);setSaved(null);setReadOnly(false);};
  const inputs=():AssessmentInputs=>({pet_id:pet?.id||null,species,category,products});
  function change(i:number,patch:Partial<Product>){setProducts(all=>all.map((p,j)=>j===i?{...p,...patch,label_confirmed:patch.label_confirmed!==undefined?patch.label_confirmed:false}:p));clearResult();}
  const shown=readOnly?saved?.result:preview;
  return <>
    <Link className="back-link" to="/knowledge">← 返回知识库</Link>
    <PageTitle eyebrow="PRODUCTS" title="挑选适合它的食物与用品" desc={pet?"结合 "+pet.name+" 的档案，核对具体配方与规格。":"未选择宠物，提供猫狗通用选购比较。"}/>
    <Feedback action={action}/>
    {!supported?<Empty>当前物种暂不支持产品评估，不能套用猫狗标准。</Empty>:<>
      <Panel className="product-context"><div className="form-grid"><label>比较物种<select value={species} disabled={!!pet || busy} onChange={e=>{setSpecies(e.target.value as "cat"|"dog");clearResult();}}><option value="cat">猫</option><option value="dog">狗</option></select></label><label>比较类别<select value={category} disabled={busy || readOnly} onChange={e=>{setCategory(e.target.value);setProducts(all=>all.map(p=>({...p,label_confirmed:false})));clearResult();}}>{Object.entries(categories).map(([key,label])=><option key={key} value={key}>{label}</option>)}</select></label></div><p className="small muted">一次比较1—3个同类产品。资料和计算留在本地，不生成品牌排名。</p></Panel>
      <State {...ocr} retry={ocr.reload}/>
      {readOnly && <div className="note">正在查看历史快照：{dateText(saved!.created_at,user.timezone)} · {saved!.result.context.pet?.name||"普通知识"}。它不代表当前状态。<Button onClick={()=>{setPreview(null);setSaved(null);setReadOnly(false);}}>用这些资料重新比较</Button></div>}
      {!readOnly && <form onSubmit={e=>{e.preventDefault();action.run(async()=>{const result=await api<Assessment>("/products/assessments/preview","POST",inputs());setPreview(result);setSaved(null);},"本地比较已完成，尚未保存");}}>
        {products.map((p,i)=><ProductEditor key={i} product={p} index={i} food={foodCategories.includes(category)} ocr={ocr.data} busy={busy} onProcessing={setProcessing} onChange={patch=>change(i,patch)} onRemove={()=>{if(products.length===1)setProducts([blankProduct()]);else setProducts(all=>all.filter((_,j)=>j!==i));clearResult();}}/>)}
        <div className="button-row product-form-actions"><Button type="button" disabled={products.length>=3 || busy} onClick={()=>{setProducts(all=>[...all,blankProduct()]);clearResult();}}><Plus size={16}/>添加同类产品</Button><Button type="submit" className="primary" disabled={busy || products.some(p=>!p.label_confirmed || !p.name.trim())}>核对并比较</Button></div>
      </form>}
      {shown && <Panel className="assessment-result"><div className="section-heading"><h2>{readOnly?"历史比较":"比较结果"}</h2><span className="badge green">本地规则计算</span></div><p className="small muted">{dateText(shown.evaluated_at,user.timezone)} · {shown.context.pet?.name||"未选择宠物"} · {shown.rule_version}</p>
        <div className="assessment-columns">{shown.products.map((p,i)=><section className="assessment-column" key={i}><h3>{p.name}</h3><strong className={"assessment-status status-"+p.status}>{p.status_label}</strong>
          {[["已知优点",p.strengths],["风险与条件",p.risks],["需要补充",p.missing]].map(([label,list])=>(list as string[]).length>0&&<div key={label as string}><h4>{label as string}</h4><ul>{(list as string[]).map(item=><li key={item}>{item}</li>)}</ul></div>)}
          <h4>成本 · {p.costs.currency}</h4><dl className="product-costs">{[["每100克",p.costs.per_100g],["每100kcal",p.costs.per_100kcal],["每日本产品",p.costs.daily],["每30天本产品",p.costs.monthly],["用品月摊销",p.costs.monthly_ownership]].map(([label,value])=><div key={String(label)}><dt>{String(label)}</dt><dd>{value===null?"资料不足":Number(value).toFixed(2)}</dd></div>)}</dl>
          <details className="product-details"><summary>计算依据与资料性质</summary><p>价格日期：{p.costs.price_date||"未知"}</p>{p.costs.basis.map(x=><p key={x}>{x}</p>)}<p>{p.provenance}</p>{p.analysis.map((a,j)=><p key={j}>{a.nutrient} {a.qualifier==="min"?"≥":a.qualifier==="max"?"≤":"典型值"}{a.value}%</p>)}</details>
          {saved && !readOnly && pet && ["main","treat"].includes(category) && <Button disabled={busy || ["incompatible","professional","caution"].includes(p.status)} onClick={()=>{if(window.confirm("将这个食品添加到营养资料？现有计划与喂食量不会自动改变，随后需要补充摄入并重新评估。"))action.run(async key=>{await api("/products/assessments/"+saved.id+"/nutrition-food","POST",{product_index:i,revision:shown.context.nutrition_revision,confirm:true},key);navigate("/nutrition");},"食品资料已添加");}}>添加到营养资料</Button>}
        </section>)}</div><p className="note">{shown.note}</p><Sources items={shown.sources}/>
        {!readOnly && <div className="button-row"><Button className="primary" disabled={busy || !!saved} onClick={()=>action.run(async key=>{const row=await api<SavedAssessment>("/products/assessments","POST",{inputs:inputs(),preview_token:shown.preview_token,confirm:true},key);setSaved(row);history.reload();},"比较已保存")}>{saved?"已保存比较":"明确保存这次比较"}</Button><Link className="care-link" to="/nutrition">营养资料与重新评估 <ArrowUpRight size={14}/></Link></div>}
      </Panel>}
      <Panel><h2>保存的比较</h2><State {...history} retry={history.reload}/>{history.data?.length===0?<p className="muted">还没有保存的比较。先录入资料并预览结果。</p>:history.data?.map(row=><div className="comparison-history" key={row.id}><div><strong>{row.names.join(" / ")}</strong><small>{categories[row.category]} · {dateText(row.created_at,user.timezone)}</small></div><div className="button-row"><Button disabled={busy} onClick={()=>action.run(async()=>{const detail=await api<SavedAssessment>("/products/assessments/"+row.id);setSaved(detail);setReadOnly(true);setSpecies(detail.inputs.species);setCategory(detail.inputs.category);setProducts(detail.inputs.products);setPreview(null);},"已读取历史快照")}>查看</Button><Button disabled={busy} className="danger-text" onClick={()=>{if(window.confirm("删除这次保存的比较？"))action.run(async()=>{await api("/products/assessments/"+row.id,"DELETE");if(saved?.id===row.id)clearResult();history.reload();},"比较已删除");}}>删除</Button></div></div>)}</Panel>
    </>}
  </>;
}
