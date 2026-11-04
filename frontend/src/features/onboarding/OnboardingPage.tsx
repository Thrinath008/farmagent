import { useEffect, useState } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { ArrowLeft, ArrowRight, Check } from "lucide-react";
import { Controller, FormProvider, useForm, type FieldPath } from "react-hook-form";
import { Link, useNavigate } from "react-router";
import { z } from "zod";
import { Field, SelectField } from "@/components/forms/Field";
import { Logo } from "@/components/layout/Logo";
import { ErrorState } from "@/components/states/States";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { CropFields, FarmDetailFields, PlaceFields } from "@/features/farm/fields";
import { cropSchema, emptyCrop, emptyFarm, farmSchema, toCropInput, toFarmInput } from "@/features/farm/schema";
import { keys, useCatalog, useSession } from "@/hooks/queries";
import { LANGUAGES, ONBOARDING_SKIPPED } from "@/lib/labels";
import { cn } from "@/lib/utils";
import { useFarmContext } from "@/providers/FarmProvider";
import { api } from "@/services/api";

const schema = z.object({
  display_name: z.string().max(160, "Keep this under 160 characters."),
  preferred_language: z.string().min(1),
  ...farmSchema.shape,
  ...cropSchema.shape,
});

type Values = z.infer<typeof schema>;

const STEPS: { title: string; intro: string; fields: FieldPath<Values>[] }[] = [
  {
    title: "You",
    intro: "This is how FarmAgent will greet you, and the language the assistant will reply in.",
    fields: ["display_name", "preferred_language"],
  },
  {
    title: "Location",
    intro: "Weather is looked up by location. Without one, FarmAgent will not give weather-based advice.",
    fields: ["location_name", "state", "country"],
  },
  {
    title: "Farm",
    intro: "All optional. FarmAgent marks anything you leave out as unknown, and never fills it in for you.",
    fields: ["name", "size_value", "area_unit", "soil_type"],
  },
  {
    title: "Crop",
    intro: "Rules are implemented for wheat so far. Other crops can be recorded, but get general guidance only.",
    fields: ["crop", "variety", "sowing_date", "growth_stage", "irrigation_method"],
  },
];

function hasFarmDetails(values: Values): boolean {
  return Boolean(
    values.latitude !== null ||
      values.name.trim() ||
      values.location_name.trim() ||
      values.state.trim() ||
      values.country.trim() ||
      values.size_value.trim() ||
      values.area_unit ||
      values.soil_type ||
      values.crop,
  );
}

