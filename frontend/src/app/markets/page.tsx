import WatchlistPanel from "@/components/WatchlistPanel";

/**
 * Markets (Phase 1, task scope §6). Server Component — the only
 * interactivity on this page lives inside `WatchlistPanel` (reused
 * unchanged, same as `INFORMATION_ARCHITECTURE.md` §2.2 requires for
 * the Акции section). Forex/Crypto/Commodities are honest,
 * non-interactive unavailable states: no fake search forms, no
 * fabricated prices, no placeholder dashboards
 * (`INFORMATION_ARCHITECTURE.md` §2.2's "не кликабельная пустая
 * страница, не имитация функциональности" rule, and
 * `TECHNOLOGY_EVALUATION.md` §14 / `ADR-0011`, which is still a Draft
 * awaiting real provider research).
 */

interface BlockedMarket {
  key: string;
  name: string;
  description: string;
}

const BLOCKED_MARKETS: BlockedMarket[] = [
  {
    key: "forex",
    name: "Forex",
    description: "В планах. Живые данные по валютному рынку пока не подключены.",
  },
  {
    key: "crypto",
    name: "Криптовалюта",
    description: "В планах. Живые данные по криптовалютному рынку пока не подключены.",
  },
  {
    key: "commodities",
    name: "Сырьё",
    description: "В планах. Живые данные по рынку сырья пока не подключены.",
  },
];

export default function MarketsPage() {
  return (
    <main className="markets">
      <header className="markets-header">
        <h1>Рынки</h1>
        <p className="markets-subtitle">
          Акции доступны сегодня. Forex, криптовалюта и сырьё — в планах: живые данные для них
          пока не подключены.
        </p>
      </header>

      <section className="market-section" aria-labelledby="market-stocks-heading">
        <div className="market-section-heading-row">
          <h2 id="market-stocks-heading">Акции</h2>
          <span className="market-section-status market-section-status-available">
            Доступно
          </span>
        </div>
        <WatchlistPanel />
      </section>

      {BLOCKED_MARKETS.map((market) => (
        <section
          key={market.key}
          className="market-section market-section-blocked"
          aria-labelledby={`market-${market.key}-heading`}
        >
          <div className="market-section-heading-row">
            <h2 id={`market-${market.key}-heading`}>{market.name}</h2>
            <span className="market-section-status market-section-status-blocked">
              Запланировано
            </span>
          </div>
          <p className="market-section-blocked-description">{market.description}</p>
        </section>
      ))}
    </main>
  );
}
