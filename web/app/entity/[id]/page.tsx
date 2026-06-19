import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { getEntity } from "@/lib/api/entities";
import { Entity360 } from "@/components/entity/entity-360";

// Entity 360 is a logged-in reader view, not a marketing surface (FRONTEND_SPEC §7).
export const metadata: Metadata = {
  title: "Entity 360",
  robots: { index: false, follow: false },
};

export default async function EntityPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const { data: entity } = await getEntity(id);

  if (!entity) {
    notFound();
  }

  return <Entity360 entity={entity} />;
}
