import { Suspense } from "react";
import { SearchResults } from "@/components/shop/search-results";
import { Skeleton } from "@/components/ui";

export const metadata = { title: "Search" };

export default function SearchPage() {
  return (
    <Suspense fallback={<Skeleton className="h-96" />}>
      <SearchResults />
    </Suspense>
  );
}
