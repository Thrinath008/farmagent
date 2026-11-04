import { MapPin } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Field, SelectField } from "@/components/forms/Field";
import { LocationPicker, type PickedPlace } from "@/components/forms/LocationPicker";
import { placeTitle } from "@/lib/format";
import { ANOTHER_PLACE } from "@/lib/labels";
import type { Farm } from "@/types/api";

/** Choose a saved farm, or assess somewhere else without saving it. */
export function PlaceField({
  farms,
  value,
  onChange,
  picked,
  onPick,
}: {
  farms: Farm[];
  value: string;
  onChange: (value: string) => void;
  picked: PickedPlace | null;
  onPick: (place: PickedPlace | null) => void;
}) {
  return (
    <div className="grid gap-3">
      <Field id="assess-farm" label="Farm">
        <SelectField
          id="assess-farm"
          value={value}
          onChange={onChange}
          options={[
            ...farms.map((farm) => ({
              value: farm.id,
              label: farm.name ?? farm.location_name ?? "Unnamed farm",
            })),
            { value: ANOTHER_PLACE, label: "Another location" },
          ]}
        />
      </Field>
      {value === ANOTHER_PLACE &&
        (picked ? (
          <div className="flex flex-wrap items-center justify-between gap-2 rounded border border-border bg-muted/50 px-3 py-2 text-sm">
            <span className="flex min-w-0 items-center gap-2">
              <MapPin className="size-4 shrink-0 text-shoot-ink" aria-hidden="true" />
              {placeTitle(picked)}
            </span>
            <Button type="button" variant="ghost" size="sm" onClick={() => onPick(null)}>
              Change
            </Button>
          </div>
        ) : (
          <LocationPicker idPrefix="assess-location" onPick={onPick} />
        ))}
    </div>
  );
}
