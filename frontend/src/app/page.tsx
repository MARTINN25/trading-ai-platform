import OverviewView from "@/components/OverviewView";

// Server Component: only assembles the page (ADR-0003, §17, §21.1).
// It does not fetch or own any business data itself — `OverviewView`
// (Client Component) owns all data fetching and interaction, talking
// to the FastAPI backend directly via the typed API clients.
//
// Phase 1 (Application Shell & Intelligence Workspace, task scope §5):
// `/` is now a real Overview — watchlist, recent insights, recent
// journal activity, entry to Markets — replacing the previous bare
// watchlist-only landing page.
export default function HomePage() {
  return <OverviewView />;
}
