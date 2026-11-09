"use client";

import { useQuery } from "@tanstack/react-query";
import { UserSwitch } from "@phosphor-icons/react";
import { api, type DemoUser } from "@/lib/api";
import { useSession } from "@/lib/session";
import { fmt } from "@/lib/format";
import { Select } from "@/components/ui";

/** "Shop as" another shopper so personalization is visible: same query, different ranking per persona. */
export function PersonaSwitcher() {
  const { userId, persona, shopAs, ready } = useSession();
  const { data } = useQuery({ queryKey: ["demo-users"], queryFn: () => api.get<DemoUser[]>("/users/demo"), staleTime: 300_000 });
  const users = data ?? [];
  const current = users.find((u) => u.id === userId);
  return (
    <label className="flex items-center gap-1.5 text-xs text-fg-2" title="Shop as another shopper">
      <UserSwitch size={20} className={current ? "text-accent" : "text-fg-2"} aria-hidden />
      <span className="sr-only">Shop as</span>
      <Select
        aria-label="Shop as persona"
        className="h-8 max-w-[118px] text-xs sm:max-w-[190px]"
        value={current ? current.id : "me"}
        disabled={!ready}
        onChange={(e) => {
          const u = users.find((x) => x.id === e.target.value);
          shopAs(u ? u.id : null, u ? u.persona : null);
        }}
      >
        <option value="me">New visitor (me)</option>
        {users.map((u) => (
          <option key={u.id} value={u.id}>
            {fmt.title(u.persona)} · {u.interactions} interactions
          </option>
        ))}
      </Select>
      {persona && <span className="sr-only">Shopping as {persona}</span>}
    </label>
  );
}
