import InsightsHistoryPanel from "@/components/InsightsHistoryPanel";

// Server Component: only unwraps the optional `?open=` query param
// (set by the "Инсайт #{id}" link from `TradeJournalView.tsx`, task
// scope §9) and hands it to the client component that owns fetching —
// mirrors `InstrumentDetailsPage`/`JournalPage` (ADR-0003, §17, §21.1).
export default async function InsightsPage({
  searchParams,
}: {
  searchParams: Promise<{ [key: string]: string | string[] | undefined }>;
}) {
  const resolved = await searchParams;
  const rawOpen = resolved.open;
  const parsedOpenId = typeof rawOpen === "string" && rawOpen.trim() !== "" ? Number(rawOpen) : NaN;
  const openInsightId = Number.isInteger(parsedOpenId) ? parsedOpenId : undefined;

  return <InsightsHistoryPanel openInsightId={openInsightId} />;
}
