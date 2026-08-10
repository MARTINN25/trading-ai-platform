import InstrumentDetailsView from "@/components/InstrumentDetailsView";

// Server Component: only unwraps the dynamic segment (params is a
// Promise in this Next.js version) and hands the ticker to the client
// component that owns fetching/loading/error state — mirrors how
// HomePage assembles WatchlistPanel (ADR-0003, §17, §21.1).
export default async function InstrumentDetailsPage({
  params,
}: {
  params: Promise<{ ticker: string }>;
}) {
  const { ticker } = await params;
  return <InstrumentDetailsView ticker={ticker} />;
}
