import { ExperimentBuilder } from "@/components/admin/experiment-builder";
import { PageHeader } from "@/components/ui";

export default function NewExperimentPage() {
  return (
    <>
      <PageHeader title="New experiment" description="Change the storefront, deploy it to half of the shoppers, read the verdict." />
      <ExperimentBuilder />
    </>
  );
}
