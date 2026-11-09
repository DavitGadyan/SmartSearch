"use client";

import Link from "next/link";
import type { Experiment } from "@/lib/api";
import { useAdmin } from "@/lib/admin";
import { ExperimentCard } from "@/components/admin/experiment-card";
import { PowerCalculator } from "@/components/admin/power-calculator";
import { Disclosure, ErrorBox, PageHeader, Skeleton } from "@/components/ui";

export default function ExperimentsPage() {
  const { data, isLoading, error } = useAdmin<Experiment[]>("/experiments");
  if (error) return <ErrorBox error={error} />;
  // chronological; the layered A/A check sits after the test it accompanies
  const sorted = [...(data ?? [])].sort((a, b) => (a.start_at ?? "").localeCompare(b.start_at ?? "") || Number(a.key.startsWith("aa_")) - Number(b.key.startsWith("aa_")));
  return (
    <>
      <PageHeader
        title="Experiments"
        description="Half of the shoppers see a change. We measure what they buy."
        action={
          <Link href="/admin/experiments/new" className="inline-flex h-9 items-center rounded-control bg-accent px-4 text-sm font-medium text-accent-fg hover:bg-fg-2">
            New experiment
          </Link>
        }
      />
      {isLoading ? (
        <div className="stagger grid gap-4">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} className="h-56" />
          ))}
        </div>
      ) : (
        <div className="stagger grid gap-4">
          {sorted.map((e) => (
            <ExperimentCard key={e.key} experiment={e} />
          ))}
        </div>
      )}
      <Disclosure summary="Plan a new test" className="mt-10">
        <PowerCalculator />
      </Disclosure>
    </>
  );
}
