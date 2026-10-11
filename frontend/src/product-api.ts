import { token } from "./api";
import type { Pet, Source } from "./api";
export type Breed = {id: string; species: string; name: string; summary: string; classification: string; article_id: string; aliases: string[]};
export type BreedList = {items: Breed[]; note: string; requires_confirmation: boolean};
export type AnalysisValue = {nutrient: string; value: number | null; qualifier: "min" | "max" | "typical"; unit: "percent"};
export type Product = {
  name: string; brand: string; formula: string; market_version: string;
  target_species: ("cat" | "dog")[]; life_stage: "adult" | "growing" | "senior" | "all" | "unknown";
  adequacy: "complete" | "complement" | "unknown"; adequacy_statement: string;
  energy: number | null; energy_unit: "kcal_100g" | "kcal_kg" | "kj_100g" | "kj_kg" | "kcal_portion" | "kj_portion";
  portion_grams: number | null; net_grams: number | null; daily_grams: number | null;
  price: number | null; price_date: string | null; currency: "CNY" | "USD" | "EUR" | "HKD";
  ingredients: string; analysis: AnalysisValue[]; processing: "cooked" | "raw" | "unknown"; therapeutic: boolean;
  material: string; dimensions: string; size_confirmed: boolean | null; cleaning_method: string; warnings: string;
  expected_lifetime_months: number | null; monthly_consumables: number | null;
  manufacturer_evidence: string; source_note: string; raw_label: string; origin: "manual" | "ocr"; label_confirmed: boolean;
};
export const categories: Record<string,string> = {main:"主粮", complement:"补充食品", treat:"零食", bowls:"食水器具", litter:"猫砂与砂盆", carriers:"航空箱与笼箱", beds:"窝垫", scratch:"抓挠攀爬", toys:"互动与啃咬玩具", harness:"牵引与胸背", grooming:"梳洗工具", dental:"口腔用品", cleaning:"环境清洁"};
export type AssessmentInputs = {pet_id: string | null; species: "cat" | "dog"; category: string; products: Product[]};
export type Assessment = {preview_token:string; rule_version:string; evaluated_at:string; origin:string; note:string; context:{pet:Pet | null; nutrition_revision:number}; sources: Source[];
  products: {name:string;status:string;status_label:string;strengths:string[];risks:string[];missing:string[];analysis:AnalysisValue[];origin:string;provenance:string;
    costs:{currency:string;price_date:string|null;per_100g:number|null;per_100kcal:number|null;daily:number|null;monthly:number|null;monthly_ownership:number|null;basis:string[]}}[]};
export type SavedAssessment = {id:string;created_at:string;pet_id:string|null;inputs:AssessmentInputs;result:Assessment};
export type AssessmentHistory = {id:string;pet_id:string|null;created_at:string;category:string;names:string[];rule_version:string};
export type OCRStatus = {available:boolean;message:string;engine:string;timeout_seconds:number};
export type OCRResult = {status:string;raw_text:string;message:string;suggestions:Partial<Product>;images:{lines:{text:string;confidence:number;needs_review:boolean}[]}[]};
export function blankProduct(): Product {return {name:"",brand:"",formula:"",market_version:"",target_species:[],life_stage:"unknown",adequacy:"unknown",adequacy_statement:"",energy:null,energy_unit:"kcal_100g",portion_grams:null,net_grams:null,daily_grams:null,price:null,price_date:null,currency:"CNY",ingredients:"",analysis:[],processing:"unknown",therapeutic:false,material:"",dimensions:"",size_confirmed:null,cleaning_method:"",warnings:"",expected_lifetime_months:null,monthly_consumables:null,manufacturer_evidence:"",source_note:"用户提供的包装资料，未经厂家核实",raw_label:"",origin:"manual",label_confirmed:false};}
export async function recognizePackaging(files: File[], signal?:AbortSignal):Promise<OCRResult> {
  const form = new FormData(); files.forEach(file=>form.append("files",file));
  const response = await fetch("/api/v1/products/ocr",{method:"POST",headers:{Authorization:"Bearer "+token()},body:form,signal});
  if(response.status===401){sessionStorage.removeItem("chongban_token");window.dispatchEvent(new Event("auth-expired"));}
  const result = await response.json();
  if(!response.ok)throw new Error(typeof result.detail === "string" ? result.detail : "识别失败，请重试或手动输入");
  return result;
}
