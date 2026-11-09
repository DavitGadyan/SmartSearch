import { Hero } from "@/components/shop/hero";
import { HomeStats } from "@/components/shop/home-stats";
import { Rail } from "@/components/shop/rail";

export default function HomePage() {
  return (
    <>
      <Hero />
      <HomeStats />
      <Rail title="Picked for you" endpoint="/recommendations/for-you" rail="for_you" needsUser hideOnFallback eager />
      <Rail title="Trending" endpoint="/recommendations/trending" rail="trending" eager />
      <Rail title="New arrivals" endpoint="/recommendations/new-arrivals" rail="new_arrivals" />
    </>
  );
}
