import type {
  Catalog,
  ChatResponse,
  ConversationDetail,
  CurrentWeather,
  DecisionFactor,
  Farm,
  FarmCrop,
  FarmingAdvice,
  Forecast,
  Health,
  IrrigationAssessment,
  IrrigationResponse,
  IrrigationSchedule,
  PestRiskAssessment,
  PestRiskResponse,
  Recommendation,
  ScenarioDefinition,
  ScenarioResult,
  ScenarioRun,
  User,
  WeatherMeta,
  WeatherSnapshot,
} from "@/types/api";

const NOW = () => new Date().toISOString();

export const user: User = {
  id: "user-1",
  display_name: null,
  preferred_language: "English",
  created_at: "2026-10-01T00:00:00Z",
};

export const health: Health = {
  status: "ok",
  version: "1.0.0",
  environment: "test",
  database: "ok",
  weather_configured: true,
  ai_configured: true,
  ai_model: "claude-opus-5-5",
};

export const catalog: Catalog = {
  crops: [
    {
      id: "wheat",
      name: "Wheat",
      support_level: "rules_implemented",
      support_note: "Rules implemented",
      stages: [
        { id: "tillering", label: "Tillering", irrigation_critical: true, note: null },
        { id: "heading", label: "Heading", irrigation_critical: true, note: null },
      ],
      irrigation_considerations: [],
      sources: [],
    },
    {
      id: "rice",
      name: "Rice",
      support_level: "planned",
      support_note: "Crop-specific rules are not available yet.",
      stages: [],
      irrigation_considerations: [],
      sources: [],
    },
  ],
  soil_types: ["loam", "clay"],
  irrigation_methods: ["border", "drip"],
  soil_moisture_levels: ["low", "adequate", "high", "unknown"],
  area_units: ["acre", "hectare"],
};

export const schedule: IrrigationSchedule = {
  sowing_date: "2026-11-01",
  days_after_sowing: 12,
  windows: [
    { number: 1, start_date: "2026-11-20", end_date: "2026-11-30", basis: "3 weeks after sowing" },
    { number: 2, start_date: "2026-12-20", end_date: "2026-12-30", basis: "7 weeks after sowing" },
  ],
  last_irrigation_by: "2027-03-10",
  next_window: { number: 1, start_date: "2026-11-20", end_date: "2026-11-30", basis: "3 weeks after sowing" },
  in_window: null,
  source_id: "pau-pop-rabi-2025-26",
};

export const farmCrop: FarmCrop = {
  id: "crop-1",
  farm_id: "farm-1",
  crop: "wheat",
  crop_name: "Wheat",
  support_level: "rules_implemented",
  variety: null,
  sowing_date: null,
  growth_stage: "tillering",
  growth_stage_label: "Tillering",
  irrigation_method: "border",
  irrigation_schedule: null,
  created_at: "2026-10-01T00:00:00Z",
};

export const farm: Farm = {
  id: "farm-1",
  name: "North field",
  location_name: "Ludhiana",
  state: "Punjab",
  country: "India",
  latitude: 30.9,
  longitude: 75.85,
  size_value: 5,
  area_unit: "acre",
  soil_type: "loam",
  crops: [farmCrop],
  created_at: "2026-10-01T00:00:00Z",
  updated_at: "2026-10-01T00:00:00Z",
};

export function weatherMeta(overrides: Partial<WeatherMeta> = {}): WeatherMeta {
  return {
    provenance: "live",
    source: "OpenWeatherMap",
    observed_at: NOW(),
    fetched_at: NOW(),
    age_seconds: 0,
    is_stale: false,
    warning: null,
    ...overrides,
  };
}

export function currentWeather(meta: Partial<WeatherMeta> = {}): CurrentWeather {
  return {
    latitude: 30.9,
    longitude: 75.85,
    location_name: "Ludhiana",
    temperature_c: 21,
    feels_like_c: 20,
    humidity_pct: 58,
    description: "scattered clouds",
    icon: null,
    wind_speed_ms: 3,
    wind_gust_ms: 5,
    wind_direction_deg: 90,
    cloud_cover_pct: 40,
    rain_last_1h_mm: null,
    rain_last_3h_mm: null,
    observed_at: NOW(),
    timezone_offset_seconds: 19800,
    meta: weatherMeta(meta),
  };
}

export function forecast(meta: Partial<WeatherMeta> = {}): Forecast {
  return {
    latitude: 30.9,
    longitude: 75.85,
    location_name: "Ludhiana",
    timezone_offset_seconds: 19800,
    resolution_hours: 3,
    horizon_hours: 120,
    hourly: [
      {
        time: "2026-11-05T00:00:00Z",
        temperature_c: 18,
        feels_like_c: 18,
        humidity_pct: 60,
        wind_speed_ms: 2,
        wind_gust_ms: 4,
        cloud_cover_pct: 30,
        rain_mm: 2.5,
        rain_probability_pct: 70,
        description: "light rain",
      },
    ],
    daily: [
      {
        date: "2026-11-05",
        temp_min_c: 13,
        temp_max_c: 27,
        humidity_mean_pct: 60,
        wind_max_ms: 4,
        rain_total_mm: 2.5,
        rain_probability_max_pct: 70,
        description: "light rain",
        periods: 8,
      },
    ],
    meta: weatherMeta(meta),
  };
}

