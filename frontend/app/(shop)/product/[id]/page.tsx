import { ProductPage } from "@/components/shop/product-page";

export default async function Page({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <ProductPage id={Number(id)} />;
}
