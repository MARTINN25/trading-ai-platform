import WatchlistPanel from "@/components/WatchlistPanel";

// Server Component: only assembles the page (ADR-0003, §17, §21.1).
// It does not fetch or own any business data itself — all watchlist
// interaction lives in the client component below, which talks to the
// FastAPI backend directly via the typed API client.
export default function HomePage() {
  return (
    <main>
      <h1>AI Trading Assistant Platform</h1>
      <WatchlistPanel />
    </main>
  );
}
