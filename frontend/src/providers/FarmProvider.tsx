import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";
import { useFarms } from "@/hooks/queries";
import type { Farm, FarmCrop } from "@/types/api";

const FARM_KEY = "farmagent.selected_farm";
const CROP_KEY = "farmagent.selected_crop";

interface FarmContextValue {
  farms: Farm[];
  farm: Farm | null;
  crop: FarmCrop | null;
  isLoading: boolean;
  error: unknown;
  refetch: () => void;
  selectFarm: (id: string) => void;
  selectCrop: (id: string) => void;
}

const FarmContext = createContext<FarmContextValue | null>(null);

function stored(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

export function FarmProvider({ children }: { children: ReactNode }) {
  const query = useFarms();
  const [farmId, setFarmId] = useState(() => stored(FARM_KEY));
  const [cropId, setCropId] = useState(() => stored(CROP_KEY));

  const selectFarm = useCallback((id: string) => {
    localStorage.setItem(FARM_KEY, id);
    setFarmId(id);
  }, []);

  const selectCrop = useCallback((id: string) => {
    localStorage.setItem(CROP_KEY, id);
    setCropId(id);
  }, []);

  const value = useMemo<FarmContextValue>(() => {
    const farms = query.data ?? [];
    const farm = farms.find((f) => f.id === farmId) ?? farms[0] ?? null;
    const crop = farm?.crops.find((c) => c.id === cropId) ?? farm?.crops[0] ?? null;
    return {
      farms,
      farm,
      crop,
      isLoading: query.isPending,
      error: query.error,
      refetch: query.refetch,
      selectFarm,
      selectCrop,
    };
  }, [query.data, query.isPending, query.error, query.refetch, farmId, cropId, selectFarm, selectCrop]);

  return <FarmContext.Provider value={value}>{children}</FarmContext.Provider>;
}

export function useFarmContext(): FarmContextValue {
  const value = useContext(FarmContext);
  if (!value) throw new Error("useFarmContext must be used inside FarmProvider");
  return value;
}
