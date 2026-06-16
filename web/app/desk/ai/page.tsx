import type { Metadata } from "next";
import { getLatestBrief } from "@/lib/api/briefs";
import { BriefReader } from "@/components/brief/brief-reader";
import { EmptyState } from "@/components/common/empty-state";

export const metadata: Metadata = {
  title: "AI Infrastructure Desk",
  robots: { index: false, follow: false },
};

export default async function AIDeskPage() {
  const { data: brief } = await getLatestBrief("ai");

  if (!brief) {
    return (
      <div className="mx-auto max-w-content px-4 py-16 sm:px-6">
        <EmptyState
          title="Today's brief is being prepared."
          hint="Check back at 5:30am ET for the latest AI Infrastructure desk briefing."
        />
      </div>
    );
  }

  return <BriefReader brief={brief} />;
}
