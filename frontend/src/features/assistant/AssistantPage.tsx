import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Check,
  CircleX,
  LoaderCircle,
  MessageSquarePlus,
  SendHorizontal,
  Square,
  Trash2,
} from "lucide-react";
import { Link, useNavigate, useParams } from "react-router";
import { toast } from "sonner";
import { AdviceCard, SaveRecommendationButton } from "@/components/advice/AdviceCard";
import { ConfirmDialog } from "@/components/forms/ConfirmDialog";
import { PageHeader } from "@/components/layout/PageHeader";
import { ProvenanceBadge } from "@/components/provenance/ProvenanceBadge";
import { EmptyState, ErrorState, LoadingState } from "@/components/states/States";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { keys, useHealth } from "@/hooks/queries";
import { dateTime, secondsSince } from "@/lib/format";
import { SUGGESTED_QUESTIONS, TOOL_LABEL } from "@/lib/labels";
import { cn } from "@/lib/utils";
import { useFarmContext } from "@/providers/FarmProvider";
import { api, ApiError, streamChat } from "@/services/api";
import type { AgentEvent, ChatMessage, DataProvenance, ToolLogEntry } from "@/types/api";

const MAX_MESSAGE = 4000;

interface Step {
  id: string;
  name: string;
  state: "running" | "ok" | "failed";
  durationMs?: number;
  provenance?: string | null;
}

interface Turn {
  question: string;
  steps: Step[];
  error: unknown;
  running: boolean;
}

function toolLabel(name: string): string {
  return TOOL_LABEL[name] ?? name.replaceAll("_", " ");
}

function isWeatherProvenance(value: string | null | undefined): value is DataProvenance {
  return value === "live" || value === "cached" || value === "simulated" || value === "unavailable";
}

function seconds(ms: number): string {
  return ms < 100 ? "<0.1 s" : `${(ms / 1000).toFixed(1)} s`;
}

/** An answer read after this long is a record of earlier conditions, whatever it was based on then. */
const FRESH_SECONDS = 600;

function isOld(createdAt: string): boolean {
  return (secondsSince(createdAt) ?? 0) > FRESH_SECONDS;
}

function StepRow({ step, historical }: { step: Step; historical?: boolean }) {
  return (
    <li className="flex flex-wrap items-center gap-2 text-sm">
      {step.state === "running" && (
        <LoaderCircle className="size-4 animate-spin text-muted-foreground" aria-hidden="true" />
      )}
      {step.state === "ok" && <Check className="size-4 text-shoot-ink" aria-hidden="true" />}
      {step.state === "failed" && <CircleX className="size-4 text-clay-ink" aria-hidden="true" />}
      <span>
        {toolLabel(step.name)}
        {step.state === "failed" && <span className="text-clay-ink"> (this failed)</span>}
      </span>
      {step.durationMs !== undefined && (
        <span className="font-mono text-xs text-muted-foreground">{seconds(step.durationMs)}</span>
      )}
      {isWeatherProvenance(step.provenance) && (
        <ProvenanceBadge provenance={step.provenance} historical={historical} className="!py-0.5" />
      )}
    </li>
  );
}

function CheckedTools({ log, historical }: { log: ToolLogEntry[]; historical: boolean }) {
  if (log.length === 0) return null;
  return (
    <details className="mt-2 text-sm">
      <summary className="cursor-pointer text-muted-foreground">
        What FarmAgent checked ({log.length} {log.length === 1 ? "step" : "steps"})
      </summary>
      <ol className="mt-2 grid gap-1.5">
        {log.map((entry, index) => (
          <StepRow
            key={`${entry.name}-${index}`}
            historical={historical}
            step={{
              id: String(index),
              name: entry.name,
              state: entry.ok ? "ok" : "failed",
              durationMs: entry.duration_ms,
              provenance: entry.provenance,
            }}
          />
        ))}
      </ol>
    </details>
  );
}

