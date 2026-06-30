import type { Metadata } from "next";
import { getLatestWire } from "@/lib/api/wire";
import { WireList, DESK_LABEL } from "@/components/brief/wire-list";
import { EmptyState } from "@/components/common/empty-state";

export const metadata: Metadata = {
  title: "Defense Desk — Full Wire",
  robots: { index: false, follow: false },
};

export default async function DefenseWirePage() {
  const { data: wire } = await getLatestWire("defense");

  if (!wire) {
    return (
      <div className="mx-auto max-w-content px-4 py-16 sm:px-6">
        <EmptyState
          title="The wire is being prepared."
          hint="Check back once today's Defense desk brief has published."
        />
      </div>
    );
  }

  return <WireList wire={wire} deskLabel={DESK_LABEL.defense} />;
}
