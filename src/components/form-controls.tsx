"use client";
import type { Ref } from "react";
export function NativeSelectField({
  label,
  value,
  onChange,
  options,
  disabled = false,
  invalid = false,
  describedBy,
  inputRef,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: { value: string; label: string }[];
  disabled?: boolean;
  invalid?: boolean;
  describedBy?: string;
  inputRef?: Ref<HTMLSelectElement>;
}) {
  return (
    <label className="auth-field">
      <span>{label}</span>
      <select
        ref={inputRef}
        aria-invalid={invalid}
        aria-describedby={describedBy}
        aria-label={label}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        disabled={disabled}
      >
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </label>
  );
}
export function NativeDateField({
  kind = "date",
  label,
  value,
  onChange,
  disabled = false,
  invalid = false,
  describedBy,
  inputRef,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
  invalid?: boolean;
  describedBy?: string;
  inputRef?: Ref<HTMLInputElement>;
  kind?: "date" | "time";
}) {
  return (
    <label className="auth-field">
      <span>{label}</span>
      <input
        ref={inputRef}
        type={kind}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        disabled={disabled}
        aria-invalid={invalid}
        aria-describedby={describedBy}
      />
    </label>
  );
}
