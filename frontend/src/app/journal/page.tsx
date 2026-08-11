import TradeJournalView from "@/components/TradeJournalView";

// Server Component: only unwraps optional prefill query params
// (`?ticker=...&insight_id=...`, set by the "Добавить в дневник" link
// from `InsightHistorySection.tsx`) and hands them to the client
// component that owns fetching/loading/error state — mirrors
// `InstrumentDetailsPage` (ADR-0003, §17, §21.1). No insight *content*
// ever passes through this URL — only the ticker string and a numeric
// id, which the backend re-validates on submit (task scope §14).
export default async function JournalPage({
  searchParams,
}: {
  searchParams: Promise<{ [key: string]: string | string[] | undefined }>;
}) {
  const resolved = await searchParams;
  const rawTicker = resolved.ticker;
  const rawInsightId = resolved.insight_id;

  const prefillTicker = typeof rawTicker === "string" ? rawTicker : undefined;
  const parsedInsightId =
    typeof rawInsightId === "string" && rawInsightId.trim() !== "" ? Number(rawInsightId) : NaN;
  const prefillInsightId = Number.isInteger(parsedInsightId) ? parsedInsightId : undefined;

  return <TradeJournalView prefillTicker={prefillTicker} prefillInsightId={prefillInsightId} />;
}
