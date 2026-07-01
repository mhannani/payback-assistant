import { cn } from "@/lib/utils";
import type { ProductOut } from "@/lib/types";
import { PartnerLogo } from "@/components/partners/partner-logos";

/** Format integer cents as a localized EUR price (the catalog is German/EUR). */
function formatPrice(cents: number): string {
  return new Intl.NumberFormat("de-DE", { style: "currency", currency: "EUR" }).format(cents / 100);
}

/** The comparative unit price, e.g. "1,50 €/100 g" — or "—" when the product has no parseable size. */
function formatUnitPrice(cents: number | null, basis: ProductOut["unit_basis"]): string {
  if (cents == null || basis == null) return "—";
  const unit = basis === "per_100g" ? "100 g" : "100 ml";
  return `${formatPrice(cents)}/${unit}`;
}

// One shared grid template for the header and every row, so columns line up. Produkt = 1fr (fills the
// width); price / unit / logo = auto (content-width, pinned right). CSS grid, not <table> — the same
// choice the project's shared DataTable makes, because grid gives predictable column control that
// table-auto does not (which is why the earlier <table> left a gap and wouldn't right-align the logo).
const GRID = "grid grid-cols-[1fr_auto_auto_auto] items-center gap-x-3";

/** A value comparison: products ranked by price-per-unit (cheapest value first), as a compact grid
 * (name · pack price · unit price · shop logo) with the best-value row highlighted. Distinct from the
 * product list because the *unit* price — not the sticker — is what makes a comparison meaningful. */
export function CompareCard({ items, cheapestId }: { items: ProductOut[]; cheapestId: string | null }) {
  if (items.length === 0) {
    return (
      <div className="rounded-xl border border-border bg-card p-3 text-sm text-muted-foreground">
        Nichts zum Vergleichen gefunden.
      </div>
    );
  }

  return (
    <div className="overflow-hidden rounded-xl border border-border bg-card text-xs">
      {/* Header */}
      <div className={cn(GRID, "border-b border-border bg-muted/50 px-3 py-1.5 text-muted-foreground")}>
        <span className="font-medium">Produkt</span>
        <span className="text-right font-medium">Preis</span>
        <span className="text-right font-medium">pro Menge</span>
        <span className="text-right font-medium">Markt</span>
      </div>

      {/* Rows */}
      {items.map((p) => {
        const isCheapest = p.id === cheapestId;
        return (
          <div
            key={p.id}
            className={cn(GRID, "border-b border-border/60 px-3 py-1.5 last:border-0", isCheapest && "bg-accent")}
          >
            {/* Produkt (fills) */}
            <div className="min-w-0">
              <p className="line-clamp-2 font-medium text-foreground">{p.name}</p>
              {isCheapest && (
                <span className="mt-0.5 inline-block rounded-full bg-primary px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wide text-primary-foreground">
                  Günstigster
                </span>
              )}
            </div>

            {/* Pack price */}
            <span className="whitespace-nowrap text-right text-foreground">{formatPrice(p.price_cents)}</span>

            {/* Unit price (the comparison metric) */}
            <span
              className={cn(
                "whitespace-nowrap text-right",
                isCheapest ? "font-semibold text-primary" : "text-muted-foreground",
              )}
            >
              {formatUnitPrice(p.unit_price_cents, p.unit_basis)}
            </span>

            {/* Shop — brand mark at its official colors, pinned right by the grid cell's justify-self */}
            <PartnerLogo partner={p.partner} name={p.partner_name} className="h-3.5 justify-self-end" />
          </div>
        );
      })}
    </div>
  );
}
