import type { Source } from "./api";
export type Food = {
  name: string;
  kind: "main" | "treat";
  complete_adult_food: boolean | null;
  energy: number | null;
  energy_unit:
    | "kcal_100g"
    | "kcal_kg"
    | "kj_100g"
    | "kj_kg"
    | "kcal_portion"
    | "kj_portion";
  portion_grams: number | null;
  daily_grams: number | null;
  label_note: string;
};
export type NutritionData = {
  life_stage: "adult" | "growing" | "senior" | "unknown";
  bcs: number | null;
  muscle: "normal" | "loss" | "unknown";
  assessed_on: string | null;
  assessor: "owner" | "vet" | "unknown";
  activity_level: "low" | "normal" | "high" | "unknown";
  health_status: "healthy" | "unwell" | "unknown";
  pregnancy_lactation: "no" | "yes" | "unknown";
  diet_restrictions: string;
  current_symptoms: string;
  weight_confirmed: boolean;
  treats_confirmed: boolean;
  food_shares_confirmed: boolean;
  foods: Food[];
};
export type NutritionProfile = {
  profile: NutritionData;
  revision: number;
  active_plan_id: string | null;
  needs_reassessment: boolean;
};
export type NutritionPreview = {
  status: "ready" | "needs_info" | "professional_required";
  revision: number;
  preview_token: string;
  sources: Source[];
  urgent: boolean;
  questions: string[];
  warnings: string[];
  conditions: string;
  weight: number | null;
  weight_date: string | null;
  calculation: null | {
    rer_kcal: number;
    daily_kcal_range: [number, number];
    current_kcal: number;
    current_treat_kcal: number;
    formula: string;
    factor_range: [number, number];
  };
  foods: {
    name: string;
    kind: string;
    current_daily_grams: number;
    current_kcal: number;
    kcal_per_gram: number;
    calorie_share?: number;
    reference_grams_range?: [number, number];
  }[];
};
export type HospitalItem = {
  id: string;
  name: string;
  address: string;
  phone: string;
  distance_m: number | null;
  opening_hours: string;
  opening_status: string;
  emergency: string;
  species_capability: string;
  qualification: string;
  source: string;
  source_url: string;
  map_url: string;
  navigation_url: string;
  match_reason: string;
};
export type HospitalResult = {
  mode: "map_link" | "external";
  status: "ok" | "empty" | "unavailable";
  items: HospitalItem[];
  message: string;
  search_url: string;
  queried_at: string;
};
export type MapUsage = {
  enabled: boolean;
  day_requests: number;
  month_requests: number;
  day_limit: number;
  month_limit: number;
  note: string;
};
export type VisitSummary = {
  text: string;
  sources: Source[];
  urgent: boolean;
  mode: string;
};
export type ActionCard = {
  type: "nutrition" | "hospitals" | "visit_summary" | "products" | "knowledge";
  title: string;
  href: string;
  text?: string;
  status?: string;
};
