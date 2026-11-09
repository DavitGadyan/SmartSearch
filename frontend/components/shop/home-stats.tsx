"use client";

import { Stat } from "@/components/ui";
import { fmt } from "@/lib/format";

/** Three catalog facts under the hero; the numbers count up as they appear. */
export function HomeStats() {
  return (
    <div className="stagger mx-auto mt-14 grid max-w-3xl grid-cols-3 gap-3">
      <Stat label="products" value={42994} format={fmt.num} />
      <Stat label="human relevance judgments" value={233000} format={fmt.compact} />
      <Stat label="experiments" value={4} />
    </div>
  );
}
