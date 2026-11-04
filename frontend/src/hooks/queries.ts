import { useMutation, useMutationState, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError, tokenStore } from "@/services/api";
import type { CurrentWeather, Forecast, User, WeatherMeta } from "@/types/api";

export const keys = {
  session: ["session"] as const,
  health: ["health"] as const,
  catalog: ["catalog"] as const,
  farms: ["farms"] as const,
  current: (lat: number | null, lon: number | null) => ["weather", "current", lat, lon] as const,
  forecast: (lat: number | null, lon: number | null) => ["weather", "forecast", lat, lon] as const,
  conversations: ["conversations"] as const,
  conversation: (id: string | undefined) => ["conversations", id] as const,
  recommendations: ["recommendations"] as const,
  scenarios: ["scenarios"] as const,
};

// A page left open must not keep claiming LIVE WEATHER, so weather is re-requested on a timer. The
// server answers from its cache within the TTL and labels that as cached, with its age.
const WEATHER_REFRESH = {
  staleTime: 60_000,
  refetchInterval: 10 * 60_000,
  refetchOnWindowFocus: true,
};

async function bootstrapSession(): Promise<User> {
  if (tokenStore.get()) {
    try {
      return await api.me();
    } catch (error) {
      if (!(error instanceof ApiError && error.status === 401)) throw error;
      tokenStore.clear();
    }
  }
  const { token, user } = await api.createGuest();
  tokenStore.set(token);
  return user;
}

export function useSession() {
  return useQuery({ queryKey: keys.session, queryFn: bootstrapSession, staleTime: Infinity });
}

export function useHealth() {
  return useQuery({ queryKey: keys.health, queryFn: api.health, staleTime: 60_000 });
}

export function useCatalog() {
  return useQuery({ queryKey: keys.catalog, queryFn: api.catalog, staleTime: Infinity });
}

export function useFarms() {
  const session = useSession();
  return useQuery({ queryKey: keys.farms, queryFn: api.farms, enabled: session.isSuccess });
}

export function useCurrentWeather(lat: number | null, lon: number | null) {
  return useQuery({
    queryKey: keys.current(lat, lon),
    queryFn: () => api.currentWeather(lat as number, lon as number),
    enabled: lat !== null && lon !== null,
    ...WEATHER_REFRESH,
  });
}

export function useForecast(lat: number | null, lon: number | null) {
  return useQuery({
    queryKey: keys.forecast(lat, lon),
    queryFn: () => api.forecast(lat as number, lon as number),
    enabled: lat !== null && lon !== null,
    ...WEATHER_REFRESH,
  });
}

const refreshKey = (lat: number | null, lon: number | null) => ["refresh-weather", lat, lon];

export function useRefreshWeather(lat: number | null, lon: number | null) {
  const client = useQueryClient();
  return useMutation({
    mutationKey: refreshKey(lat, lon),
    mutationFn: async () => {
      if (lat === null || lon === null) throw new ApiError("bad_request", "Choose a location first.");
      const [current, forecast] = await Promise.all([
        api.currentWeather(lat, lon, true),
        api.forecast(lat, lon, true),
      ]);
      return { current, forecast };
    },
    onSuccess: ({ current, forecast }: { current: CurrentWeather; forecast: Forecast }) => {
      client.setQueryData(keys.current(lat, lon), current);
      client.setQueryData(keys.forecast(lat, lon), forecast);
    },
  });
}

/** Whether the latest refresh of this place failed, for panels that show weather but do not own the button. */
export function useRefreshFailed(lat: number | null, lon: number | null): boolean {
  const statuses = useMutationState({
    filters: { mutationKey: refreshKey(lat, lon) },
    select: (mutation) => mutation.state.status,
  });
  return statuses.at(-1) === "error";
}

/**
 * The meta to display for a weather query. When a background refresh failed, the data on screen is
 * no longer what the server just said, so it must not keep its LIVE label.
 */
export function displayMeta(meta: WeatherMeta, refreshFailed: boolean): WeatherMeta {
  if (!refreshFailed) return meta;
  return {
    ...meta,
    provenance: "cached",
    is_stale: true,
    warning: "This could not be refreshed, so it may be out of date.",
  };
}
