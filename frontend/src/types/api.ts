// Mirrors backend/app/schemas. Field names stay in snake_case so they read the same on both sides.

export type DataProvenance = "live" | "cached" | "simulated" | "unavailable";
export type RiskLevel = "low" | "moderate" | "elevated" | "uncertain" | "not_applicable";
export type Confidence = "insufficient" | "limited" | "moderate" | "good" | "not_applicable";
export type IrrigationStatus = "favorable" | "monitor" | "caution" | "insufficient_information";
export type IrrigationAction =
  | "consider_irrigating"
  | "consider_postponing"
  | "check_soil_and_reassess"
  | "hold_irrigation"
  | "cannot_assess";
export type FactorDirection = "supports_irrigating" | "against_irrigating" | "neutral" | "unknown";
export type Intent =
  | "irrigation_advice"
  | "weather_question"
  | "pest_disease_risk"
  | "field_operation"
  | "crop_guidance"
  | "farm_briefing"
  | "general"
  | "out_of_scope";
export type SoilMoisture = "low" | "adequate" | "high" | "unknown";
export type RecommendationOrigin =
  | "assistant"
  | "irrigation_advisor"
  | "crop_health"
  | "scenario_lab";

export interface SourceRef {
  id: string;
  title: string;
  publisher: string;
  url: string;
}

// Session

export interface User {
  id: string;
  display_name: string | null;
  preferred_language: string;
  created_at: string;
}

export interface GuestSession {
  token: string;
  user: User;
}

export interface Health {
  status: "ok" | "degraded";
  version: string;
  environment: string;
  database: "ok" | "unavailable";
  weather_configured: boolean;
  ai_configured: boolean;
  ai_model: string | null;
}

// Crop catalogue

export interface CropStage {
  id: string;
  label: string;
  irrigation_critical: boolean;
  note: string | null;
}

export interface CatalogCrop {
  id: string;
  name: string;
  support_level: "rules_implemented" | "planned";
  support_note: string;
  stages: CropStage[];
  irrigation_considerations: string[];
  sources: SourceRef[];
}

export interface Catalog {
  crops: CatalogCrop[];
  soil_types: string[];
  irrigation_methods: string[];
  soil_moisture_levels: string[];
  area_units: string[];
}

// Farms

export interface IrrigationWindow {
  number: number;
  start_date: string;
  end_date: string;
  basis: string;
}

export interface IrrigationSchedule {
  sowing_date: string;
  days_after_sowing: number;
  windows: IrrigationWindow[];
  last_irrigation_by: string;
  next_window: IrrigationWindow | null;
  in_window: IrrigationWindow | null;
  source_id: string;
}

export interface FarmCrop {
  id: string;
  farm_id: string;
  crop: string;
  crop_name: string;
  support_level: string;
  variety: string | null;
  sowing_date: string | null;
  growth_stage: string | null;
  growth_stage_label: string | null;
  irrigation_method: string | null;
  irrigation_schedule: IrrigationSchedule | null;
  created_at: string;
}

export interface Farm {
  id: string;
  name: string | null;
  location_name: string | null;
  state: string | null;
  country: string | null;
  latitude: number | null;
  longitude: number | null;
  size_value: number | null;
  area_unit: string | null;
  soil_type: string | null;
  crops: FarmCrop[];
  created_at: string;
  updated_at: string;
}

export interface FarmCropInput {
  crop?: string;
  variety?: string | null;
  sowing_date?: string | null;
  growth_stage?: string | null;
  irrigation_method?: string | null;
}

export interface FarmInput {
  name?: string | null;
  location_name?: string | null;
  state?: string | null;
  country?: string | null;
  latitude?: number | null;
  longitude?: number | null;
  size_value?: number | null;
  area_unit?: string | null;
  soil_type?: string | null;
  crops?: FarmCropInput[];
}

// Weather

export interface WeatherMeta {
  provenance: DataProvenance;
  source: string;
  observed_at: string | null;
  fetched_at: string | null;
  age_seconds: number | null;
  is_stale: boolean;
  warning: string | null;
}

export interface CurrentWeather {
  latitude: number;
  longitude: number;
  location_name: string | null;
  temperature_c: number;
  feels_like_c: number | null;
  humidity_pct: number;
  description: string | null;
  icon: string | null;
  wind_speed_ms: number | null;
  wind_gust_ms: number | null;
  wind_direction_deg: number | null;
  cloud_cover_pct: number | null;
  rain_last_1h_mm: number | null;
  rain_last_3h_mm: number | null;
  observed_at: string;
  timezone_offset_seconds: number;
  meta: WeatherMeta;
}

