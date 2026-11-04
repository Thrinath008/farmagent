import { useId, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { Equal, FlaskConical, LoaderCircle, MoveRight } from "lucide-react";
import { AdviceCard } from "@/components/advice/AdviceCard";
import { WeightBlocks } from "@/components/decision/DecisionLedger";
import { ConfidenceLabel, RiskChip, StatusIndicator } from "@/components/decision/StatusIndicator";
import { PageHeader } from "@/components/layout/PageHeader";
import { ProvenanceBadge } from "@/components/provenance/ProvenanceBadge";
import { ErrorState, LoadingState } from "@/components/states/States";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { keys, useHealth } from "@/hooks/queries";
import { mm, percent, signed, temp, windKmh, words } from "@/lib/format";
import { ACTION_LABEL } from "@/lib/labels";
import { cn } from "@/lib/utils";
import { api } from "@/services/api";
import type { FactorComparison, ScenarioDefinition, ScenarioResult, ScenarioRun } from "@/types/api";

function SimulatedNotice({ text }: { text: string }) {
  return (
    <div className="hatched rounded border border-dashed border-amber-mark p-3.5 text-sm text-amber-ink sm:p-4">
      <span className="rounded-[2px] bg-card px-2.5 py-1.5 leading-relaxed [box-decoration-break:clone]">
        <strong className="font-mono text-xs tracking-wide uppercase">Simulated data</strong>{" "}
        <span className="text-ink">{text}</span>
      </span>
    </div>
  );
}

function ScenarioCard({ scenario }: { scenario: ScenarioDefinition }) {
  const { inputs } = scenario;
  const rows: [string, string][] = [
    ["Temperature", temp(inputs.temperature_c)],
    ["Humidity", percent(inputs.humidity_pct)],
    ["Chance of rain", percent(inputs.rain_probability_pct)],
    ["Expected rain", mm(inputs.expected_rain_mm)],
    ["Wind", windKmh(inputs.wind_speed_ms)],
    ["Soil moisture", words(inputs.soil_moisture)],
    ["Crop", words(inputs.crop)],
    ["Growth stage", words(inputs.growth_stage)],
  ];
  return (
    <article className="panel p-4 sm:p-5" data-testid={`scenario-${scenario.id}`}>
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="eyebrow">Scenario {scenario.id}</p>
          <h2 className="display mt-1 text-xl">{scenario.title}</h2>
        </div>
        <ProvenanceBadge provenance="simulated" />
      </div>
      <p className="mt-1.5 text-sm text-muted-foreground">{scenario.description}</p>
      <dl className="mt-4 grid grid-cols-2 gap-x-4 gap-y-2.5">
        {rows.map(([label, value]) => (
          <div key={label}>
            <dt className="text-xs text-muted-foreground">{label}</dt>
            <dd className="font-medium">{value}</dd>
          </div>
        ))}
      </dl>
    </article>
  );
}

function Outcome({ result }: { result: ScenarioResult }) {
  const { assessment, pest_risk: risk } = result;
  return (
    <article className="panel p-4 sm:p-5" data-testid={`outcome-${result.definition.id}`}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="eyebrow">Scenario {result.definition.id} · {result.definition.title}</p>
        <ProvenanceBadge provenance={result.provenance} />
      </div>
      <div className="mt-3">
        <StatusIndicator status={assessment.status} large />
      </div>
      <h3 className="display mt-3 text-lg sm:text-xl">{assessment.headline}</h3>
      <p className="mt-2 text-sm leading-relaxed">{assessment.summary}</p>
      <dl className="mt-4 grid grid-cols-2 gap-x-4 gap-y-3 border-t border-border pt-3 text-sm">
        <div>
          <dt className="text-xs text-muted-foreground">Action</dt>
          <dd className="font-medium">{ACTION_LABEL[assessment.action]}</dd>
        </div>
        <div>
          <dt className="text-xs text-muted-foreground">Rule score</dt>
          <dd className="numeral text-lg">{signed(assessment.score)}</dd>
        </div>
        <div>
          <dt className="text-xs text-muted-foreground">Weather-related crop risk</dt>
          <dd className="mt-1">
            <RiskChip level={risk.overall_classification} />
          </dd>
        </div>
        <div className="self-end">
          <ConfidenceLabel confidence={assessment.confidence} note={assessment.confidence_note} />
        </div>
      </dl>
      <p className="mt-3 text-sm text-muted-foreground">{assessment.next_action}</p>
    </article>
  );
}

function InputDifferences({ run }: { run: ScenarioRun }) {
  return (
    <section className="panel overflow-x-auto p-4 sm:p-5" aria-labelledby="inputs-heading">
      <h2 id="inputs-heading" className="display text-lg">
        What differs between the scenarios
      </h2>
      <table className="mt-3 w-full min-w-[26rem] text-left text-sm">
        <thead className="text-xs text-muted-foreground">
          <tr className="border-b border-border">
            <th scope="col" className="py-2 pr-4 font-medium">Input</th>
            <th scope="col" className="py-2 pr-4 font-medium">Scenario A</th>
            <th scope="col" className="py-2 pr-4 font-medium">Scenario B</th>
            <th scope="col" className="py-2 font-medium">
              <span className="sr-only">Same or different</span>
            </th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border">
          {run.input_differences.map((row) => (
            <tr key={row.key} className={row.differs ? "" : "text-muted-foreground"} data-differs={row.differs}>
              <th scope="row" className="py-2 pr-4 font-normal">{row.label}</th>
              <td className={cn("py-2 pr-4", row.differs && "font-medium")}>{row.values.A}</td>
              <td className={cn("py-2 pr-4", row.differs && "font-medium")}>{row.values.B}</td>
              <td className="py-2 text-xs whitespace-nowrap">
                {row.differs ? (
                  <span className="inline-flex items-center gap-1 text-amber-ink">
                    <MoveRight className="size-3.5" aria-hidden="true" /> Differs
                  </span>
                ) : (
                  <span className="inline-flex items-center gap-1">
                    <Equal className="size-3.5" aria-hidden="true" /> Same
                  </span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

function FactorSide({ factor, id, units }: { factor: FactorComparison; id: "A" | "B"; units: number }) {
  return (
    <div className="min-w-0">
      <p className="flex flex-wrap items-baseline gap-x-2 text-sm">
        <span className="eyebrow">{id}</span>
        <span className="font-mono text-xs">{factor.values[id]}</span>
      </p>
      <div className="mt-1.5">
        <WeightBlocks weight={factor.weights[id] ?? 0} units={units} />
      </div>
      <p className="mt-1.5 text-sm text-muted-foreground">{factor.explanations[id]}</p>
    </div>
  );
}

function FactorComparisonView({ run }: { run: ScenarioRun }) {
  const units = Math.max(
    3,
    ...run.factor_comparison.flatMap((factor) => Object.values(factor.weights).map(Math.abs)),
  );
  return (
    <section className="panel p-4 sm:p-5" aria-labelledby="factors-heading">
      <h2 id="factors-heading" className="display text-lg">
        How each factor counted
      </h2>
      <div className="mt-2 flex flex-wrap items-center gap-4 text-xs text-muted-foreground" aria-hidden="true">
        <span className="inline-flex items-center gap-1.5">
          <span className="size-2.5 rounded-[1px] bg-rain-mark" /> Against irrigating
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span className="size-2.5 rounded-[1px] bg-shoot" /> Supports irrigating
        </span>
      </div>
      <ul className="mt-3 divide-y divide-border border-t border-border">
        {run.factor_comparison.map((factor) => (
          <li key={factor.key} className="py-3" data-testid={`comparison-${factor.key}`}>
            <p className="text-sm font-medium">{factor.label}</p>
            <div className="mt-2 grid gap-4 md:grid-cols-2">
              <FactorSide factor={factor} id="A" units={units} />
              <FactorSide factor={factor} id="B" units={units} />
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}

function AgentRecommendation({ result, asked }: { result: ScenarioResult; asked: boolean }) {
  const { ai, definition } = result;
  return (
    <div className="grid content-start gap-3" data-testid={`recommendation-${definition.id}`}>
      <h3 className="display text-base">Scenario {definition.id}</h3>
      <p className="eyebrow">From the rule-based engine</p>
      <AdviceCard advice={result.advice} />
      {asked && ai.status === "completed" && ai.advice && (
        <>
          <p className="eyebrow mt-2">Claude's explanation</p>
          <AdviceCard advice={ai.advice} />
        </>
      )}
      {asked && ai.status === "unavailable" && (
        <p className="rounded border border-dashed border-input p-3 text-sm text-muted-foreground" role="status">
          Claude's explanation is unavailable: {ai.message} The rule-based result above is unaffected.
        </p>
      )}
    </div>
  );
}

export function ScenarioLabPage() {
  const checkboxId = useId();
  const health = useHealth();
  const [includeAi, setIncludeAi] = useState(false);
  const [askedAi, setAskedAi] = useState(false);
  const scenarios = useQuery({ queryKey: keys.scenarios, queryFn: api.scenarios, staleTime: Infinity });
  const run = useMutation({ mutationFn: (withAi: boolean) => api.runScenarios({ include_ai: withAi }) });
  const aiReady = Boolean(health.data?.ai_configured);

  function runBoth() {
    const withAi = includeAi && aiReady;
    setAskedAi(withAi);
    run.mutate(withAi);
  }

  return (
    <div className="space-y-5">
      <PageHeader
        title="Scenario Lab"
        description="The same wheat field under two made-up weather patterns. Both go through the real decision engine, so you can see exactly why the advice changes."
      />
      <SimulatedNotice text="All weather on this page is made up to show how the engine responds. It is not real weather and must not be used to make decisions in the field." />

      {scenarios.isPending && <LoadingState label="Loading scenarios" />}
      {scenarios.isError && <ErrorState error={scenarios.error} onRetry={() => scenarios.refetch()} />}
      {scenarios.data && (
        <div className="grid gap-5 md:grid-cols-2">
          {scenarios.data.map((scenario) => (
            <ScenarioCard key={scenario.id} scenario={scenario} />
          ))}
        </div>
      )}

      <section className="flex flex-wrap items-center gap-x-6 gap-y-3 rounded bg-forest p-4 text-white sm:p-5" aria-label="Run the scenarios">
        <Button
          size="lg"
          onClick={runBoth}
          disabled={run.isPending || !scenarios.data}
          className="bg-sidebar-primary text-forest hover:bg-sidebar-primary/90"
        >
          {run.isPending ? (
            <LoaderCircle className="animate-spin" aria-hidden="true" />
          ) : (
            <FlaskConical aria-hidden="true" />
          )}
          {run.isPending ? (includeAi && aiReady ? "Running, Claude can take a minute…" : "Running…") : "Run Both Scenarios"}
        </Button>
        <div className="flex items-center gap-2.5">
          <Checkbox
            id={checkboxId}
            checked={includeAi && aiReady}
            disabled={!aiReady}
            onCheckedChange={(value) => setIncludeAi(value === true)}
            className="border-white/60 data-checked:border-sidebar-primary data-checked:bg-sidebar-primary data-checked:text-forest"
          />
          <Label htmlFor={checkboxId} className="text-sm leading-snug font-normal text-white/90">
            {aiReady
              ? "Also ask Claude to explain each scenario (slower, uses API credits)"
              : "Claude's explanation needs an Anthropic key on the server. The engine result does not."}
          </Label>
        </div>
      </section>

      <div aria-live="polite" className="space-y-5">
        {run.isError && <ErrorState error={run.error} onRetry={runBoth} />}
        {run.data && !run.isPending && (
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.25 }}
            className="space-y-5"
            data-testid="scenario-results"
          >
            <h2 className="display text-xl sm:text-2xl">
              {run.data.outcomes_differ
                ? "Same crop, same stage. Different weather, different advice."
                : "Both scenarios led to the same advice."}
            </h2>
            <div className="grid gap-5 md:grid-cols-2">
              {run.data.results.map((result) => (
                <Outcome key={result.definition.id} result={result} />
              ))}
            </div>
            <InputDifferences run={run.data} />
            <FactorComparisonView run={run.data} />
            <section aria-labelledby="reasoning-heading">
              <h2 id="reasoning-heading" className="display text-lg">
                Recommendations and reasoning
              </h2>
              <div className="mt-3 grid gap-5 md:grid-cols-2">
                {run.data.results.map((result) => (
                  <AgentRecommendation key={result.definition.id} result={result} asked={askedAi} />
                ))}
              </div>
            </section>
          </motion.div>
        )}
      </div>
    </div>
  );
}
