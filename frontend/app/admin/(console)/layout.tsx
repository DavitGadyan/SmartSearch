import { AdminNav, AdminTopBar } from "@/components/admin/nav";

export const metadata = { title: "Console" };

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-dvh lg:grid lg:grid-cols-[240px_1fr]">
      <aside className="glass-strong hidden border-y-0 border-l-0 lg:block">
        <div className="sticky top-0 h-dvh">
          <AdminNav />
        </div>
      </aside>
      <div className="min-w-0">
        <AdminTopBar />
        <main className="mx-auto max-w-[1200px] px-4 py-8 lg:px-10 lg:py-10">{children}</main>
      </div>
    </div>
  );
}
