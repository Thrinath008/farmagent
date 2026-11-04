import { useEffect, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { Leaf, ShieldAlert } from "lucide-react";
import { Link } from "react-router";
import { SaveRecommendationButton } from "@/components/advice/AdviceCard";
import { SourceList } from "@/components/advice/SourceList";
import { ConfidenceLabel, RiskChip } from "@/components/decision/StatusIndicator";
import { Field, SelectField } from "@/components/forms/Field";
import type { PickedPlace } from "@/components/forms/LocationPicker";
import { PlaceField } from "@/components/forms/PlaceField";
import { PageHeader } from "@/components/layout/PageHeader";
import { ProvenanceBadge } from "@/components/provenance/ProvenanceBadge";
import { EmptyState, ErrorState, LoadingState } from "@/components/states/States";
import { Button } from "@/components/ui/button";
import { useCatalog } from "@/hooks/queries";
import { secondsSince } from "@/lib/format";
import { ANOTHER_PLACE } from "@/lib/labels";
import { useFarmContext } from "@/providers/FarmProvider";
import { api, ApiError } from "@/services/api";
import type { AssessmentTarget, PestRiskResponse, PotentialRisk } from "@/types/api";

const CATEGORY_LABEL: Record<string, string> = {
  fungal: "Fungal disease",
  insect: "Insect pest",
  abiotic: "Heat stress",
};

function RiskRow({ risk }: { risk: PotentialRisk }) {
  return (
    <li>
      <details className="group" data-testid={`risk-${risk.id}`}>
        <summary className="flex cursor-pointer list-none flex-wrap items-center justify-between gap-x-4 gap-y-1.5 py-3 [&::-webkit-details-marker]:hidden">
          <span className="min-w-0">
            <span className="font-medium">{risk.name}</span>{" "}
            <span className="text-xs text-muted-foreground">{CATEGORY_LABEL[risk.category] ?? risk.category}</span>
          </span>
          <RiskChip level={risk.classification} />
        </summary>
        <div className="grid gap-4 pb-4 text-sm md:grid-cols-2">
          <div>
            <h4 className="font-medium">Why this was flagged</h4>
            <ul className="mt-1 list-disc space-y-1 pl-5">
              {risk.evidence.map((line) => (
                <li key={line}>{line}</li>
              ))}
            </ul>
            <h4 className="mt-3 font-medium">Conditions published as favourable</h4>
            <p className="mt-1 text-muted-foreground">{risk.favorable_conditions}</p>
            {risk.regional_note && <p className="mt-2 text-muted-foreground">{risk.regional_note}</p>}
          </div>
          <div>
            <h4 className="font-medium">What to look for</h4>
            <ul className="mt-1 list-disc space-y-1 pl-5">
              {risk.monitoring_actions.map((line) => (
                <li key={line}>{line}</li>
              ))}
            </ul>
            <div className="mt-3">
              <SourceList sources={risk.sources} />
            </div>
          </div>
        </div>
      </details>
    </li>
  );
}

function Result({ data, target }: { data: PestRiskResponse; target: AssessmentTarget }) {
  const { assessment, weather, weather_issues: issues } = data;
  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2 }}
      className="space-y-5"
      data-testid="risk-result"
    >
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

      <section className="panel p-4 sm:p-6" aria-labelledby="risk-heading">
        <div className="flex flex-wrap items-center gap-3">
          <RiskChip level={assessment.overall_classification} prefix="Weather-related risk" />
          <ProvenanceBadge
            className="ml-auto"
            provenance={assessment.weather_provenance}
            isStale={weather?.is_stale}
            ageSeconds={secondsSince(weather?.observed_at)}
            source={weather?.source}
          />
        </div>
        <h2 id="risk-heading" className="display mt-4 text-xl sm:text-2xl">
          {assessment.headline}
        </h2>
        <p className="mt-2 text-[0.9375rem] leading-relaxed">{assessment.explanation}</p>
        {assessment.crop_sensitivity && (
          <p className="mt-3 text-sm text-muted-foreground">
            <span className="font-medium text-foreground">Crop sensitivity: </span>
            {assessment.crop_sensitivity}
          </p>
        )}
        <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
          <ConfidenceLabel confidence={assessment.confidence} note={assessment.confidence_note} />
          {assessment.confidence !== "insufficient" && (
            <SaveRecommendationButton
              input={{
                advice: data.advice,
                origin: "crop_health",
                farm_id: target.farm_id ?? null,
                crop: assessment.crop,
                latitude: target.latitude ?? null,
                longitude: target.longitude ?? null,
              }}
            />
          )}
        </div>
      </section>

      {assessment.environmental_conditions.length > 0 && (
        <section className="panel p-4 sm:p-5" aria-labelledby="conditions-heading">
          <h3 id="conditions-heading" className="display text-base">
            Environmental conditions
          </h3>
          <dl className="mt-3 grid grid-cols-2 gap-x-5 gap-y-3 sm:grid-cols-3 lg:grid-cols-4">
            {assessment.environmental_conditions.map((row) => (
              <div key={row.label}>
                <dt className="text-xs text-muted-foreground">{row.label}</dt>
                <dd className="numeral mt-1 text-lg">{row.value}</dd>
              </div>
            ))}
          </dl>
        </section>
      )}

      {assessment.risks.length > 0 && (
        <section className="panel px-4 pt-4 pb-1 sm:px-5" aria-labelledby="potential-heading">
          <h3 id="potential-heading" className="display text-base">
            Potential risks
          </h3>
          <p className="mt-1 text-sm text-muted-foreground">
            Highest first. Open a row for the reasoning and what to look for in the field.
          </p>
          <ul className="mt-2 divide-y divide-border border-t border-border">
            {assessment.risks.map((risk) => (
              <RiskRow key={risk.id} risk={risk} />
            ))}
          </ul>
        </section>
      )}

      {assessment.missing_information.length > 0 && (
        <section className="panel p-4 sm:p-5">
          <h3 className="display text-base">What is still unknown</h3>
          <ul className="mt-2 list-disc space-y-1 pl-5 text-sm">
            {assessment.missing_information.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </section>
      )}
    </motion.div>
  );
}

