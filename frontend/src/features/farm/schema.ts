import { z } from "zod";
import type { Farm, FarmCrop, FarmCropInput, FarmInput } from "@/types/api";

const text = z.string().max(160, "Keep this under 160 characters.");

export const farmSchema = z
  .object({
    name: text,
    location_name: text,
    state: text,
    country: text,
    latitude: z.number().nullable(),
    longitude: z.number().nullable(),
    size_value: z
      .string()
      .refine(
        (value) => value.trim() === "" || (Number.isFinite(Number(value)) && Number(value) > 0),
        "Enter a number above zero, or leave this empty.",
      ),
    area_unit: z.string(),
    soil_type: z.string(),
  });

export type FarmValues = z.infer<typeof farmSchema>;

export const emptyFarm: FarmValues = {
  name: "",
  location_name: "",
  state: "",
  country: "",
  latitude: null,
  longitude: null,
  size_value: "",
  area_unit: "",
  soil_type: "",
};

export function farmToValues(farm: Farm): FarmValues {
  return {
    name: farm.name ?? "",
    location_name: farm.location_name ?? "",
    state: farm.state ?? "",
    country: farm.country ?? "",
    latitude: farm.latitude,
    longitude: farm.longitude,
    size_value: farm.size_value !== null ? String(farm.size_value) : "",
    area_unit: farm.area_unit ?? "",
    soil_type: farm.soil_type ?? "",
  };
}

const orNull = (value: string) => (value.trim() === "" ? null : value.trim());

/** Anything left empty stays null. Nothing is filled in on the farmer's behalf. */
export function toFarmInput(values: FarmValues): FarmInput {
  return {
    name: orNull(values.name),
    location_name: orNull(values.location_name),
    state: orNull(values.state),
    country: orNull(values.country),
    latitude: values.latitude,
    longitude: values.longitude,
    size_value: values.size_value.trim() === "" ? null : Number(values.size_value),
    area_unit: orNull(values.area_unit),
    soil_type: orNull(values.soil_type),
  };
}

export const cropSchema = z.object({
  crop: z.string(),
  variety: text,
  sowing_date: z.string(),
  growth_stage: z.string(),
  irrigation_method: z.string(),
});

export const requiredCropSchema = cropSchema.extend({
  crop: z.string().min(1, "Choose a crop."),
});

export type CropValues = z.infer<typeof cropSchema>;

export const emptyCrop: CropValues = {
  crop: "",
  variety: "",
  sowing_date: "",
  growth_stage: "",
  irrigation_method: "",
};

export function cropToValues(crop: FarmCrop): CropValues {
  return {
    crop: crop.crop,
    variety: crop.variety ?? "",
    sowing_date: crop.sowing_date ?? "",
    growth_stage: crop.growth_stage ?? "",
    irrigation_method: crop.irrigation_method ?? "",
  };
}

export function toCropInput(values: CropValues): FarmCropInput {
  return {
    crop: values.crop,
    variety: orNull(values.variety),
    sowing_date: orNull(values.sowing_date),
    growth_stage: orNull(values.growth_stage),
    irrigation_method: orNull(values.irrigation_method),
  };
}
