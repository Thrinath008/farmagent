import { useState } from "react";
import { MapPin } from "lucide-react";
import { Controller, useFormContext } from "react-hook-form";
import { Field, SelectField } from "@/components/forms/Field";
import { LocationPicker } from "@/components/forms/LocationPicker";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { coordinates, words } from "@/lib/format";
import type { Catalog } from "@/types/api";
import type { CropValues, FarmValues } from "./schema";

export function PlaceFields({ idPrefix = "farm" }: { idPrefix?: string }) {
  const form = useFormContext<FarmValues>();
  const [changing, setChanging] = useState(false);
  const latitude = form.watch("latitude");
  const longitude = form.watch("longitude");
  const hasCoordinates = latitude !== null && longitude !== null;
  const errors = form.formState.errors;

  return (
    <div className="grid gap-4">
      {hasCoordinates && !changing ? (
        <div className="flex flex-wrap items-center justify-between gap-2 rounded border border-border bg-muted/50 px-3 py-2 text-sm">
          <span className="flex min-w-0 items-center gap-2">
            <MapPin className="size-4 shrink-0 text-shoot-ink" aria-hidden="true" />
            <span className="font-mono text-xs">{coordinates(latitude, longitude)}</span>
          </span>
          <Button type="button" variant="ghost" size="sm" onClick={() => setChanging(true)}>
            Change location
          </Button>
        </div>
      ) : (
        <LocationPicker
          idPrefix={`${idPrefix}-place`}
          onPick={(place) => {
            form.setValue("latitude", place.latitude, { shouldDirty: true });
            form.setValue("longitude", place.longitude, { shouldDirty: true });
            // A lookup that named nothing must not wipe what the farmer typed.
            if (place.name) form.setValue("location_name", place.name, { shouldDirty: true });
            if (place.state) form.setValue("state", place.state, { shouldDirty: true });
            if (place.country) form.setValue("country", place.country, { shouldDirty: true });
            setChanging(false);
          }}
        />
      )}
      <div className="grid gap-3 sm:grid-cols-3">
        <Field id={`${idPrefix}-location_name`} label="Village or town" optional error={errors.location_name?.message}>
          <Input id={`${idPrefix}-location_name`} {...form.register("location_name")} />
        </Field>
        <Field id={`${idPrefix}-state`} label="State" optional error={errors.state?.message}>
          <Input id={`${idPrefix}-state`} {...form.register("state")} />
        </Field>
        <Field id={`${idPrefix}-country`} label="Country" optional error={errors.country?.message}>
          <Input id={`${idPrefix}-country`} {...form.register("country")} />
        </Field>
      </div>
    </div>
  );
}

export function FarmDetailFields({ catalog, idPrefix = "farm" }: { catalog: Catalog | undefined; idPrefix?: string }) {
  const form = useFormContext<FarmValues>();
  const errors = form.formState.errors;
  return (
    <div className="grid gap-4">
      <Field id={`${idPrefix}-name`} label="Farm name" optional error={errors.name?.message}>
        <Input id={`${idPrefix}-name`} {...form.register("name")} />
      </Field>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field id={`${idPrefix}-size`} label="Farm size" optional error={errors.size_value?.message}>
          <Input
            id={`${idPrefix}-size`}
            inputMode="decimal"
            aria-invalid={Boolean(errors.size_value) || undefined}
            {...form.register("size_value")}
          />
        </Field>
        <Field id={`${idPrefix}-unit`} label="Area unit" optional>
          <Controller
            control={form.control}
            name="area_unit"
            render={({ field }) => (
              <SelectField
                id={`${idPrefix}-unit`}
                value={field.value}
                onChange={field.onChange}
                clearLabel="Not set"
                options={(catalog?.area_units ?? []).map((value) => ({ value, label: words(value) }))}
              />
            )}
          />
        </Field>
      </div>
      <Field id={`${idPrefix}-soil`} label="Soil type" optional hint="If you are not sure, leave this. FarmAgent will not assume one.">
        <Controller
          control={form.control}
          name="soil_type"
          render={({ field }) => (
            <SelectField
              id={`${idPrefix}-soil`}
              value={field.value}
              onChange={field.onChange}
              clearLabel="Not sure"
              options={(catalog?.soil_types ?? []).map((value) => ({ value, label: words(value) }))}
            />
          )}
        />
      </Field>
    </div>
  );
}

export function CropFields({
  catalog,
  idPrefix = "crop",
  lockCrop,
  cropOptional,
}: {
  catalog: Catalog | undefined;
  idPrefix?: string;
  lockCrop?: boolean;
  cropOptional?: boolean;
}) {
  const form = useFormContext<CropValues>();
  const errors = form.formState.errors;
  const chosen = form.watch("crop");
  const profile = catalog?.crops.find((item) => item.id === chosen);

  return (
    <div className="grid gap-4">
      <Field
        id={`${idPrefix}-crop`}
        label="Crop"
        optional={cropOptional}
        error={errors.crop?.message}
        hint={profile?.support_level === "planned" ? profile.support_note : undefined}
      >
        <Controller
          control={form.control}
          name="crop"
          render={({ field }) => (
            <SelectField
              id={`${idPrefix}-crop`}
              value={field.value}
              disabled={lockCrop}
              invalid={Boolean(errors.crop)}
              clearLabel={cropOptional ? "Decide later" : undefined}
              onChange={(value) => {
                field.onChange(value);
                form.setValue("growth_stage", "");
              }}
              options={(catalog?.crops ?? []).map((item) => ({
                value: item.id,
                label: item.support_level === "planned" ? `${item.name} (rules not yet available)` : item.name,
              }))}
            />
          )}
        />
      </Field>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field id={`${idPrefix}-variety`} label="Variety" optional error={errors.variety?.message}>
          <Input id={`${idPrefix}-variety`} {...form.register("variety")} />
        </Field>
        <Field id={`${idPrefix}-sowing`} label="Sowing date" optional hint="Lets FarmAgent lay out the irrigation season.">
          <Input id={`${idPrefix}-sowing`} type="date" {...form.register("sowing_date")} />
        </Field>
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        {profile && profile.stages.length > 0 && (
          <Field id={`${idPrefix}-stage`} label="Growth stage" optional hint="FarmAgent does not guess this from the sowing date.">
            <Controller
              control={form.control}
              name="growth_stage"
              render={({ field }) => (
                <SelectField
                  id={`${idPrefix}-stage`}
                  value={field.value}
                  onChange={field.onChange}
                  clearLabel="Not sure"
                  options={profile.stages.map((stage) => ({ value: stage.id, label: stage.label }))}
                />
              )}
            />
          </Field>
        )}
        <Field id={`${idPrefix}-method`} label="Irrigation method" optional>
          <Controller
            control={form.control}
            name="irrigation_method"
            render={({ field }) => (
              <SelectField
                id={`${idPrefix}-method`}
                value={field.value}
                onChange={field.onChange}
                clearLabel="Not sure"
                options={(catalog?.irrigation_methods ?? []).map((value) => ({ value, label: words(value) }))}
              />
            )}
          />
        </Field>
      </div>
    </div>
  );
}