export const factors: DecisionFactor[] = [
  {
    key: "soil_moisture",
    label: "Soil moisture",
    value: "Not provided",
    direction: "unknown",
    weight: 0,
    explanation: "Soil moisture was not provided.",
    source_ids: [],
  },
  {
    key: "forecast_rain",
    label: "Forecast rain (48 h)",
    value: "5.0 mm, up to 70% chance",
    direction: "against_irrigating",
    weight: -2,
    explanation: "Some rain is reasonably likely.",
    source_ids: [],
  },
  {
    key: "heat",
    label: "Heat and dryness",
    value: "up to 27 °C",
    direction: "supports_irrigating",
    weight: 1,
    explanation: "Warmer than the upper range for this stage.",
    source_ids: [],
  },
  {
    key: "wind",
    label: "Wind",
    value: "up to 17 km/h",
    direction: "neutral",
    weight: 0,
    explanation: "Wind is not a concern.",
    source_ids: [],
  },
];

export const advice: FarmingAdvice = {
  intent: "irrigation_advice",
  recommendation: "Consider postponing irrigation",
  summary: "Rain may do some of the work.",
  reasoning: ["Forecast rain is reasonably likely."],
  weather_context: {
    temperature_c: 21,
    humidity_pct: 58,
    rain_probability_pct: 70,
    expected_rain_mm: 5,
    window_hours: 48,
    wind_speed_ms: 3,
    description: "scattered clouds",
    location_name: "Ludhiana",
    provenance: "live",
    source: "OpenWeatherMap",
    observed_at: "2026-11-05T00:00:00Z",
    is_stale: false,
  },
  risk_level: "low",
  confidence: "limited",
  missing_information: ["Current soil moisture"],
  next_steps: ["Check soil moisture by hand at root depth."],
  data_sources: ["OpenWeatherMap"],
  requires_expert_verification: false,
  generated_by: "rule_engine",
};

export const snapshot: WeatherSnapshot = {
  provenance: "live",
  source: "OpenWeatherMap",
  observed_at: "2026-11-05T00:00:00Z",
  is_stale: false,
  warning: null,
  location_name: "Ludhiana",
  latitude: 30.9,
  longitude: 75.85,
  description: "scattered clouds",
  temperature_c: 21,
  feels_like_c: 20,
  humidity_pct: 58,
  wind_speed_ms: 3,
  rain_last_1h_mm: null,
  forecast_available: true,
  rain_next_24h_mm: 2.5,
  rain_next_48h_mm: 5,
  rain_prob_max_24h_pct: 70,
  rain_prob_max_48h_pct: 70,
  temp_max_48h_c: 27,
  temp_min_48h_c: 13,
  humidity_mean_48h_pct: 58,
  wind_max_24h_ms: 4,
  et0_mm_day: 2.8,
};

export const assessment: IrrigationAssessment = {
  crop: "wheat",
  crop_name: "Wheat",
  growth_stage: "tillering",
  growth_stage_label: "Tillering",
  status: "caution",
  action: "consider_postponing",
  headline: "Consider postponing irrigation",
  summary: "Rain may do some of the work.",
  next_action: "Check soil moisture, then wait to see how much rain actually falls.",
  next_steps: ["Check soil moisture by hand at root depth."],
  factors,
  supporting_factors: [],
  missing_information: ["Current soil moisture"],
  limitations: ["These are rule-based labels."],
  score: -1,
  risk_level: "low",
  confidence: "limited",
  confidence_note: "Soil moisture is unknown.",
  estimated_crop_water_use_mm_day: 2.8,
  schedule: null,
  weather_provenance: "live",
  sources: [],
};

export const irrigationResponse: IrrigationResponse = {
  assessment,
  advice,
  weather: snapshot,
  weather_issues: [],
  farm_id: "farm-1",
};

export const irrigationNoWeather: IrrigationResponse = {
  assessment: {
    ...assessment,
    status: "insufficient_information",
    action: "cannot_assess",
    headline: "Not enough information to assess",
    summary: "Verified weather could not be retrieved, so no weather-dependent assessment was made.",
    next_action: "Check the field yourself and try again once the missing information is available.",
    next_steps: [],
    factors: [],
    missing_information: ["Verified weather for this location"],
    score: 0,
    risk_level: "uncertain",
    confidence: "insufficient",
    confidence_note: "Weather is required.",
    estimated_crop_water_use_mm_day: null,
    weather_provenance: "unavailable",
  },
  advice: { ...advice, weather_context: null, risk_level: "uncertain", confidence: "insufficient" },
  weather: null,
  weather_issues: [{ code: "weather_unavailable", message: "Live weather could not be retrieved." }],
  farm_id: "farm-1",
};

