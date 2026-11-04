import { useEffect, useMemo } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, CircleDashed, Trash2, XCircle } from "lucide-react";
import { Controller, useForm } from "react-hook-form";
import { useNavigate } from "react-router";
import { toast } from "sonner";
import { z } from "zod";
import { SourceList } from "@/components/advice/SourceList";
import { ConfirmDialog } from "@/components/forms/ConfirmDialog";
import { Field, SelectField } from "@/components/forms/Field";
import { PageHeader } from "@/components/layout/PageHeader";
import { ErrorState, LoadingState } from "@/components/states/States";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { keys, useCatalog, useHealth, useSession } from "@/hooks/queries";
import { LANGUAGES, ONBOARDING_SKIPPED } from "@/lib/labels";
import { api, ApiError, tokenStore } from "@/services/api";
import type { SourceRef } from "@/types/api";

const schema = z.object({
  display_name: z.string().max(160, "Keep this under 160 characters."),
  preferred_language: z.string().min(1),
});
type Values = z.infer<typeof schema>;

function Profile() {
  const client = useQueryClient();
  const session = useSession();
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: { display_name: "", preferred_language: "English" },
  });
  const user = session.data;
  useEffect(() => {
    if (user) {
      form.reset({
        display_name: user.display_name ?? "",
        preferred_language: user.preferred_language || "English",
      });
    }
  }, [user, form]);

  const save = useMutation({
    mutationFn: (values: Values) =>
      api.updateMe({
        display_name: values.display_name.trim() || null,
        preferred_language: values.preferred_language,
      }),
    onSuccess: (updated) => {
      client.setQueryData(keys.session, updated);
      toast.success("Profile saved");
    },
    onError: (error) => toast.error(error instanceof ApiError ? error.message : "It could not be saved."),
  });

  return (
    <section className="panel p-4 sm:p-5" aria-labelledby="profile-heading">
      <h2 id="profile-heading" className="display text-lg">Profile</h2>
      <form className="mt-3 grid gap-4 sm:max-w-md" onSubmit={form.handleSubmit((values) => save.mutate(values))} noValidate>
        <Field id="settings-name" label="Your name" optional error={form.formState.errors.display_name?.message}>
          <Input id="settings-name" autoComplete="name" {...form.register("display_name")} />
        </Field>
        <Field
          id="settings-language"
          label="Preferred language"
          hint="The assistant replies in this language. The rest of FarmAgent is in English for now."
        >
          <Controller
            control={form.control}
            name="preferred_language"
            render={({ field }) => (
              <SelectField
                id="settings-language"
                value={field.value}
                onChange={field.onChange}
                options={LANGUAGES.map((value) => ({ value, label: value }))}
              />
            )}
          />
        </Field>
        <div>
          <Button type="submit" disabled={save.isPending || !form.formState.isDirty}>
            {save.isPending ? "Saving…" : "Save profile"}
          </Button>
        </div>
      </form>
    </section>
  );
}

function Status({ ok, label, detail }: { ok: boolean | null; label: string; detail: string }) {
  return (
    <li className="flex items-start gap-3 py-3">
      {ok === null ? (
        <CircleDashed className="mt-0.5 size-5 shrink-0 text-muted-foreground" aria-hidden="true" />
      ) : ok ? (
        <CheckCircle2 className="mt-0.5 size-5 shrink-0 text-shoot-ink" aria-hidden="true" />
      ) : (
        <XCircle className="mt-0.5 size-5 shrink-0 text-clay-ink" aria-hidden="true" />
      )}
      <div>
        <p className="font-medium">{label}</p>
        <p className="text-sm text-muted-foreground">{detail}</p>
      </div>
    </li>
  );
}