export function CropHealthPage() {
  const { farms, farm, crop } = useFarmContext();
  const catalog = useCatalog();
  const [place, setPlace] = useState(ANOTHER_PLACE);
  const [picked, setPicked] = useState<PickedPlace | null>(null);
  const [cropId, setCropId] = useState("");
  const [stage, setStage] = useState("");
  const [formError, setFormError] = useState<string | null>(null);
  const [target, setTarget] = useState<AssessmentTarget | null>(null);
  const assess = useMutation({ mutationFn: (body: AssessmentTarget) => api.assessPestRisk(body) });

  const chosenFarm = farms.find((item) => item.id === place) ?? null;
  const profile = catalog.data?.crops.find((item) => item.id === cropId);

  function applyFarm(farmId: string) {
    const next = farms.find((item) => item.id === farmId);
    const stored = next?.id === farm?.id ? crop : (next?.crops[0] ?? null);
    setPlace(farmId);
    setCropId(stored?.crop ?? "");
    setStage(stored?.growth_stage ?? "");
  }

  const selectedKey = `${farm?.id}:${crop?.id}:${crop?.growth_stage}`;
  useEffect(() => {
    if (farm) applyFarm(farm.id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedKey]);

  function run() {
    if (place === ANOTHER_PLACE && !picked) {
      setFormError("Choose a location first. Weather is looked up by location.");
      return;
    }
    if (!cropId) {
      setFormError("Choose a crop.");
      return;
    }
    setFormError(null);
    const record = chosenFarm?.crops.find((item) => item.crop === cropId) ?? null;
    const body: AssessmentTarget = {
      farm_id: chosenFarm?.id ?? null,
      farm_crop_id: record?.id ?? null,
      latitude: place === ANOTHER_PLACE ? (picked as PickedPlace).latitude : null,
      longitude: place === ANOTHER_PLACE ? (picked as PickedPlace).longitude : null,
      crop: cropId,
      growth_stage: stage || null,
    };
    setTarget(body);
    assess.mutate(body);
  }

  return (
    <div className="space-y-5">
      <PageHeader
        title="Crop Health & Risk"
        description="Whether the coming weather favours problems your crop is known to face, and what to scout for."
      />

      <p
        className="flex gap-3 rounded border border-amber-mark/50 bg-amber-wash p-4 text-sm text-amber-ink"
        data-testid="diagnosis-disclaimer"
      >
        <ShieldAlert className="mt-0.5 size-5 shrink-0" aria-hidden="true" />
        <span>
          <strong className="font-semibold">This is a weather-based risk assessment, not a plant disease diagnosis.</strong>{" "}
          Weather can show that conditions favour a problem. It cannot show that the problem is in your
          field. Inspect the crop, and speak to your agricultural extension officer or Krishi Vigyan
          Kendra before any treatment.
        </span>
      </p>

      <div className="grid items-start gap-5 lg:grid-cols-[21rem_minmax(0,1fr)]">
        <div className="panel grid gap-4 p-4 sm:p-5 lg:sticky lg:top-6">
          {catalog.isError && <ErrorState compact error={catalog.error} onRetry={() => catalog.refetch()} />}
          <PlaceField
            farms={farms}
            value={place}
            onChange={(value) => {
              setFormError(null);
              if (value === ANOTHER_PLACE) setPlace(value);
              else applyFarm(value);
            }}
            picked={picked}
            onPick={(next) => {
              setFormError(null);
              setPicked(next);
            }}
          />
          <Field id="risk-crop" label="Crop" hint={profile?.support_level === "planned" ? profile.support_note : undefined}>
            <SelectField
              id="risk-crop"
              value={cropId}
              onChange={(value) => {
                setCropId(value);
                setStage("");
                setFormError(null);
              }}
              options={(catalog.data?.crops ?? []).map((item) => ({
                value: item.id,
                label: item.support_level === "planned" ? `${item.name} (rules not yet available)` : item.name,
              }))}
            />
          </Field>
          {profile && profile.stages.length > 0 && (
            <Field id="risk-stage" label="Growth stage" hint="Some risks only matter at certain stages.">
              <SelectField
                id="risk-stage"
                value={stage}
                onChange={setStage}
                clearLabel="Not sure"
                options={profile.stages.map((item) => ({ value: item.id, label: item.label }))}
              />
            </Field>
          )}
          {formError && (
            <p role="alert" className="text-xs font-medium text-clay-ink">
              {formError}
            </p>
          )}
          <Button size="lg" onClick={run} disabled={assess.isPending || catalog.isPending}>
            <Leaf aria-hidden="true" />
            {assess.isPending ? "Checking the weather…" : "Check weather-related risk"}
          </Button>
        </div>

        <div className="min-w-0" aria-live="polite">
          {assess.isPending && <LoadingState label="Retrieving weather and assessing risk" />}
          {assess.isError && <ErrorState error={assess.error} onRetry={run} />}
          {assess.data && !assess.isPending && target && <Result data={assess.data} target={target} />}
          {assess.isIdle && (
            <EmptyState title="Your risk assessment will appear here" icon={Leaf}>
              Choose a farm and crop, then run the check. Risks are compared against the forecast for
              your location.
            </EmptyState>
          )}
        </div>
      </div>
    </div>
  );
}
