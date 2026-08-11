import Link from "next/link";
import WatchlistPanel from "@/components/WatchlistPanel";

// Server Component: only assembles the page (ADR-0003, §17, §21.1).
// It does not fetch or own any business data itself — all watchlist
// interaction lives in the client component below, which talks to the
// FastAPI backend directly via the typed API client.
//
// The "Дневник" link is a minimal entry point into `/journal`
// (task scope §12: no full market-navigation shell here — FR-003 is a
// separate future slice — just enough for the user to reach the
// section FR-030 requires).
export default function HomePage() {
  return (
    <main>
      <header className="home-header">
        <h1>AI Trading Assistant Platform</h1>
        <Link href="/journal" className="home-journal-link">
          Дневник сделок
        </Link>
      </header>
      <WatchlistPanel />
    </main>
  );
}
