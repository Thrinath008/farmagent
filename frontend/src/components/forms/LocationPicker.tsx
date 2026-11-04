import { useState, type SyntheticEvent } from "react";
import { useMutation } from "@tanstack/react-query";
import { LoaderCircle, LocateFixed, MapPin, Search } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ErrorState } from "@/components/states/States";
import { coordinates } from "@/lib/format";
import { api, ApiError } from "@/services/api";
import type { GeocodeResult } from "@/types/api";

export interface PickedPlace {
  name: string | null;
  state: string | null;
  country: string | null;
  latitude: number;
  longitude: number;
}

function placeLabel(place: GeocodeResult): string {
  return [place.name, place.state, place.country].filter(Boolean).join(", ");
}

function currentPosition(): Promise<GeolocationPosition> {
  return new Promise((resolve, reject) => {
    if (!navigator.geolocation) {
      reject(new ApiError("bad_request", "This browser cannot share its location."));
      return;
    }
    navigator.geolocation.getCurrentPosition(resolve, reject, { timeout: 12_000 });
  });
}

/** Search by name, use the device's location (asked for only on click), or type coordinates. */
export function LocationPicker({
  onPick,
  idPrefix = "location",
}: {
  onPick: (place: PickedPlace) => void;
  idPrefix?: string;
}) {
  const [query, setQuery] = useState("");
  const [manual, setManual] = useState(false);
  const [lat, setLat] = useState("");
  const [lon, setLon] = useState("");
  const [manualError, setManualError] = useState<string | null>(null);
  const [geoError, setGeoError] = useState<string | null>(null);

  const search = useMutation({ mutationFn: (q: string) => api.geocode(q) });

  const locate = useMutation({
    mutationFn: async () => {
      setGeoError(null);
      let position: GeolocationPosition;
      try {
        position = await currentPosition();
      } catch (error) {
        if (error instanceof ApiError) throw error;
        const denied = (error as GeolocationPositionError).code === 1;
        throw new ApiError(
          "bad_request",
          denied
            ? "Location permission was declined. Search for your village or town instead."
            : "Your location could not be found. Search for your village or town instead.",
        );
      }
      const { latitude, longitude } = position.coords;
      // The name is a convenience. Coordinates alone still work when reverse lookup fails.
      const named = await api.reverseGeocode(latitude, longitude).catch(() => ({ results: [] }));
      const place = named.results[0];
      onPick({
        name: place?.name ?? null,
        state: place?.state ?? null,
        country: place?.country ?? null,
        latitude,
        longitude,
      });
    },
    onError: (error) => setGeoError(error instanceof ApiError ? error.message : "Location lookup failed."),
  });

  function submitSearch(event: SyntheticEvent) {
    event.preventDefault();
    event.stopPropagation();
    if (query.trim().length >= 2) search.mutate(query.trim());
  }

  function submitManual() {
    const latitude = Number(lat);
    const longitude = Number(lon);
    if (lat.trim() === "" || lon.trim() === "" || !Number.isFinite(latitude) || !Number.isFinite(longitude)) {
      setManualError("Enter both latitude and longitude as numbers.");
      return;
    }
    if (Math.abs(latitude) > 90 || Math.abs(longitude) > 180) {
      setManualError("Latitude runs from -90 to 90, and longitude from -180 to 180.");
      return;
    }
    setManualError(null);
    onPick({ name: null, state: null, country: null, latitude, longitude });
  }

  return (
    <div className="grid gap-3">
      <div className="grid gap-1.5">
        <Label htmlFor={`${idPrefix}-search`}>Search for your village, town or district</Label>
        <div className="flex gap-2">
          <Input
            id={`${idPrefix}-search`}
            value={query}
            placeholder="For example, Ludhiana"
            onChange={(event) => setQuery(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") submitSearch(event);
            }}
          />
          <Button
            type="button"
            variant="secondary"
            onClick={submitSearch}
            disabled={query.trim().length < 2 || search.isPending}
          >
            {search.isPending ? (
              <LoaderCircle className="animate-spin" aria-hidden="true" />
            ) : (
              <Search aria-hidden="true" />
            )}
            Search
          </Button>
        </div>
      </div>

      {search.isError && <ErrorState compact error={search.error} />}
      {search.isSuccess && search.data.results.length === 0 && (
        <p className="text-sm text-muted-foreground" role="status">
          No places matched "{search.variables}". Check the spelling, or try a larger town nearby.
        </p>
      )}
      {search.isSuccess && search.data.results.length > 0 && (
        <ul className="divide-y divide-border rounded border border-border bg-card">
          {search.data.results.map((place) => (
            <li key={`${place.latitude},${place.longitude}`}>
              <button
                type="button"
                className="flex w-full items-center gap-2 px-3 py-2.5 text-left text-sm hover:bg-muted"
                onClick={() =>
                  onPick({
                    name: place.name,
                    state: place.state,
                    country: place.country,
                    latitude: place.latitude,
                    longitude: place.longitude,
                  })
                }
              >
                <MapPin className="size-4 shrink-0 text-shoot-ink" aria-hidden="true" />
                <span className="min-w-0 flex-1">{placeLabel(place)}</span>
                <span className="font-mono text-xs text-muted-foreground">
                  {coordinates(place.latitude, place.longitude)}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}

      <div className="flex flex-wrap items-center gap-2">
        <Button type="button" variant="outline" size="sm" onClick={() => locate.mutate()} disabled={locate.isPending}>
          {locate.isPending ? (
            <LoaderCircle className="animate-spin" aria-hidden="true" />
          ) : (
            <LocateFixed aria-hidden="true" />
          )}
          Use my current location
        </Button>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          aria-expanded={manual}
          onClick={() => setManual((open) => !open)}
        >
          Enter coordinates
        </Button>
      </div>
      {geoError && (
        <p role="alert" className="text-sm text-clay-ink">
          {geoError}
        </p>
      )}

      {manual && (
        <div className="grid gap-2 rounded border border-border p-3">
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="grid gap-1.5">
              <Label htmlFor={`${idPrefix}-lat`}>Latitude</Label>
              <Input
                id={`${idPrefix}-lat`}
                inputMode="decimal"
                value={lat}
                placeholder="30.901"
                onChange={(event) => setLat(event.target.value)}
              />
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor={`${idPrefix}-lon`}>Longitude</Label>
              <Input
                id={`${idPrefix}-lon`}
                inputMode="decimal"
                value={lon}
                placeholder="75.857"
                onChange={(event) => setLon(event.target.value)}
              />
            </div>
          </div>
          {manualError && (
            <p role="alert" className="text-sm text-clay-ink">
              {manualError}
            </p>
          )}
          <div>
            <Button type="button" variant="secondary" size="sm" onClick={submitManual}>
              Use these coordinates
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
