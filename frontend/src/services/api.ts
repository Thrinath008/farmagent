import type {
  AgentEvent,
  AnalyzeResponse,
  AssessmentTarget,
  Catalog,
  ChatRequest,
  ChatResponse,
  Conversation,
  ConversationDetail,
  CurrentWeather,
  Farm,
  FarmCrop,
  FarmCropInput,
  FarmInput,
  Forecast,
  GeocodeResult,
  GuestSession,
  Health,
  IrrigationRequest,
  IrrigationResponse,
  PestRiskResponse,
  Recommendation,
  RecommendationInput,
  ScenarioDefinition,
  ScenarioRun,
  User,
} from "@/types/api";

const API_BASE = (import.meta.env.VITE_API_URL ?? "").replace(/\/+$/, "");
const TOKEN_KEY = "farmagent.guest_token";

export const tokenStore = {
  get(): string | null {
    try {
      return localStorage.getItem(TOKEN_KEY);
    } catch {
      return null;
    }
  },
  set(token: string) {
    localStorage.setItem(TOKEN_KEY, token);
  },
  clear() {
    localStorage.removeItem(TOKEN_KEY);
  },
};

export class ApiError extends Error {
  readonly code: string;
  readonly status: number;
  readonly requestId?: string;
  readonly fields?: { field: string; problem: string }[];

  constructor(
    code: string,
    message: string,
    status = 0,
    requestId?: string,
    fields?: { field: string; problem: string }[],
  ) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.status = status;
    this.requestId = requestId;
    this.fields = fields;
  }
}

const UNREACHABLE =
  "FarmAgent's server could not be reached. Check your connection and try again.";

interface RequestOptions {
  method?: string;
  body?: unknown;
  query?: Record<string, string | number | boolean | null | undefined>;
  signal?: AbortSignal;
}

function buildUrl(path: string, query?: RequestOptions["query"]): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value !== null && value !== undefined && value !== "") params.set(key, String(value));
  }
  const suffix = params.toString();
  return `${API_BASE}/api${path}${suffix ? `?${suffix}` : ""}`;
}

function headers(hasBody: boolean): HeadersInit {
  const result: Record<string, string> = {};
  if (hasBody) result["Content-Type"] = "application/json";
  const token = tokenStore.get();
  if (token) result["X-Guest-Token"] = token;
  return result;
}

async function toApiError(response: Response): Promise<ApiError> {
  try {
    const { error } = await response.json();
    if (error?.code && error?.message) {
      return new ApiError(error.code, error.message, response.status, error.request_id, error.fields);
    }
  } catch {
    // Not our JSON error envelope, usually a proxy in front of an API that is down.
  }
  return new ApiError("server_unreachable", UNREACHABLE, response.status);
}

async function send(url: string, init: RequestInit): Promise<Response> {
  try {
    return await fetch(url, init);
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new ApiError("network_error", UNREACHABLE);
  }
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = "GET", body, query, signal } = options;
  const hasBody = body !== undefined;
  const response = await send(buildUrl(path, query), {
    method,
    headers: headers(hasBody),
    body: hasBody ? JSON.stringify(body) : undefined,
    signal,
  });
  if (!response.ok) throw await toApiError(response);
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

/** Split a server-sent event stream into parsed `data:` frames. Tolerates frames cut across reads. */
export function createSseParser(onFrame: (data: unknown) => void) {
  let buffer = "";
  return (chunk: string) => {
    buffer += chunk;
    let boundary = buffer.indexOf("\n\n");
    while (boundary !== -1) {
      const frame = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);
      const data = frame
        .split("\n")
        .filter((line) => line.startsWith("data:"))
        .map((line) => line.slice(5).trimStart())
        .join("\n");
      if (data) onFrame(JSON.parse(data));
      boundary = buffer.indexOf("\n\n");
    }
  };
}

