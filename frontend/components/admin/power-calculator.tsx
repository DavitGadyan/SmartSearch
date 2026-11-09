"use client";

import { useState } from "react";
import { useAdmin } from "@/lib/admin";
import { fmt } from "@/lib/format";
import { Input, Label, Rows } from "@/components/ui";
import { Bars } from "./charts";

type Power = { required_n_per_arm: number; total_users: number; duration_days: number; mde_curve: { n_per_arm: number; mde_rel: number }[] };

/** Sample size, duration and the detectable-lift curve for a conversion-rate test (two-sided z-test). */
export function PowerCalculator() {
  const [p, setP] = useState({ baseline_rate: 0.03, mde_rel: 0.05, alpha: 0.05, power: 0.8, daily_users: 1500 });
  const { data } = useAdmin<Power>("/experiments/tools/power", p);
  const field = (k: keyof typeof p, label: string, step: string) => (
    <div className="grid gap-1">
      <Label htmlFor={k}>{label}</Label>
      <Input id={k} type="number" step={step} value={p[k]} onChange={(e) => setP({ ...p, [k]: Number(e.target.value) })} className="tnum h-9" />
    </div>
  );
  return (
    <div className="grid gap-6 lg:grid-cols-[320px_1fr]">
      <div className="grid grid-cols-2 gap-3">
        {field("baseline_rate", "Baseline rate", "0.001")}
        {field("mde_rel", "Relative MDE", "0.01")}
        {field("alpha", "Alpha", "0.01")}
        {field("power", "Power", "0.05")}
        {field("daily_users", "Eligible users / day", "100")}
        {data && (
          <div className="col-span-2 mt-2">
            <Rows
              dense
              items={[
                ["Users per arm", fmt.num(data.required_n_per_arm)],
                ["Total users", fmt.num(data.total_users)],
                ["Duration", `${data.duration_days} days`],
              ]}
            />
          </div>
        )}
      </div>
      <div>
        {data && <Bars data={data.mde_curve.map((r) => ({ n: fmt.compact(r.n_per_arm), mde: r.mde_rel }))} x="n" series={[{ key: "mde", name: "Detectable relative lift" }]} height={220} format={(v) => fmt.pct(v)} yFormat={(v) => fmt.pct(v, 0)} />}
        <p className="mt-1 text-xs text-muted">Smallest detectable relative lift by users per arm.</p>
      </div>
    </div>
  );
}
