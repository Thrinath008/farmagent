import { useEffect, useState } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { MapPin, Pencil, Plus, Trash2 } from "lucide-react";
import { FormProvider, useForm } from "react-hook-form";
import { toast } from "sonner";
import { ConfirmDialog } from "@/components/forms/ConfirmDialog";
import { SelectField } from "@/components/forms/Field";
import { PageHeader } from "@/components/layout/PageHeader";
import { SeasonStrip } from "@/components/SeasonStrip";
import { EmptyState, ErrorState, LoadingState } from "@/components/states/States";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { keys, useCatalog } from "@/hooks/queries";
import { calendarDate, coordinates, placeName, words } from "@/lib/format";
import { useFarmContext } from "@/providers/FarmProvider";
import { api, ApiError } from "@/services/api";
import type { Farm, FarmCrop } from "@/types/api";
import { CropFields, FarmDetailFields, PlaceFields } from "./fields";
import {
  cropToValues,
  emptyCrop,
  emptyFarm,
  farmSchema,
  farmToValues,
  requiredCropSchema,
  toCropInput,
  toFarmInput,
  type CropValues,
  type FarmValues,
} from "./schema";

function problemMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : "That could not be saved. Try again.";
}

function FarmDialog({
  open,
  onOpenChange,
  farm,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  farm: Farm | null;
}) {
  const client = useQueryClient();
  const catalog = useCatalog();
  const { selectFarm } = useFarmContext();
  const form = useForm<FarmValues>({ resolver: zodResolver(farmSchema), defaultValues: emptyFarm });

  useEffect(() => {
    if (open) form.reset(farm ? farmToValues(farm) : emptyFarm);
  }, [open, farm, form]);

  const save = useMutation({
    mutationFn: (values: FarmValues) =>
      farm ? api.updateFarm(farm.id, toFarmInput(values)) : api.createFarm(toFarmInput(values)),
    onSuccess: (saved) => {
      client.invalidateQueries({ queryKey: keys.farms });
      if (!farm) selectFarm(saved.id);
      toast.success(farm ? "Farm updated" : "Farm added");
      onOpenChange(false);
    },
  });

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90dvh] overflow-y-auto sm:max-w-xl">
        <DialogHeader>
          <DialogTitle className="display text-lg">{farm ? "Edit farm" : "Add a farm"}</DialogTitle>
          <DialogDescription>Only the location is needed for weather. Everything else can wait.</DialogDescription>
        </DialogHeader>
        <FormProvider {...form}>
          <form id="farm-form" className="grid gap-5" onSubmit={form.handleSubmit((values) => save.mutate(values))} noValidate>
            <PlaceFields />
            <FarmDetailFields catalog={catalog.data} />
            {save.isError && <p role="alert" className="text-sm text-clay-ink">{problemMessage(save.error)}</p>}
          </form>
        </FormProvider>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button type="submit" form="farm-form" disabled={save.isPending}>
            {save.isPending ? "Saving…" : farm ? "Save changes" : "Add farm"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function CropDialog({
  open,
  onOpenChange,
  farmId,
  crop,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  farmId: string;
  crop: FarmCrop | null;
}) {
  const client = useQueryClient();
  const catalog = useCatalog();
  const form = useForm<CropValues>({ resolver: zodResolver(requiredCropSchema), defaultValues: emptyCrop });

  useEffect(() => {
    if (open) form.reset(crop ? cropToValues(crop) : emptyCrop);
  }, [open, crop, form]);

  const save = useMutation({
    mutationFn: (values: CropValues) => {
      const input = toCropInput(values);
      if (!crop) return api.addCrop(farmId, input);
      // The crop itself cannot change on an existing record. To grow something else, add a new crop.
      const { crop: _unchanged, ...update } = input;
      void _unchanged;
      return api.updateCrop(farmId, crop.id, update);
    },
    onSuccess: () => {
      client.invalidateQueries({ queryKey: keys.farms });
      toast.success(crop ? "Crop updated" : "Crop added");
      onOpenChange(false);
    },
  });

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90dvh] overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <DialogTitle className="display text-lg">{crop ? `Edit ${crop.crop_name.toLowerCase()}` : "Add a crop"}</DialogTitle>
          <DialogDescription>Only the crop is needed. Add the rest when you know it.</DialogDescription>
        </DialogHeader>
        <FormProvider {...form}>
          <form id="crop-form" onSubmit={form.handleSubmit((values) => save.mutate(values))} noValidate>
            <CropFields catalog={catalog.data} lockCrop={Boolean(crop)} />
            {save.isError && <p role="alert" className="mt-3 text-sm text-clay-ink">{problemMessage(save.error)}</p>}
          </form>
        </FormProvider>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button type="submit" form="crop-form" disabled={save.isPending}>
            {save.isPending ? "Saving…" : crop ? "Save changes" : "Add crop"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function CropRow({ farm, crop, onEdit }: { farm: Farm; crop: FarmCrop; onEdit: () => void }) {
  const client = useQueryClient();
  const catalog = useCatalog();
  const stages = catalog.data?.crops.find((item) => item.id === crop.crop)?.stages ?? [];

  const updateStage = useMutation({
    mutationFn: (growth_stage: string | null) => api.updateCrop(farm.id, crop.id, { growth_stage }),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: keys.farms });
      toast.success("Growth stage updated");
    },
    onError: (error) => toast.error(problemMessage(error)),
  });

  const remove = useMutation({
    mutationFn: () => api.deleteCrop(farm.id, crop.id),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: keys.farms });
      toast.success("Crop removed");
    },
    onError: (error) => toast.error(problemMessage(error)),
  });

  const details = [
    crop.variety,
    crop.sowing_date ? `Sown ${calendarDate(crop.sowing_date, { year: "numeric" })}` : null,
    crop.irrigation_method ? words(crop.irrigation_method) : null,
  ].filter(Boolean);

  return (
    <li className="py-4" data-testid={`crop-${crop.id}`}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="font-medium">{crop.crop_name}</p>
          <p className="mt-0.5 text-sm text-muted-foreground">{details.length > 0 ? details.join(" · ") : "No details yet"}</p>
          {crop.support_level === "planned" && (
            <p className="mt-1 text-xs text-amber-ink">Crop-specific rules are not available yet.</p>
          )}
        </div>
        <div className="flex flex-wrap items-end gap-2">
          {stages.length > 0 && (
            <div className="grid gap-1">
              <label htmlFor={`stage-${crop.id}`} className="text-xs text-muted-foreground">
                Growth stage
              </label>
              <SelectField
                id={`stage-${crop.id}`}
                className="w-52"
                value={crop.growth_stage ?? ""}
                clearLabel="Not sure"
                disabled={updateStage.isPending}
                onChange={(value) => updateStage.mutate(value || null)}
                options={stages.map((stage) => ({ value: stage.id, label: stage.label }))}
              />
            </div>
          )}
          <Button variant="outline" size="icon" aria-label={`Edit ${crop.crop_name}`} onClick={onEdit}>
            <Pencil aria-hidden="true" />
          </Button>
          <ConfirmDialog
            title={`Remove ${crop.crop_name.toLowerCase()} from this farm?`}
            description="Its sowing date and stage will be removed. Saved recommendations stay in Farming History."
            confirmLabel="Remove crop"
            onConfirm={() => remove.mutate()}
            trigger={
              <Button variant="outline" size="icon" aria-label={`Remove ${crop.crop_name}`}>
                <Trash2 aria-hidden="true" />
              </Button>
            }
          />
        </div>
      </div>
      {crop.irrigation_schedule && (
        <SeasonStrip className="mt-4" schedule={crop.irrigation_schedule} cropName={crop.crop_name} />
      )}
    </li>
  );
}

