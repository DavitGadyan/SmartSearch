"use client";

import { Select } from "@/components/ui";

export function WindowSelect({ value, onChange }: { value: number; onChange: (d: number) => void }) {
  return (
    <Select className="h-9 text-xs" value={value} onChange={(e) => onChange(Number(e.target.value))} aria-label="Date window">
      <option value={7}>Last 7 days</option>
      <option value={14}>Last 14 days</option>
      <option value={28}>Last 28 days</option>
    </Select>
  );
}