export const pestAssessment: PestRiskAssessment = {
  crop: "wheat",
  crop_name: "Wheat",
  growth_stage: "tillering",
  growth_stage_label: "Tillering",
  overall_classification: "elevated",
  headline: "Conditions favour yellow rust",
  explanation: "Cool, humid weather favours this disease. That does not mean it is in your field.",
  risks: [
    {
      id: "yellow_rust",
      name: "Yellow rust",
      category: "disease",
      classification: "elevated",
      favorable_conditions: "Cool, humid weather",
      evidence: ["8 forecast periods in range"],
      monitoring_actions: ["Scout the field for yellow stripes on leaves."],
      regional_note: null,
      sources: [],
    },
  ],
  environmental_conditions: [{ label: "Humidity", value: "88%" }],
  crop_sensitivity: "Wheat is sensitive at tillering.",
  missing_information: [],
  confidence: "limited",
  confidence_note: "Based on forecast weather only.",
  disclaimer: "This is a weather-based risk assessment, not a plant disease diagnosis.",
  weather_provenance: "live",
};

export const pestResponse: PestRiskResponse = {
  assessment: pestAssessment,
  advice: { ...advice, intent: "pest_disease_risk", recommendation: null },
  weather: snapshot,
  weather_issues: [],
  farm_id: "farm-1",
};

export const pestNoWeather: PestRiskResponse = {
  assessment: {
    ...pestAssessment,
    overall_classification: "uncertain",
    headline: "Risk cannot be assessed without weather",
    explanation: "Verified weather could not be retrieved.",
    risks: [],
    environmental_conditions: [],
    confidence: "insufficient",
    weather_provenance: "unavailable",
  },
  advice: { ...advice, intent: "pest_disease_risk", weather_context: null },
  weather: null,
  weather_issues: [{ code: "weather_not_configured", message: "Live weather is not configured." }],
  farm_id: "farm-1",
};

const scenario = (id: "A" | "B", title: string, temperature: number): ScenarioDefinition => ({
  id,
  title,
  description: `${title} description`,
  inputs: {
    temperature_c: temperature,
    humidity_pct: 50,
    rain_probability_pct: id === "A" ? 85 : 5,
    expected_rain_mm: id === "A" ? 15 : 0,
    wind_speed_ms: 2,
    crop: "wheat",
    growth_stage: "vegetative",
    soil_moisture: id === "A" ? "unknown" : "low",
  },
});

export const scenarios: ScenarioDefinition[] = [scenario("A", "Rain expected", 24), scenario("B", "Hot and dry", 36)];

const simulatedAdvice: FarmingAdvice = {
  ...advice,
  weather_context: { ...(advice.weather_context as NonNullable<FarmingAdvice["weather_context"]>), provenance: "simulated", source: "Scenario Lab" },
};

const scenarioResult = (definition: ScenarioDefinition, headline: string): ScenarioResult => ({
  definition,
  provenance: "simulated",
  assessment: { ...assessment, headline, weather_provenance: "simulated" },
  pest_risk: { ...pestAssessment, weather_provenance: "simulated" },
  advice: simulatedAdvice,
  ai: { status: "not_requested", advice: null, tool_log: [], message: null, code: null },
});

export const scenarioRun: ScenarioRun = {
  label: "Simulated",
  notice: "Simulated data",
  results: [scenarioResult(scenarios[0], "Hold off for the rain"), scenarioResult(scenarios[1], "Consider irrigating soon")],
  input_differences: [
    { key: "temperature_c", label: "Temperature", values: { A: "24 °C", B: "36 °C" }, differs: true },
  ],
  factor_comparison: [
    {
      key: "forecast_rain",
      label: "Forecast rain",
      values: { A: "15 mm", B: "0 mm" },
      weights: { A: -3, B: 0 },
      explanations: { A: "Rain is likely.", B: "No rain is expected." },
    },
  ],
  outcomes_differ: true,
};

export const chatResponse: ChatResponse = {
  conversation_id: "conv-1",
  message_id: "msg-2",
  advice,
  tool_log: [],
  saved_recommendation_ids: [],
};

export function conversationDetail(createdAt = new Date().toISOString()): ConversationDetail {
  return {
    id: "conv-1",
    farm_id: "farm-1",
    title: "Should I irrigate?",
    created_at: createdAt,
    updated_at: createdAt,
    messages: [
      { id: "msg-1", role: "user", content: "Should I irrigate?", advice: null, tool_log: null, created_at: createdAt },
      {
        id: "msg-2",
        role: "assistant",
        content: advice.summary,
        advice,
        tool_log: [{ name: "get_current_weather", input: {}, ok: true, duration_ms: 120, error_code: null, provenance: "live" }],
        created_at: createdAt,
      },
    ],
  };
}

export const recommendation: Recommendation = {
  id: "rec-1",
  farm_id: "farm-1",
  conversation_id: null,
  origin: "irrigation_advisor",
  intent: "irrigation_advice",
  crop: "wheat",
  recommendation: "Consider postponing irrigation",
  summary: "Rain may do some of the work.",
  risk_level: "low",
  confidence: "limited",
  advice,
  weather_provenance: "live",
  weather_observed_at: "2026-10-01T06:00:00Z",
  created_at: "2026-10-01T06:00:00Z",
};
