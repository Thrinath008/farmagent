import { useEffect, useState } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { Droplets, Info } from "lucide-react";
import { Controller, useForm } from "react-hook-form";
import { Link } from "react-router";
import { z } from "zod";
import { SaveRecommendationButton } from "@/components/advice/AdviceCard";
import { SourceList } from "@/components/advice/SourceList";
import { DecisionLedger } from "@/components/decision/DecisionLedger";
import { ConfidenceLabel, InfoTip, StatusIndicator } from "@/components/decision/StatusIndicator";
import { Field, SelectField } from "@/components/forms/Field";
import type { PickedPlace } from "@/components/forms/LocationPicker";
import { PlaceField } from "@/components/forms/PlaceField";
import { Metric, PageHeader } from "@/components/layout/PageHeader";
import { ProvenanceBadge } from "@/components/provenance/ProvenanceBadge";
import { SeasonStrip } from "@/components/SeasonStrip";
import { EmptyState, ErrorState, LoadingState } from "@/components/states/States";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useCatalog } from "@/hooks/queries";
import { mm, percent, secondsSince, temp, todayIso, windKmh, words } from "@/lib/format";
import { ACTION_LABEL, ANOTHER_PLACE } from "@/lib/labels";
import { useFarmContext } from "@/providers/FarmProvider";
import { api, ApiError } from "@/services/api";
import type { ApiIssue, IrrigationRequest, IrrigationResponse, SoilMoisture } from "@/types/api";

const schema = z.object({
  place: z.string(),
  crop: z.string().min(1, "Choose a crop."),
  growth_stage: z.string(),
  soil_type: z.string(),
  irrigation_method: z.string(),
  soil_moisture: z.enum(["low", "adequate", "high", "unknown"]),
  recent_rainfall_mm: z
    .string()
    .refine(
      (value) =>
        value.trim() === "" || (Number.isFinite(Number(value)) && Number(value) >= 0 && Number(value) <= 1000),
      "Enter rainfall in millimetres, from 0 to 1000.",
    ),
  sowing_date: z.string(),
});

type Values = z.infer<typeof schema>;

const MOISTURE_LABEL: Record<SoilMoisture, string> = {
  unknown: "I have not checked",
  low: "Low, the soil feels dry",
  adequate: "Adequate",
  high: "High, the soil is wet",
};

function WeatherIssues({ issues }: { issues: ApiIssue[] }) {
  if (issues.length === 0) return null;
  return (
    <div className="space-y-3" data-testid="weather-issues">
      {issues.map((issue) =>
        issue.code === "location_missing" ? (
          <EmptyState
            key={issue.code}
            title="This farm has no location"
            action={
              <Button variant="outline" size="sm" asChild>
                <Link to="/farm">Set the location</Link>
              </Button>
            }
          >
            {issue.message}
          </EmptyState>
        ) : (
          <ErrorState key={issue.code} error={new ApiError(issue.code, issue.message)} />
        ),
      )}
    </div>
  );
}