function Question({ text, at }: { text: string; at?: string }) {
  return (
    <div>
      <p className="eyebrow">You asked{at ? ` · ${dateTime(at)}` : ""}</p>
      <p className="mt-1 text-[0.9375rem] font-medium whitespace-pre-wrap">{text}</p>
    </div>
  );
}

function Thread({
  messages,
  conversationId,
  farmId,
}: {
  messages: ChatMessage[];
  conversationId: string;
  farmId: string | null;
}) {
  return (
    <>
      {messages.map((message) =>
        message.role === "user" ? (
          <Question key={message.id} text={message.content} at={message.created_at} />
        ) : (
          <div key={message.id} className="border-b border-border pb-6">
            {message.advice ? (
              <AdviceCard
                advice={message.advice}
                historical={isOld(message.created_at)}
                footer={
                  <SaveRecommendationButton
                    input={{
                      advice: message.advice,
                      origin: "assistant",
                      conversation_id: conversationId,
                      farm_id: farmId,
                    }}
                  />
                }
              />
            ) : (
              <p className="text-[0.9375rem] whitespace-pre-wrap">{message.content}</p>
            )}
            <CheckedTools log={message.tool_log ?? []} historical={isOld(message.created_at)} />
          </div>
        ),
      )}
    </>
  );
}

function ConversationList({ activeId }: { activeId?: string }) {
  const navigate = useNavigate();
  const client = useQueryClient();
  const conversations = useQuery({ queryKey: keys.conversations, queryFn: api.conversations });
  const remove = useMutation({
    mutationFn: (id: string) => api.deleteConversation(id),
    onSuccess: (_, id) => {
      client.invalidateQueries({ queryKey: keys.conversations });
      if (id === activeId) navigate("/assistant");
      toast.success("Conversation deleted");
    },
    onError: (error) => toast.error(error instanceof ApiError ? error.message : "It could not be deleted."),
  });

  if (conversations.isPending) return <LoadingState label="Loading conversations" />;
  if (conversations.isError) {
    return <ErrorState compact error={conversations.error} onRetry={() => conversations.refetch()} />;
  }
  if (conversations.data.length === 0) {
    return <p className="text-sm text-muted-foreground">Your conversations will be kept here.</p>;
  }
  return (
    <ul className="grid grid-cols-[minmax(0,1fr)] gap-0.5">
      {conversations.data.map((item) => (
        <li key={item.id} className="group flex items-center gap-1">
          <Link
            to={`/assistant/${item.id}`}
            aria-current={item.id === activeId ? "page" : undefined}
            className={cn(
              "min-w-0 flex-1 rounded px-2 py-2 text-sm hover:bg-muted",
              item.id === activeId && "bg-sage font-medium",
            )}
          >
            <span className="block truncate">{item.title}</span>
            <span className="font-mono text-[0.6875rem] text-muted-foreground">{dateTime(item.updated_at)}</span>
          </Link>
          <ConfirmDialog
            title="Delete this conversation?"
            description="The messages will be removed. Recommendations you saved stay in Farming History."
            confirmLabel="Delete conversation"
            onConfirm={() => remove.mutate(item.id)}
            trigger={
              <Button variant="ghost" size="icon-sm" aria-label={`Delete conversation: ${item.title}`}>
                <Trash2 aria-hidden="true" />
              </Button>
            }
          />
        </li>
      ))}
    </ul>
  );
}