function FarmCard({ farm, onEdit }: { farm: Farm; onEdit: () => void }) {
  const client = useQueryClient();
  const [cropDialog, setCropDialog] = useState<{ open: boolean; crop: FarmCrop | null }>({ open: false, crop: null });
  const remove = useMutation({
    mutationFn: () => api.deleteFarm(farm.id),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: keys.farms });
      toast.success("Farm deleted");
    },
    onError: (error) => toast.error(problemMessage(error)),
  });
  const place = placeName(farm);
  const size = farm.size_value !== null ? `${farm.size_value} ${farm.area_unit ?? ""}`.trim() : null;

  return (
    <article className="panel p-4 sm:p-5" data-testid={`farm-${farm.id}`}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="display text-lg">{farm.name ?? "Unnamed farm"}</h2>
          <p className="mt-1 flex flex-wrap items-center gap-x-2 text-sm text-muted-foreground">
            <MapPin className="size-3.5 text-shoot-ink" aria-hidden="true" />
            {place ?? (farm.latitude === null ? "No location set" : "")}
            {farm.latitude !== null && farm.longitude !== null && (
              <span className="font-mono text-xs">{coordinates(farm.latitude, farm.longitude)}</span>
            )}
          </p>
          <p className="mt-1 text-sm text-muted-foreground">
            {[size, farm.soil_type ? `${words(farm.soil_type)} soil` : null].filter(Boolean).join(" · ") ||
              "Size and soil not set"}
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={onEdit}>
            <Pencil aria-hidden="true" /> Edit farm
          </Button>
          <ConfirmDialog
            title={`Delete ${farm.name ?? "this farm"}?`}
            description="The farm and its crops will be removed. Saved recommendations stay in Farming History."
            confirmLabel="Delete farm"
            onConfirm={() => remove.mutate()}
            trigger={
              <Button variant="outline" size="sm">
                <Trash2 aria-hidden="true" /> Delete
              </Button>
            }
          />
        </div>
      </div>

      <div className="mt-4 border-t border-border">
        {farm.crops.length === 0 ? (
          <p className="py-4 text-sm text-muted-foreground">No crops on this farm yet.</p>
        ) : (
          <ul className="divide-y divide-border">
            {farm.crops.map((crop) => (
              <CropRow key={crop.id} farm={farm} crop={crop} onEdit={() => setCropDialog({ open: true, crop })} />
            ))}
          </ul>
        )}
        <Button variant="secondary" size="sm" onClick={() => setCropDialog({ open: true, crop: null })}>
          <Plus aria-hidden="true" /> Add a crop
        </Button>
      </div>
      <CropDialog
        open={cropDialog.open}
        crop={cropDialog.crop}
        farmId={farm.id}
        onOpenChange={(open) => setCropDialog((state) => ({ ...state, open }))}
      />
    </article>
  );
}