function Result({ data, request }: { data: IrrigationResponse; request: IrrigationRequest }) {
  const { assessment, weather, advice } = data;
  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2 }}
      className="space-y-5"
      data-testid="irrigation-result"
    >
      <WeatherIssues issues={data.weather_issues} />

      <section className="panel p-4 sm:p-6" aria-labelledby="assessment-heading">
        <div className="flex flex-wrap items-center gap-3">
          <StatusIndicator status={assessment.status} large />
          <InfoTip label="What these labels mean">
            Favorable, Monitor, Caution and Insufficient information come from FarmAgent's rules. They
            are guidance labels and have not been calibrated as scientific measurements.
          </InfoTip>
          <ProvenanceBadge
            className="ml-auto"
            provenance={assessment.weather_provenance}
            isStale={weather?.is_stale}
            ageSeconds={secondsSince(weather?.observed_at)}
            source={weather?.source}
          />
        </div>
        <h2 id="assessment-heading" className="display mt-4 text-xl sm:text-2xl">
          {assessment.headline}
        </h2>
        <p className="mt-2 text-[0.9375rem] leading-relaxed">{assessment.summary}</p>

        <div className="mt-4 rounded bg-sage p-3">
          <p className="eyebrow">Recommended next action · {ACTION_LABEL[assessment.action]}</p>
          <p className="mt-1 font-medium">{assessment.next_action}</p>
          {assessment.next_steps.length > 0 && (
            <ul className="mt-2 list-disc space-y-1 pl-5 text-sm">
              {assessment.next_steps.map((step) => (
                <li key={step}>{step}</li>
              ))}
            </ul>
          )}
        </div>

        <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
          <ConfidenceLabel confidence={assessment.confidence} note={assessment.confidence_note} />
          {assessment.confidence !== "insufficient" && (
            <SaveRecommendationButton
              input={{
                advice,
                origin: "irrigation_advisor",
                farm_id: request.farm_id ?? null,
                crop: assessment.crop,
                latitude: request.latitude ?? null,
                longitude: request.longitude ?? null,
              }}
            />
          )}
        </div>
      </section>

      {weather && weather.provenance !== "unavailable" && (
        <section className="panel p-4 sm:p-5" aria-labelledby="conditions-heading">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h3 id="conditions-heading" className="display text-base">
              Weather used for this assessment
            </h3>
            {weather.location_name && <span className="text-sm text-muted-foreground">{weather.location_name}</span>}
          </div>
          {weather.warning && (
            <p className="mt-2 rounded bg-amber-wash p-2.5 text-sm text-amber-ink">{weather.warning}</p>
          )}
          <dl className="mt-3 grid grid-cols-2 gap-x-5 gap-y-4 sm:grid-cols-3 lg:grid-cols-5">
            <Metric label="Temperature" value={temp(weather.temperature_c)} />
            <Metric label="Humidity" value={percent(weather.humidity_pct)} />
            <Metric label="Expected rain, next 48 h" value={mm(weather.rain_next_48h_mm)} />
            <Metric label="Highest chance of rain, next 48 h" value={percent(weather.rain_prob_max_48h_pct)} />
            <Metric label="Strongest wind, next 24 h" value={windKmh(weather.wind_max_24h_ms)} />
          </dl>
          {assessment.estimated_crop_water_use_mm_day !== null && (
            <p className="mt-3 flex items-center gap-1 text-sm text-muted-foreground">
              Rough crop water use: about {assessment.estimated_crop_water_use_mm_day} mm a day.
              <InfoTip label="About this estimate">
                A rough figure from the Hargreaves equation and FAO-56 crop coefficients. It is shown
                for information and does not decide the status above.
              </InfoTip>
            </p>
          )}
        </section>
      )}

      {assessment.schedule && (
        <section className="panel p-4 sm:p-5">
          <SeasonStrip schedule={assessment.schedule} cropName={assessment.crop_name} />
        </section>
      )}

      {assessment.factors.length > 0 && (
        <section className="panel p-4 sm:p-5">
          <DecisionLedger factors={assessment.factors} score={assessment.score} />
        </section>
      )}

      {(assessment.missing_information.length > 0 || assessment.limitations.length > 0) && (
        <section className="panel grid gap-5 p-4 sm:p-5 md:grid-cols-2">
          {assessment.missing_information.length > 0 && (
            <div>
              <h3 className="display text-base">What is still unknown</h3>
              <ul className="mt-2 list-disc space-y-1 pl-5 text-sm">
                {assessment.missing_information.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </div>
          )}
          {assessment.limitations.length > 0 && (
            <div>
              <h3 className="display text-base">Limits of this assessment</h3>
              <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-muted-foreground">
                {assessment.limitations.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </div>
          )}
        </section>
      )}

      {assessment.sources.length > 0 && (
        <section className="panel p-4 sm:p-5">
          <SourceList sources={assessment.sources} title="Agricultural sources behind these rules" />
        </section>
      )}
    </motion.div>
  );
}

