import { ShopHeader } from "@/components/shop/header";
import { UiBanner } from "@/components/shop/hero";

export default function ShopLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-dvh">
      <ShopHeader />
      <UiBanner />
      <main className="mx-auto max-w-[1400px] px-4 pb-24 pt-6 lg:px-6">{children}</main>
    </div>
  );
}