function Integrations() {
  const health = useHealth();
  return (
    <section className="panel p-4 sm:p-5" aria-labelledby="integrations-heading">
      <h2 id="integrations-heading" className="display text-lg">Connections</h2>
      <p className="mt-1 text-sm text-muted-foreground">
        Whether this server has what each feature needs. Keys are kept on the server and never reach your browser.
      </p>
      {health.isPending && <LoadingState className="mt-3" label="Checking connections" />}
      {health.isError && <ErrorState className="mt-3" compact error={health.error} onRetry={() => health.refetch()} />}
      {health.data && (
        <ul className="mt-2 divide-y divide-border">
          <Status
            ok={health.data.weather_configured}
            label={`Live weather: ${health.data.weather_configured ? "connected" : "not connected"}`}
            detail={
              health.data.weather_configured
                ? "An OpenWeatherMap key is set on the server."
                : "Set OPENWEATHER_API_KEY on the server. Until then, weather-dependent assessments report that no weather is available."
            }
          />
          <Status
            ok={health.data.ai_configured}
            label={`AI assistant: ${health.data.ai_configured ? "connected" : "not connected"}`}
            detail={
              health.data.ai_configured
                ? `Using ${health.data.ai_model}.`
                : "Set ANTHROPIC_API_KEY on the server. The Irrigation Advisor, Crop Health and Scenario Lab work without it."
            }
          />
          <Status
            ok={health.data.database === "ok"}
            label={`Database: ${health.data.database === "ok" ? "connected" : "unavailable"}`}
            detail={
              health.data.database === "ok"
                ? "Your farms and history are being stored."
                : "Farms and history cannot be loaded or saved until the database is back."
            }
          />
        </ul>
      )}
    </section>
  );
}

function Sources() {
  const catalog = useCatalog();
  const sources = useMemo(() => {
    const seen = new Map<string, SourceRef>();
    for (const crop of catalog.data?.crops ?? []) {
      for (const source of crop.sources) seen.set(source.id, source);
    }
    return [...seen.values()];
  }, [catalog.data]);
  const supported = catalog.data?.crops.filter((crop) => crop.support_level === "rules_implemented") ?? [];
  const planned = catalog.data?.crops.filter((crop) => crop.support_level === "planned") ?? [];
  return (
    <section className="panel p-4 sm:p-5" aria-labelledby="sources-heading">
      <h2 id="sources-heading" className="display text-lg">Crop rules and sources</h2>
      {catalog.isPending && <LoadingState className="mt-3" label="Loading crop rules" />}
      {catalog.isError && <ErrorState className="mt-3" compact error={catalog.error} onRetry={() => catalog.refetch()} />}
      {catalog.data && (
        <>
          <p className="mt-1 text-sm">
            <span className="font-medium">Rules implemented: </span>
            {supported.map((crop) => crop.name).join(", ")}.{" "}
            <span className="font-medium">Planned: </span>
            {planned.map((crop) => crop.name).join(", ")}.
          </p>
          <p className="mt-1 text-sm text-muted-foreground">
            The rules are drawn from the published guidance below. They have not been validated in field trials.
          </p>
          <div className="mt-3">
            <SourceList sources={sources} title="Published guidance" />
          </div>
        </>
      )}
    </section>
  );
}

function DangerZone() {
  const client = useQueryClient();
  const navigate = useNavigate();
  const remove = useMutation({
    mutationFn: api.deleteMe,
    onSuccess: () => {
      tokenStore.clear();
      for (const key of [ONBOARDING_SKIPPED, "farmagent.selected_farm", "farmagent.selected_crop"]) {
        localStorage.removeItem(key);
      }
      client.clear();
      navigate("/welcome", { replace: true });
    },
    onError: (error) => toast.error(error instanceof ApiError ? error.message : "Your data could not be deleted."),
  });
  return (
    <section className="panel p-4 sm:p-5" aria-labelledby="data-heading">
      <h2 id="data-heading" className="display text-lg">Your data</h2>
      <p className="mt-1 max-w-prose text-sm text-muted-foreground">
        You are using FarmAgent as a guest, linked to this browser. Clearing this browser's data or using
        another device starts a new, empty guest profile.
      </p>
      <div className="mt-3">
        <ConfirmDialog
          title="Delete all your data?"
          description="Your profile, farms, conversations and saved recommendations will be permanently deleted. This cannot be undone."
          confirmLabel="Delete everything"
          onConfirm={() => remove.mutate()}
          trigger={
            <Button variant="destructive" disabled={remove.isPending}>
              <Trash2 aria-hidden="true" /> Delete all my data
            </Button>
          }
        />
      </div>
    </section>
  );
}

export function SettingsPage() {
  return (
    <div className="space-y-5">
      <PageHeader title="Settings" />
      <Profile />
      <Integrations />
      <Sources />
      <DangerZone />
    </div>
  );
}