export function AssistantPage() {
  const { conversationId } = useParams();
  const navigate = useNavigate();
  const client = useQueryClient();
  const health = useHealth();
  const { farm, crop } = useFarmContext();
  const [draft, setDraft] = useState("");
  const [turn, setTurn] = useState<Turn | null>(null);
  const abort = useRef<AbortController | null>(null);
  const end = useRef<HTMLDivElement>(null);

  const detail = useQuery({
    queryKey: keys.conversation(conversationId),
    queryFn: () => api.conversation(conversationId as string),
    enabled: Boolean(conversationId),
  });

  const unconfigured = health.data ? !health.data.ai_configured : false;
  const running = turn?.running ?? false;
  const messageCount = detail.data?.messages.length ?? 0;

  useEffect(() => {
    end.current?.scrollIntoView?.({ block: "nearest" });
  }, [messageCount, running, turn?.steps.length]);

  // Leaving the page or the conversation cancels a run in progress.
  useEffect(() => {
    return () => abort.current?.abort();
  }, []);

  function applyEvent(event: AgentEvent) {
    setTurn((current) => {
      if (!current) return current;
      if (event.type === "tool_start") {
        return {
          ...current,
          steps: [...current.steps, { id: event.id, name: event.name, state: "running" }],
        };
      }
      if (event.type === "tool_end") {
        return {
          ...current,
          steps: current.steps.map((step) =>
            step.id === event.id
              ? {
                  ...step,
                  state: event.ok ? "ok" : "failed",
                  durationMs: event.duration_ms,
                  provenance: event.provenance,
                }
              : step,
          ),
        };
      }
      return current;
    });
  }

  async function send(raw: string) {
    const message = raw.trim();
    if (!message || running) return;
    const controller = new AbortController();
    abort.current = controller;
    setDraft("");
    setTurn({ question: message, steps: [], error: null, running: true });
    try {
      const response = await streamChat(
        { message, conversation_id: conversationId ?? null, farm_id: farm?.id ?? null },
        applyEvent,
        controller.signal,
      );
      // Load the stored exchange before dropping the temporary one, so nothing flickers away.
      await client.fetchQuery({
        queryKey: keys.conversation(response.conversation_id),
        queryFn: () => api.conversation(response.conversation_id),
      });
      client.invalidateQueries({ queryKey: keys.conversations });
      if (response.saved_recommendation_ids.length > 0) {
        client.invalidateQueries({ queryKey: keys.recommendations });
      }
      setTurn(null);
      if (response.conversation_id !== conversationId) {
        navigate(`/assistant/${response.conversation_id}`, { replace: true });
      }
    } catch (error) {
      setDraft(message);
      if (error instanceof DOMException && error.name === "AbortError") {
        setTurn(null);
        return;
      }
      setTurn((current) => (current ? { ...current, running: false, error } : current));
    }
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      send(draft);
    }
  }

  const stageText = crop?.growth_stage_label ? `, ${crop.growth_stage_label.toLowerCase()}` : "";

  return (
    <div className="space-y-5">
      <PageHeader
        title="AI Farming Assistant"
        description="Ask about your fields in your own words. It checks real weather and FarmAgent's crop rules before it answers, and shows you what it checked."
        actions={
          <Button variant="outline" onClick={() => navigate("/assistant")} disabled={!conversationId && !turn}>
            <MessageSquarePlus aria-hidden="true" /> New conversation
          </Button>
        }
      />

      <div className="grid items-start gap-5 lg:grid-cols-[16rem_minmax(0,1fr)]">
        <details className="panel p-3 lg:hidden">
          <summary className="cursor-pointer text-sm font-medium">Past conversations</summary>
          <div className="mt-2">
            <ConversationList activeId={conversationId} />
          </div>
        </details>
        <aside className="panel sticky top-6 hidden max-h-[calc(100dvh-3rem)] overflow-y-auto p-3 lg:block" aria-label="Past conversations">
          <h2 className="eyebrow px-2 pb-2">Past conversations</h2>
          <ConversationList activeId={conversationId} />
        </aside>

        <section className="flex min-h-[60dvh] min-w-0 flex-col" aria-label="Conversation">
          <div className="flex-1 space-y-6 pb-4">
            {unconfigured && <ErrorState error={new ApiError("agent_not_configured", "")} />}

            {conversationId && detail.isPending && <LoadingState label="Loading this conversation" />}
            {conversationId && detail.isError && (
              <ErrorState
                error={detail.error}
                title={detail.error instanceof ApiError && detail.error.status === 404 ? "That conversation no longer exists" : undefined}
                onRetry={() => detail.refetch()}
              />
            )}
            {detail.data && conversationId && (
              <Thread messages={detail.data.messages} conversationId={conversationId} farmId={detail.data.farm_id} />
            )}

            {!conversationId && !turn && !unconfigured && (
              <EmptyState title="Start with a question">
                <ul className="mt-2 grid gap-1.5" aria-label="Suggested questions">
                  {SUGGESTED_QUESTIONS.map((question) => (
                    <li key={question}>
                      <button
                        type="button"
                        className="rounded border border-border bg-card px-3 py-2 text-left text-sm text-foreground hover:border-shoot hover:bg-sage/60"
                        onClick={() => send(question)}
                      >
                        {question}
                      </button>
                    </li>
                  ))}
                </ul>
              </EmptyState>
            )}

            {turn && (
              <div className="space-y-3" data-testid="current-turn">
                <Question text={turn.question} />
                {(turn.running || turn.steps.length > 0) && (
                  <ol className="grid gap-1.5 rounded border border-border bg-muted/40 p-3" aria-live="polite" aria-label="Assistant progress">
                    {turn.running && turn.steps.length === 0 && (
                      <li className="flex items-center gap-2 text-sm text-muted-foreground">
                        <LoaderCircle className="size-4 animate-spin" aria-hidden="true" /> Working out what to check…
                      </li>
                    )}
                    {turn.steps.map((step) => (
                      <StepRow key={step.id} step={step} />
                    ))}
                    {turn.running && turn.steps.length > 0 && turn.steps.every((step) => step.state !== "running") && (
                      <li className="flex items-center gap-2 text-sm text-muted-foreground">
                        <LoaderCircle className="size-4 animate-spin" aria-hidden="true" /> Writing the answer…
                      </li>
                    )}
                  </ol>
                )}
                {Boolean(turn.error) && (
                  <ErrorState error={turn.error} onRetry={() => send(turn.question)} title={turn.error instanceof ApiError && turn.error.code === "agent_not_configured" ? undefined : "The assistant could not finish"} />
                )}
              </div>
            )}
            <div ref={end} />
          </div>

          <form
            className="sticky bottom-0 -mx-1 bg-background px-1 pt-2 pb-3"
            onSubmit={(event) => {
              event.preventDefault();
              send(draft);
            }}
          >
            <p className="mb-1.5 text-xs text-muted-foreground">
              {farm ? (
                <>
                  Using {farm.name ?? farm.location_name ?? "your farm"}
                  {crop ? `, ${crop.crop_name.toLowerCase()}${stageText}` : ""}.{" "}
                  <Link to="/farm" className="text-shoot-ink underline underline-offset-2">
                    Update it in My Farm
                  </Link>{" "}
                  if anything has changed.
                </>
              ) : (
                <>
                  No farm is set up, so the assistant will ask where you are.{" "}
                  <Link to="/welcome" className="text-shoot-ink underline underline-offset-2">
                    Set up your farm
                  </Link>
                </>
              )}
            </p>
            <div className="flex items-end gap-2">
              <Textarea
                aria-label="Your question"
                placeholder={unconfigured ? "The assistant is not connected" : "Ask about irrigation, weather or crop risk"}
                value={draft}
                maxLength={MAX_MESSAGE}
                disabled={unconfigured}
                rows={2}
                className="max-h-48"
                onChange={(event) => setDraft(event.target.value)}
                onKeyDown={onKeyDown}
              />
              {running ? (
                <Button type="button" variant="outline" size="lg" className="shrink-0" onClick={() => abort.current?.abort()}>
                  <Square aria-hidden="true" /> Stop
                </Button>
              ) : (
                <Button type="submit" size="lg" className="shrink-0" disabled={unconfigured || !draft.trim()}>
                  <SendHorizontal aria-hidden="true" /> Send
                </Button>
              )}
            </div>
            {draft.length > MAX_MESSAGE - 300 && (
              <p className="mt-1 text-xs text-muted-foreground">
                {MAX_MESSAGE - draft.length} characters left
              </p>
            )}
          </form>
        </section>
      </div>
    </div>
  );
}
