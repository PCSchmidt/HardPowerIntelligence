import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { getBrief } from "@/lib/api/briefs";
import { BriefReader } from "@/components/brief/brief-reader";
import { ArchiveLock } from "@/components/subscription/archive-lock";

export const metadata: Metadata = {
  title: "Brief Archive",
  robots: { index: false, follow: false },
};

export default async function BriefDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const { data: brief, status } = await getBrief(id);

  if (status === 403) {
    return (
      <ArchiveLock
        title="Access the 90-day archive with Pro"
        body="This brief is older than today. Pro unlocks the rolling 90-day archive plus entity 360, PDF export, and follows."
      />
    );
  }

  if (!brief) {
    notFound();
  }

  return <BriefReader brief={brief} />;
}