export function OnboardingPage() {
  const client = useQueryClient();
  const navigate = useNavigate();
  const session = useSession();
  const catalog = useCatalog();
  const { selectFarm } = useFarmContext();
  const [step, setStep] = useState(0);
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: {
      display_name: "",
      preferred_language: "English",
      ...emptyFarm,
      ...emptyCrop,
    },
  });

  const user = session.data;
  useEffect(() => {
    if (user && !form.formState.isDirty) {
      form.setValue("display_name", user.display_name ?? "");
      form.setValue("preferred_language", user.preferred_language || "English");
    }
  }, [user, form]);

  const finish = useMutation({
    mutationFn: async (values: Values) => {
      const updated = await api.updateMe({
        display_name: values.display_name.trim() || null,
        preferred_language: values.preferred_language,
      });
      client.setQueryData(keys.session, updated);
      if (!hasFarmDetails(values)) {
        localStorage.setItem(ONBOARDING_SKIPPED, "1");
        return null;
      }
      return api.createFarm({
        ...toFarmInput(values),
        crops: values.crop ? [toCropInput(values)] : [],
      });
    },
    onSuccess: async (farm) => {
      if (farm) {
        selectFarm(farm.id);
        await client.invalidateQueries({ queryKey: keys.farms });
      }
      navigate("/", { replace: true });
    },
  });

  function skip() {
    localStorage.setItem(ONBOARDING_SKIPPED, "1");
    navigate("/", { replace: true });
  }

  async function next() {
    const valid = await form.trigger(STEPS[step].fields);
    if (!valid) return;
    if (step === STEPS.length - 1) {
      form.handleSubmit((values) => finish.mutate(values))();
    } else {
      setStep(step + 1);
    }
  }

  const errors = form.formState.errors;
  const last = step === STEPS.length - 1;

  return (
    <div className="grid min-h-dvh lg:grid-cols-[minmax(20rem,26rem)_minmax(0,1fr)]">
      <aside className="flex flex-col gap-6 bg-sidebar p-6 text-sidebar-foreground sm:p-8 lg:min-h-dvh lg:p-10">
        <p className="flex items-center gap-2 text-white">
          <Logo className="size-6" />
          <span className="display text-lg">FarmAgent</span>
        </p>
        <div className="lg:mt-10">
          <h1 className="display text-3xl text-white sm:text-4xl">Set up your fields</h1>
          <p className="mt-3 max-w-prose text-[0.9375rem] text-sidebar-foreground/85">
            Advice for your own crop, built on real weather for your own location. Everything here can
            be changed later.
          </p>
        </div>
        <ol className="hidden gap-2 lg:mt-6 lg:grid" aria-label="Setup steps">
          {STEPS.map((item, index) => (
            <li
              key={item.title}
              aria-current={index === step ? "step" : undefined}
              className={cn(
                "flex items-center gap-3 text-sm",
                index === step ? "font-medium text-white" : "text-sidebar-foreground/70",
              )}
            >
              <span
                className={cn(
                  "flex size-6 items-center justify-center rounded-[2px] border font-mono text-xs",
                  index < step
                    ? "border-sidebar-primary bg-sidebar-primary text-forest"
                    : index === step
                      ? "border-white"
                      : "border-sidebar-border",
                )}
              >
                {index < step ? <Check className="size-3.5" aria-hidden="true" /> : index + 1}
              </span>
              {item.title}
            </li>
          ))}
        </ol>
        <p className="text-xs text-sidebar-foreground/70 lg:mt-auto">
          Want to see how it works first?{" "}
          <Link to="/scenario-lab" className="text-white underline underline-offset-2">
            Open the Scenario Lab
          </Link>
          , which uses made-up weather and needs no setup.
        </p>
      </aside>

      <main className="flex items-start justify-center p-5 sm:p-8 lg:items-center lg:p-12">
        <div className="w-full max-w-xl">
          <FormProvider {...form}>
            <form
              noValidate
              onSubmit={(event) => {
                event.preventDefault();
                next();
              }}
            >
              <p className="eyebrow">
                Step {step + 1} of {STEPS.length}
              </p>
              <motion.div
                key={step}
                initial={{ opacity: 0, x: 8 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ duration: 0.16 }}
              >
                <h2 className="display mt-2 text-2xl">{STEPS[step].title}</h2>
                <p className="mt-1.5 text-[0.9375rem] text-muted-foreground">{STEPS[step].intro}</p>

                <div className="mt-6">
                  {step === 0 && (
                    <div className="grid gap-4">
                      <Field id="onboarding-name" label="Your name" optional error={errors.display_name?.message}>
                        <Input id="onboarding-name" autoComplete="name" {...form.register("display_name")} />
                      </Field>
                      <Field
                        id="onboarding-language"
                        label="Preferred language"
                        hint="The assistant replies in this language. The rest of FarmAgent is in English for now."
                      >
                        <Controller
                          control={form.control}
                          name="preferred_language"
                          render={({ field }) => (
                            <SelectField
                              id="onboarding-language"
                              value={field.value}
                              onChange={field.onChange}
                              options={LANGUAGES.map((value) => ({ value, label: value }))}
                            />
                          )}
                        />
                      </Field>
                    </div>
                  )}
                  {step === 1 && <PlaceFields idPrefix="onboarding" />}
                  {step === 2 && <FarmDetailFields catalog={catalog.data} idPrefix="onboarding" />}
                  {step === 3 && <CropFields catalog={catalog.data} idPrefix="onboarding-crop" cropOptional />}
                </div>
              </motion.div>

              {catalog.isError && step >= 2 && (
                <ErrorState className="mt-4" compact error={catalog.error} onRetry={() => catalog.refetch()} />
              )}
              {finish.isError && (
                <ErrorState className="mt-4" compact error={finish.error} onRetry={() => next()} />
              )}

              <div className="mt-8 flex flex-wrap items-center justify-between gap-3 border-t border-border pt-5">
                <div className="flex gap-2">
                  {step > 0 && (
                    <Button type="button" variant="outline" onClick={() => setStep(step - 1)}>
                      <ArrowLeft aria-hidden="true" /> Back
                    </Button>
                  )}
                  <Button type="button" variant="ghost" onClick={skip}>
                    Skip setup
                  </Button>
                </div>
                <Button type="submit" size="lg" disabled={finish.isPending}>
                  {finish.isPending ? "Saving…" : last ? "Finish setup" : "Continue"}
                  {!finish.isPending && (last ? <Check aria-hidden="true" /> : <ArrowRight aria-hidden="true" />)}
                </Button>
              </div>
            </form>
          </FormProvider>
        </div>
      </main>
    </div>
  );
}