export interface ForecastPoint {
  time: string;
  temperature_c: number;
  feels_like_c: number | null;
  humidity_pct: number;
  wind_speed_ms: number | null;
  wind_gust_ms: number | null;
  cloud_cover_pct: number | null;
  rain_mm: number;
  rain_probability_pct: number;
  description: string | null;
}

export interface DailyForecast {
  date: string;
  temp_min_c: number;
  temp_max_c: number;
  humidity_mean_pct: number;
  wind_max_ms: number | null;
  rain_total_mm: number;
  rain_probability_max_pct: number;
  description: string | null;
  periods: number;
}

export interface Forecast {
  latitude: number;
  longitude: number;
  location_name: string | null;
  timezone_offset_seconds: number;
  resolution_hours: number;
  horizon_hours: number;
  hourly: ForecastPoint[];
  daily: DailyForecast[];
  meta: WeatherMeta;
}

export interface GeocodeResult {
  name: string;
  state: string | null;
  country: string | null;
  latitude: number;
  longitude: number;
  timezone_offset_seconds?: number | null;
}

export interface WeatherSnapshot {
  provenance: DataProvenance;
  source: string;
  observed_at: string | null;
  is_stale: boolean;
  warning: string | null;
  location_name: string | null;
  latitude: number | null;
  longitude: number | null;
  description: string | null;
  temperature_c: number | null;
  feels_like_c: number | null;
  humidity_pct: number | null;
  wind_speed_ms: number | null;
  rain_last_1h_mm: number | null;
  forecast_available: boolean;
  rain_next_24h_mm: number | null;
  rain_next_48h_mm: number | null;
  rain_prob_max_24h_pct: number | null;
  rain_prob_max_48h_pct: number | null;
  temp_max_48h_c: number | null;
  temp_min_48h_c: number | null;
  humidity_mean_48h_pct: number | null;
  wind_max_24h_ms: number | null;
  et0_mm_day: number | null;
}

// Assessments

export interface DecisionFactor {
  key: string;
  label: string;
  value: string;
  direction: FactorDirection;
  weight: number;
  explanation: string;
  source_ids: string[];
}

export interface IrrigationAssessment {
  crop: string;
  crop_name: string;
  growth_stage: string | null;
  growth_stage_label: string | null;
  status: IrrigationStatus;
  action: IrrigationAction;
  headline: string;
  summary: string;
  next_action: string;
  next_steps: string[];
  factors: DecisionFactor[];
  supporting_factors: string[];
  missing_information: string[];
  limitations: string[];
  score: number;
  risk_level: RiskLevel;
  confidence: Confidence;
  confidence_note: string;
  estimated_crop_water_use_mm_day: number | null;
  schedule: IrrigationSchedule | null;
  weather_provenance: DataProvenance;
  sources: SourceRef[];
}

export interface PotentialRisk {
  id: string;
  name: string;
  category: string;
  classification: RiskLevel;
  favorable_conditions: string;
  evidence: string[];
  monitoring_actions: string[];
  regional_note: string | null;
  sources: SourceRef[];
}

export interface PestRiskAssessment {
  crop: string;
  crop_name: string;
  growth_stage: string | null;
  growth_stage_label: string | null;
  overall_classification: RiskLevel;
  headline: string;
  explanation: string;
  risks: PotentialRisk[];
  environmental_conditions: { label: string; value: string }[];
  crop_sensitivity: string;
  missing_information: string[];
  confidence: Confidence;
  confidence_note: string;
  disclaimer: string;
  weather_provenance: DataProvenance;
}

export interface WeatherContext {
  temperature_c: number | null;
  humidity_pct: number | null;
  rain_probability_pct: number | null;
  expected_rain_mm: number | null;
  window_hours: number;
  wind_speed_ms: number | null;
  description: string | null;
  location_name: string | null;
  provenance: DataProvenance;
  source: string;
  observed_at: string | null;
  is_stale: boolean;
}

export interface FarmingAdvice {
  intent: Intent;
  recommendation: string | null;
  summary: string;
  reasoning: string[];
  weather_context: WeatherContext | null;
  risk_level: RiskLevel;
  confidence: Confidence;
  missing_information: string[];
  next_steps: string[];
  data_sources: string[];
  requires_expert_verification: boolean;
  generated_by: string;
}

