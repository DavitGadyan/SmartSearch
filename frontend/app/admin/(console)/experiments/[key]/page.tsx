import { ExperimentDetail } from "@/components/admin/experiment-detail";

export default async function Page({ params }: { params: Promise<{ key: string }> }) {
  const { key } = await params;
  return <ExperimentDetail experimentKey={key} />;
}