/** Run one agent turn. Resolves with the validated final answer, rejects with an ApiError. */
export async function streamChat(
  body: ChatRequest,
  onEvent: (event: AgentEvent) => void,
  signal?: AbortSignal,
): Promise<ChatResponse> {
  const response = await send(buildUrl("/agent/chat/stream"), {
    method: "POST",
    headers: headers(true),
    body: JSON.stringify(body),
    signal,
  });
  if (!response.ok) throw await toApiError(response);
  if (!response.body) throw new ApiError("agent_unavailable", UNREACHABLE);

  let final: ChatResponse | null = null;
  let failure: ApiError | null = null;
  const parse = createSseParser((frame) => {
    const event = frame as AgentEvent;
    if (event.type === "final") final = event.response;
    if (event.type === "error") failure = new ApiError(event.code, event.message, response.status);
    onEvent(event);
  });

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      parse(decoder.decode(value, { stream: true }));
    }
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    throw new ApiError("network_error", "The connection dropped before the assistant finished.");
  }
  if (failure) throw failure;
  if (!final) {
    throw new ApiError("agent_unavailable", "The connection closed before the assistant finished.");
  }
  return final;
}

export const api = {
  health: () => request<Health>("/health"),
  catalog: () => request<Catalog>("/crops"),

  createGuest: () => request<GuestSession>("/session/guest", { method: "POST" }),
  me: () => request<User>("/session/me"),
  updateMe: (body: { display_name?: string | null; preferred_language?: string }) =>
    request<User>("/session/me", { method: "PATCH", body }),
  deleteMe: () => request<void>("/session/me", { method: "DELETE" }),

  farms: () => request<Farm[]>("/farms"),
  createFarm: (body: FarmInput) => request<Farm>("/farms", { method: "POST", body }),
  updateFarm: (id: string, body: FarmInput) =>
    request<Farm>(`/farms/${id}`, { method: "PATCH", body }),
  deleteFarm: (id: string) => request<void>(`/farms/${id}`, { method: "DELETE" }),
  addCrop: (farmId: string, body: FarmCropInput) =>
    request<FarmCrop>(`/farms/${farmId}/crops`, { method: "POST", body }),
  updateCrop: (farmId: string, cropId: string, body: FarmCropInput) =>
    request<FarmCrop>(`/farms/${farmId}/crops/${cropId}`, { method: "PATCH", body }),
  deleteCrop: (farmId: string, cropId: string) =>
    request<void>(`/farms/${farmId}/crops/${cropId}`, { method: "DELETE" }),

  currentWeather: (lat: number, lon: number, refresh = false) =>
    request<CurrentWeather>("/weather/current", { query: { lat, lon, refresh: refresh || null } }),
  forecast: (lat: number, lon: number, refresh = false) =>
    request<Forecast>("/weather/forecast", { query: { lat, lon, refresh: refresh || null } }),
  geocode: (q: string) =>
    request<{ results: GeocodeResult[] }>("/weather/geocode", { query: { q } }),
  reverseGeocode: (lat: number, lon: number) =>
    request<{ results: GeocodeResult[] }>("/weather/geocode", { query: { lat, lon } }),

  assessIrrigation: (body: IrrigationRequest) =>
    request<IrrigationResponse>("/irrigation/assess", { method: "POST", body }),
  assessPestRisk: (body: AssessmentTarget) =>
    request<PestRiskResponse>("/pest-risk/assess", { method: "POST", body }),

  analyzeFarm: (body: { farm_id: string; farm_crop_id?: string | null; focus?: string }) =>
    request<AnalyzeResponse>("/agent/analyze", { method: "POST", body }),

  conversations: () => request<Conversation[]>("/conversations"),
  conversation: (id: string) => request<ConversationDetail>(`/conversations/${id}`),
  deleteConversation: (id: string) => request<void>(`/conversations/${id}`, { method: "DELETE" }),

  recommendations: (query: { limit?: number; farm_id?: string | null; intent?: string | null } = {}) =>
    request<Recommendation[]>("/recommendations", { query }),
  saveRecommendation: (body: RecommendationInput) =>
    request<Recommendation>("/recommendations", { method: "POST", body }),
  deleteRecommendation: (id: string) => request<void>(`/recommendations/${id}`, { method: "DELETE" }),

  scenarios: () => request<ScenarioDefinition[]>("/scenarios"),
  runScenarios: (body: { include_ai: boolean }) =>
    request<ScenarioRun>("/scenarios/run", { method: "POST", body }),
};
