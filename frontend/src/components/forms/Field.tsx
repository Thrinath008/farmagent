import type { ReactNode } from "react";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { cn } from "@/lib/utils";

interface FieldProps {
  id: string;
  label: string;
  hint?: ReactNode;
  error?: string;
  optional?: boolean;
  className?: string;
  children: ReactNode;
}

export function Field({ id, label, hint, error, optional, className, children }: FieldProps) {
  return (
    <div className={cn("grid content-start gap-1.5", className)}>
      <Label htmlFor={id} className="text-sm font-medium">
        {label}
        {optional && <span className="ml-1 font-normal text-muted-foreground">(optional)</span>}
      </Label>
      {children}
      {hint && !error && <p className="text-xs text-muted-foreground">{hint}</p>}
      {error && (
        <p id={`${id}-error`} role="alert" className="text-xs font-medium text-clay-ink">
          {error}
        </p>
      )}
    </div>
  );
}

export interface Option {
  value: string;
  label: string;
}

// Radix Select reserves the empty string, so "nothing chosen" travels as this sentinel inside it.
const NOTHING = "__none__";

export function SelectField({
  id,
  value,
  onChange,
  options,
  placeholder = "Choose",
  clearLabel,
  disabled,
  invalid,
  className,
}: {
  id: string;
  value: string;
  onChange: (value: string) => void;
  options: Option[];
  placeholder?: string;
  /** Offers a way back to "not specified" for optional fields. */
  clearLabel?: string;
  disabled?: boolean;
  invalid?: boolean;
  className?: string;
}) {
  return (
    <Select
      value={value === "" && clearLabel ? NOTHING : value}
      onValueChange={(next) => onChange(next === NOTHING ? "" : next)}
      disabled={disabled}
    >
      <SelectTrigger id={id} aria-invalid={invalid || undefined} className={cn("w-full", className)}>
        <SelectValue placeholder={placeholder} />
      </SelectTrigger>
      <SelectContent>
        {clearLabel && <SelectItem value={NOTHING}>{clearLabel}</SelectItem>}
        {options.map((option) => (
          <SelectItem key={option.value} value={option.value}>
            {option.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