export function IrrigationPage() {
  const { farms, farm, crop, isLoading } = useFarmContext();
  const catalog = useCatalog();
  const [picked, setPicked] = useState<PickedPlace | null>(null);
  const [placeError, setPlaceError] = useState<string | null>(null);
  const [lastRequest, setLastRequest] = useState<IrrigationRequest | null>(null);

  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: {
      place: ANOTHER_PLACE,
      crop: "",
      growth_stage: "",
      soil_type: "",
      irrigation_method: "",
      soil_moisture: "unknown",
      recent_rainfall_mm: "",
      sowing_date: "",
    },
  });

  const assess = useMutation({ mutationFn: (body: IrrigationRequest) => api.assessIrrigation(body) });
  const place = form.watch("place");
  const chosenCrop = form.watch("crop");
  const chosenFarm = farms.find((item) => item.id === place) ?? null;
  const cropProfile = catalog.data?.crops.find((item) => item.id === chosenCrop);

  function applyFarm(farmId: string) {
    const target = farms.find((item) => item.id === farmId);
    const stored = target?.id === farm?.id ? crop : (target?.crops[0] ?? null);
    form.reset({
      place: farmId,
      crop: stored?.crop ?? "",
      growth_stage: stored?.growth_stage ?? "",
      soil_type: target?.soil_type ?? "",
      irrigation_method: stored?.irrigation_method ?? "",
      soil_moisture: form.getValues("soil_moisture"),
      recent_rainfall_mm: form.getValues("recent_rainfall_mm"),
      sowing_date: stored?.sowing_date ?? "",
    });
  }

  // Start from what the farmer already told us about the selected farm and crop.
  const selectedKey = `${farm?.id}:${crop?.id}:${crop?.growth_stage}`;
  useEffect(() => {
    if (farm) applyFarm(farm.id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedKey]);

  function submit(values: Values) {
    const isOther = values.place === ANOTHER_PLACE;
    if (isOther && !picked) {
      setPlaceError("Choose a location first. Weather is looked up by location.");
      return;
    }
    setPlaceError(null);
    const record = chosenFarm?.crops.find((item) => item.crop === values.crop) ?? null;
    const body: IrrigationRequest = {
      farm_id: chosenFarm?.id ?? null,
      farm_crop_id: record?.id ?? null,
      latitude: isOther ? (picked as PickedPlace).latitude : null,
      longitude: isOther ? (picked as PickedPlace).longitude : null,
      crop: values.crop,
      growth_stage: values.growth_stage || null,
      soil_type: values.soil_type || null,
      irrigation_method: values.irrigation_method || null,
      soil_moisture: values.soil_moisture,
      recent_rainfall_mm: values.recent_rainfall_mm.trim() === "" ? null : Number(values.recent_rainfall_mm),
      sowing_date: values.sowing_date || null,
    };
    setLastRequest(body);
    assess.mutate(body);
  }

  const errors = form.formState.errors;

  return (
    <div className="space-y-5">
      <PageHeader
        title="Irrigation Advisor"
        description="FarmAgent retrieves the weather first, then weighs it against your crop's stage and your soil. The more you tell it, the firmer the result."
      />

      <div className="grid items-start gap-5 lg:grid-cols-[21rem_minmax(0,1fr)]">
        <form
          onSubmit={form.handleSubmit(submit)}
          className="panel grid gap-4 p-4 sm:p-5 lg:sticky lg:top-6"
          aria-label="Irrigation details"
          noValidate
        >
          {catalog.isError && <ErrorState compact error={catalog.error} onRetry={() => catalog.refetch()} />}
          <Controller
            control={form.control}
            name="place"
            render={({ field }) => (
              <PlaceField
                farms={farms}
                value={field.value}
                onChange={(value) => {
                  setPlaceError(null);
                  if (value === ANOTHER_PLACE) field.onChange(value);
                  else applyFarm(value);
                }}
                picked={picked}
                onPick={(next) => {
                  setPlaceError(null);
                  setPicked(next);
                }}
              />
            )}
          />
          {placeError && (
            <p role="alert" className="text-xs font-medium text-clay-ink">
              {placeError}
            </p>
          )}

          <Field id="crop" label="Crop" error={errors.crop?.message} hint={cropProfile?.support_level === "planned" ? cropProfile.support_note : undefined}>
            <Controller
              control={form.control}
              name="crop"
              render={({ field }) => (
                <SelectField
                  id="crop"
                  value={field.value}
                  invalid={Boolean(errors.crop)}
                  onChange={(value) => {
                    field.onChange(value);
                    form.setValue("growth_stage", "");
                  }}
                  options={(catalog.data?.crops ?? []).map((item) => ({
                    value: item.id,
                    label:
                      item.support_level === "planned" ? `${item.name} (rules not yet available)` : item.name,
                  }))}
                />
              )}
            />
          </Field>

          {cropProfile && cropProfile.stages.length > 0 && (
            <Field id="growth_stage" label="Growth stage" hint="Without it, FarmAgent cannot check whether this is a critical stage.">
              <Controller
                control={form.control}
                name="growth_stage"
                render={({ field }) => (
                  <SelectField
                    id="growth_stage"
                    value={field.value}
                    onChange={field.onChange}
                    clearLabel="Not sure"
                    options={cropProfile.stages.map((stage) => ({ value: stage.id, label: stage.label }))}
                  />
                )}
              />
            </Field>
          )}

          <Field id="soil_moisture" label="Soil moisture" hint="Feel the soil at root depth if you can. It is the most useful thing you can add.">
            <Controller
              control={form.control}
              name="soil_moisture"
              render={({ field }) => (
                <SelectField
                  id="soil_moisture"
                  value={field.value}
                  onChange={field.onChange}
                  options={(["unknown", "low", "adequate", "high"] as SoilMoisture[]).map((value) => ({
                    value,
                    label: MOISTURE_LABEL[value],
                  }))}
                />
              )}
            />
          </Field>

          <Field id="soil_type" label="Soil type" optional>
            <Controller
              control={form.control}
              name="soil_type"
              render={({ field }) => (
                <SelectField
                  id="soil_type"
                  value={field.value}
                  onChange={field.onChange}
                  clearLabel="Not sure"
                  options={(catalog.data?.soil_types ?? []).map((value) => ({ value, label: words(value) }))}
                />
              )}
            />
          </Field>

          <Field id="irrigation_method" label="Irrigation method" optional>
            <Controller
              control={form.control}
              name="irrigation_method"
              render={({ field }) => (
                <SelectField
                  id="irrigation_method"
                  value={field.value}
                  onChange={field.onChange}
                  clearLabel="Not sure"
                  options={(catalog.data?.irrigation_methods ?? []).map((value) => ({ value, label: words(value) }))}
                />
              )}
            />
          </Field>

          <Field
            id="recent_rainfall_mm"
            label="Rain in the last few days, mm"
            optional
            error={errors.recent_rainfall_mm?.message}
          >
            <Input
              id="recent_rainfall_mm"
              inputMode="decimal"
              aria-invalid={Boolean(errors.recent_rainfall_mm) || undefined}
              {...form.register("recent_rainfall_mm")}
            />
          </Field>
          <Field id="sowing_date" label="Sowing date" optional>
            <Input id="sowing_date" type="date" max={todayIso()} {...form.register("sowing_date")} />
          </Field>

          <Button type="submit" size="lg" disabled={assess.isPending || catalog.isPending || isLoading}>
            <Droplets aria-hidden="true" />
            {assess.isPending ? "Checking the weather…" : "Assess irrigation"}
          </Button>
          <p className="flex gap-1.5 text-xs text-muted-foreground">
            <Info className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
            Guidance only. Your own field knowledge and your extension officer come first.
          </p>
        </form>

        <div className="min-w-0" aria-live="polite">
          {assess.isPending && <LoadingState label="Retrieving weather and assessing irrigation" />}
          {assess.isError && <ErrorState error={assess.error} onRetry={() => form.handleSubmit(submit)()} />}
          {assess.data && !assess.isPending && lastRequest && <Result data={assess.data} request={lastRequest} />}
          {assess.isIdle && (
            <EmptyState title="Your assessment will appear here" icon={Droplets}>
              Check the details on this page, then choose Assess irrigation. Nothing is assessed until
              verified weather has been retrieved for this location.
            </EmptyState>
          )}
        </div>
      </div>
    </div>
  );
}
