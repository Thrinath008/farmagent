import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronDown, History, MessageSquareText, Trash2 } from "lucide-react";
import { Link } from "react-router";
import { toast } from "sonner";
import { AdviceCard } from "@/components/advice/AdviceCard";
import { RiskChip } from "@/components/decision/StatusIndicator";
import { ConfirmDialog } from "@/components/forms/ConfirmDialog";
import { Field, SelectField } from "@/components/forms/Field";
import { PageHeader } from "@/components/layout/PageHeader";
import { ProvenanceBadge } from "@/components/provenance/ProvenanceBadge";
import { EmptyState, ErrorState, LoadingState } from "@/components/states/States";
import { Button } from "@/components/ui/button";
import { keys } from "@/hooks/queries";
import { dateTime } from "@/lib/format";
import { INTENT_LABEL, ORIGIN_LABEL } from "@/lib/labels";
import { cn } from "@/lib/utils";
import { useFarmContext } from "@/providers/FarmProvider";
import { api, ApiError } from "@/services/api";
import type { Recommendation } from "@/types/api";

function Row({ item }: { item: Recommendation }) {
  const client = useQueryClient();
  const [open, setOpen] = useState(false);
  const remove = useMutation({
    mutationFn: () => api.deleteRecommendation(item.id),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: keys.recommendations });
      toast.success("Deleted from history");
    },
    onError: (error) => toast.error(error instanceof ApiError ? error.message : "It could not be deleted."),
  });
  return (
    <li className="py-1" data-testid={`recommendation-${item.id}`}>
      <div className="flex items-start gap-2">
        <button
          type="button"
          aria-expanded={open}
          onClick={() => setOpen((value) => !value)}
          className="flex min-w-0 flex-1 items-start gap-2 rounded px-1 py-2.5 text-left hover:bg-muted/60"
        >
          <ChevronDown
            className={cn("mt-0.5 size-4 shrink-0 text-muted-foreground transition-transform", open && "rotate-180")}
            aria-hidden="true"
          />
          <span className="min-w-0">
            <span className="block font-medium">{item.recommendation ?? item.summary}</span>
            <span className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
              <span className="font-mono">{dateTime(item.created_at)}</span>
              <span>· {INTENT_LABEL[item.intent] ?? item.intent}</span>
              <span>· {ORIGIN_LABEL[item.origin] ?? item.origin}</span>
            </span>
          </span>
        </button>
        <div className="flex shrink-0 flex-wrap items-center justify-end gap-2 py-2">
          {item.weather_provenance && (
            <ProvenanceBadge provenance={item.weather_provenance} historical className="hidden sm:inline-flex" />
          )}
          {item.risk_level !== "not_applicable" && (
            <span className="hidden md:inline-flex">
              <RiskChip level={item.risk_level} />
            </span>
          )}
          <ConfirmDialog
            title="Delete this recommendation?"
            description="It will be removed from your history. This cannot be undone."
            confirmLabel="Delete"
            onConfirm={() => remove.mutate()}
            trigger={
              <Button variant="ghost" size="icon-sm" aria-label="Delete this recommendation">
                <Trash2 aria-hidden="true" />
              </Button>
            }
          />
        </div>
      </div>
      {open && (
        <div className="pb-3 pl-7">
          <AdviceCard
            historical
            advice={item.advice}
            footer={
              item.conversation_id && (
                <Button variant="outline" size="sm" asChild>
                  <Link to={`/assistant/${item.conversation_id}`}>
                    <MessageSquareText aria-hidden="true" /> Open the conversation
                  </Link>
                </Button>
              )
            }
          />
        </div>
      )}
    </li>
  );
}

export function HistoryPage() {
  const { farms } = useFarmContext();
  const [intent, setIntent] = useState("");
  const [farmId, setFarmId] = useState("");
  const query = useQuery({
    queryKey: [...keys.recommendations, "history", intent, farmId],
    queryFn: () => api.recommendations({ limit: 100, intent: intent || null, farm_id: farmId || null }),
  });
  const filtered = Boolean(intent || farmId);

  return (
    <div className="space-y-5">
      <PageHeader
        title="Farming History"
        description="Recommendations you saved, with the weather they were based on at the time. Old advice describes old conditions, so reassess before acting on it."
      />

      <div className="grid gap-3 sm:grid-cols-2 lg:max-w-xl">
        <Field id="history-intent" label="Topic">
          <SelectField
            id="history-intent"
            value={intent}
            onChange={setIntent}
            clearLabel="All topics"
            options={Object.entries(INTENT_LABEL).map(([value, label]) => ({ value, label }))}
          />
        </Field>
        {farms.length > 0 && (
          <Field id="history-farm" label="Farm">
            <SelectField
              id="history-farm"
              value={farmId}
              onChange={setFarmId}
              clearLabel="All farms"
              options={farms.map((farm) => ({
                value: farm.id,
                label: farm.name ?? farm.location_name ?? "Unnamed farm",
              }))}
            />
          </Field>
        )}
      </div>

      {query.isPending && <LoadingState label="Loading your history" />}
      {query.isError && <ErrorState error={query.error} onRetry={() => query.refetch()} />}
      {query.data?.length === 0 && (
        <EmptyState
          icon={History}
          title={filtered ? "Nothing matches these filters" : "No saved recommendations yet"}
          action={
            filtered ? (
              <Button
                variant="outline"
                onClick={() => {
                  setIntent("");
                  setFarmId("");
                }}
              >
                Clear filters
              </Button>
            ) : (
              <Button variant="outline" asChild>
                <Link to="/irrigation">Open the Irrigation Advisor</Link>
              </Button>
            )
          }
        >
          {!filtered && "Choose Save to history on any assessment or assistant answer to keep it here."}
        </EmptyState>
      )}
      {query.data && query.data.length > 0 && (
        <ul className="panel divide-y divide-border px-3 sm:px-4">
          {query.data.map((item) => (
            <Row key={item.id} item={item} />
          ))}
        </ul>
      )}
    </div>
  );
}
