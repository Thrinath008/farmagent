import type {
  Confidence,
  Intent,
  IrrigationAction,
  IrrigationStatus,
  RiskLevel,
} from "@/types/api";

export const STATUS_LABEL: Record<IrrigationStatus, string> = {
  favorable: "Favorable",
  monitor: "Monitor",
  caution: "Caution",
  insufficient_information: "Insufficient information",
};

export const ACTION_LABEL: Record<IrrigationAction, string> = {
  consider_irrigating: "Consider irrigating",
  consider_postponing: "Consider postponing",
  check_soil_and_reassess: "Check the soil, then reassess",
  hold_irrigation: "Hold irrigation",
  cannot_assess: "Cannot assess",
};

export const RISK_LABEL: Record<RiskLevel, string> = {
  low: "Low",
  moderate: "Moderate",
  elevated: "Elevated",
  uncertain: "Uncertain",
  not_applicable: "Not applicable",
};

export const CONFIDENCE_LABEL: Record<Confidence, string> = {
  insufficient: "Insufficient",
  limited: "Limited",
  moderate: "Moderate",
  good: "Good",
  not_applicable: "Not applicable",
};

export const INTENT_LABEL: Record<Intent, string> = {
  irrigation_advice: "Irrigation",
  weather_question: "Weather",
  pest_disease_risk: "Pest and disease risk",
  field_operation: "Field work",
  crop_guidance: "Crop guidance",
  farm_briefing: "Farm briefing",
  general: "General",
  out_of_scope: "Outside farming",
};

export const ORIGIN_LABEL: Record<string, string> = {
  assistant: "AI assistant",
  irrigation_advisor: "Irrigation Advisor",
  crop_health: "Crop Health & Risk",
  scenario_lab: "Scenario Lab",
};

export const GENERATED_BY_LABEL: Record<string, string> = {
  claude_agent: "Claude, using FarmAgent's tools",
  decision_engine: "FarmAgent's rule-based engine",
  safety_fallback: "Safety fallback",
};

export const TOOL_LABEL: Record<string, string> = {
  get_current_weather: "Checked current weather",
  get_weather_forecast: "Checked the forecast",
  get_crop_information: "Looked up crop guidance",
  assess_irrigation_need: "Ran the irrigation assessment",
  assess_weather_pest_risk: "Ran the weather risk assessment",
  get_location_information: "Looked up the location",
  save_recommendation: "Saved the recommendation",
};

export const ONBOARDING_SKIPPED = "onboarding_skipped";
export const ANOTHER_PLACE = "__another__";

export const LANGUAGES = [
  "English",
  "Punjabi",
  "Hindi",
  "Telugu",
  "Tamil",
  "Kannada",
  "Marathi",
  "Bengali",
  "Gujarati",
];

export const SUGGESTED_QUESTIONS = [
  "Should I irrigate my wheat field today?",
  "What does the weather mean for my crops?",
  "Is tomorrow suitable for irrigation?",
  "Are current conditions favorable for fungal disease?",
  "What precautions should I take this week?",
];