export interface ApiIssue {
  code: string;
  message: string;
}

export interface IrrigationResponse {
  assessment: IrrigationAssessment;
  advice: FarmingAdvice;
  weather: WeatherSnapshot | null;
  weather_issues: ApiIssue[];
  farm_id: string | null;
}

export interface PestRiskResponse {
  assessment: PestRiskAssessment;
  advice: FarmingAdvice;
  weather: WeatherSnapshot | null;
  weather_issues: ApiIssue[];
  farm_id: string | null;
}

export interface AssessmentTarget {
  farm_id?: string | null;
  farm_crop_id?: string | null;
  latitude?: number | null;
  longitude?: number | null;
  crop?: string | null;
  growth_stage?: string | null;
  force_refresh?: boolean;
}

export interface IrrigationRequest extends AssessmentTarget {
  soil_type?: string | null;
  soil_moisture?: SoilMoisture;
  irrigation_method?: string | null;
  recent_rainfall_mm?: number | null;
  sowing_date?: string | null;
}

// Agent

export interface ToolLogEntry {
  name: string;
  input: Record<string, unknown>;
  ok: boolean;
  duration_ms: number;
  error_code: string | null;
  provenance: string | null;
}

export interface ChatRequest {
  message: string;
  conversation_id?: string | null;
  farm_id?: string | null;
}

export interface ChatResponse {
  conversation_id: string;
  message_id: string;
  advice: FarmingAdvice;
  tool_log: ToolLogEntry[];
  saved_recommendation_ids: string[];
}

export type AgentEvent =
  | { type: "status"; stage: string; iteration?: number }
  | { type: "tool_start"; id: string; name: string }
  | {
      type: "tool_end";
      id: string;
      name: string;
      ok: boolean;
      duration_ms: number;
      error_code: string | null;
      provenance: string | null;
    }
  | { type: "final"; response: ChatResponse }
  | { type: "error"; code: string; message: string };

export interface AnalyzeResponse {
  advice: FarmingAdvice;
  tool_log: ToolLogEntry[];
}

export interface Conversation {
  id: string;
  farm_id: string | null;
  title: string;
  created_at: string;
  updated_at: string;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  advice: FarmingAdvice | null;
  tool_log: ToolLogEntry[] | null;
  created_at: string;
}

export interface ConversationDetail extends Conversation {
  messages: ChatMessage[];
}

// History

export interface Recommendation {
  id: string;
  farm_id: string | null;
  conversation_id: string | null;
  origin: string;
  intent: Intent;
  crop: string | null;
  recommendation: string | null;
  summary: string;
  risk_level: RiskLevel;
  confidence: Confidence;
  advice: FarmingAdvice;
  weather_provenance: DataProvenance | null;
  weather_observed_at: string | null;
  created_at: string;
}

export interface RecommendationInput {
  advice: FarmingAdvice;
  origin: RecommendationOrigin;
  farm_id?: string | null;
  conversation_id?: string | null;
  crop?: string | null;
  latitude?: number | null;
  longitude?: number | null;
}

// Scenario Lab

export interface ScenarioInputs {
  temperature_c: number;
  humidity_pct: number;
  rain_probability_pct: number;
  expected_rain_mm: number;
  wind_speed_ms: number;
  crop: string;
  growth_stage: string;
  soil_moisture: SoilMoisture;
}

export interface ScenarioDefinition {
  id: "A" | "B";
  title: string;
  description: string;
  inputs: ScenarioInputs;
}

export interface ScenarioAiResult {
  status: "completed" | "unavailable" | "not_requested";
  advice: FarmingAdvice | null;
  tool_log: ToolLogEntry[];
  message: string | null;
  code: string | null;
}

export interface ScenarioResult {
  definition: ScenarioDefinition;
  provenance: "simulated";
  assessment: IrrigationAssessment;
  pest_risk: PestRiskAssessment;
  advice: FarmingAdvice;
  ai: ScenarioAiResult;
}

export interface InputDifference {
  key: string;
  label: string;
  values: Record<string, string>;
  differs: boolean;
}

export interface FactorComparison {
  key: string;
  label: string;
  values: Record<string, string>;
  weights: Record<string, number>;
  explanations: Record<string, string>;
}

export interface ScenarioRun {
  label: string;
  notice: string;
  results: ScenarioResult[];
  input_differences: InputDifference[];
  factor_comparison: FactorComparison[];
  outcomes_differ: boolean;
}
