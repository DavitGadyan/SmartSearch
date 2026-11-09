"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import { LockKey } from "@phosphor-icons/react";
import { Button, Card, Input, Label } from "@/components/ui";

function LoginForm() {
  const router = useRouter();
  const next = useSearchParams().get("next") ?? "/admin";
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const res = await fetch("/api/admin/login", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ password }) });
    setBusy(false);
    if (!res.ok) {
      setError(res.status === 401 ? "That keyword is not right." : "Login is not available right now.");
      return;
    }
    router.replace(next.startsWith("/admin") ? next : "/admin");
    router.refresh();
  };

  return (
    <Card className="w-full max-w-sm p-7">
      <span className="grid size-10 place-items-center rounded-control bg-accent-soft text-fg">
        <LockKey size={20} weight="bold" />
      </span>
      <h1 className="mt-4 font-serif text-2xl tracking-tight">Merchant console</h1>
      <p className="mt-1 text-sm text-fg-2">Enter the access keyword to continue.</p>
      <form onSubmit={submit} className="mt-6 grid gap-2">
        <Label htmlFor="keyword">Keyword</Label>
        <Input id="keyword" type="password" autoFocus autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} />
        {error && <p className="text-xs text-critical">{error}</p>}
        <Button type="submit" className="mt-2 w-full" disabled={busy || !password}>
          {busy ? "Checking…" : "Enter console"}
        </Button>
      </form>
    </Card>
  );
}

export default function AdminLoginPage() {
  return (
    <div className="flex min-h-dvh items-center justify-center p-6">
      <Suspense fallback={null}>
        <LoginForm />
      </Suspense>
    </div>
  );
}