export function FarmPage() {
  const { farms, isLoading, error, refetch } = useFarmContext();
  const [dialog, setDialog] = useState<{ open: boolean; farm: Farm | null }>({ open: false, farm: null });

  return (
    <div className="space-y-5">
      <PageHeader
        title="My Farm"
        description="Keep this current. The assistant and advisors rely on it, and will only ever use what you have entered here."
        actions={
          <Button onClick={() => setDialog({ open: true, farm: null })}>
            <Plus aria-hidden="true" /> Add a farm
          </Button>
        }
      />
      {isLoading && <LoadingState label="Loading your farms" />}
      {Boolean(error) && <ErrorState error={error} onRetry={refetch} />}
      {!isLoading && !error && farms.length === 0 && (
        <EmptyState
          title="No farms yet"
          action={<Button onClick={() => setDialog({ open: true, farm: null })}>Add your first farm</Button>}
        >
          Add a location and a crop to get irrigation and weather risk assessments for your own fields.
        </EmptyState>
      )}
      <div className="grid gap-5">
        {farms.map((farm) => (
          <FarmCard key={farm.id} farm={farm} onEdit={() => setDialog({ open: true, farm })} />
        ))}
      </div>
      <FarmDialog
        open={dialog.open}
        farm={dialog.farm}
        onOpenChange={(open) => setDialog((state) => ({ ...state, open }))}
      />
    </div>
  );
}
