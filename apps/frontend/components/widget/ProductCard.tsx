"use client";

import { useState } from "react";
import { ArrowUpRightIcon, CaretDownIcon, StorefrontIcon } from "@phosphor-icons/react";
import { cn } from "@/lib/utils";
import type { ProductOut } from "@/lib/types";

/** How many results the list shows before the "show more" toggle reveals the rest. */
const PRODUCTS_PREVIEW_COUNT = 3;

/** Format integer cents as a localized price (German locale — the catalog is EUR). */
function formatPrice(cents: number, currency: string): string {
  return new Intl.NumberFormat("de-DE", { style: "currency", currency }).format(cents / 100);
}

/** One product result — image, name, brand, partner, price, tags. Rendered as a ROW inside the
 * single ProductList container (a bottom divider separates rows; the last row's is removed there),
 * so a result set reads as one entity rather than a stack of separate cards. */
export function ProductCard({ product }: { product: ProductOut }) {
  return (
    <div className="flex gap-3 border-b border-border p-3 transition-colors last:border-0 hover:bg-muted/40">
      <div className="flex h-16 w-16 shrink-0 items-center justify-center overflow-hidden rounded-lg bg-muted">
        {product.image_url ? (
          // eslint-disable-next-line @next/next/no-img-element -- external partner CDN, not optimized
          <img src={product.image_url} alt="" className="h-full w-full object-contain" />
        ) : (
          <StorefrontIcon className="h-6 w-6 text-muted-foreground" />
        )}
      </div>

      <div className="min-w-0 flex-1">
        <div className="flex items-start justify-between gap-2">
          <p className="line-clamp-2 text-sm font-medium leading-snug text-foreground">{product.name}</p>
          <span className="shrink-0 text-sm font-semibold text-primary">
            {formatPrice(product.price_cents, product.currency)}
          </span>
        </div>

        <div className="mt-1 flex items-center gap-1.5 text-xs text-muted-foreground">
          {product.brand && <span className="truncate">{product.brand}</span>}
          {product.brand && <span aria-hidden>·</span>}
          <span className="rounded bg-muted px-1.5 py-0.5 font-medium">{product.partner_name}</span>
        </div>

        {product.tags.length > 0 && (
          <div className="mt-1.5 flex flex-wrap gap-1">
            {product.tags.slice(0, 3).map((tag) => (
              <span
                key={tag}
                className={cn(
                  "rounded-full border border-primary/20 bg-accent px-2 py-0.5",
                  "text-[10px] font-medium text-primary",
                )}
              >
                {tag}
              </span>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

/** The result set as ONE entity: a single bordered container with products as divided rows. Shows
 * the first few and, when there are more, a "Mehr anzeigen" toggle that reveals the rest in place
 * (kept inline so the embedded widget needs no host page or extra navigation). */
export function ProductList({ items }: { items: ProductOut[] }) {
  const [expanded, setExpanded] = useState(false);
  const hasMore = items.length > PRODUCTS_PREVIEW_COUNT;
  const shown = expanded ? items : items.slice(0, PRODUCTS_PREVIEW_COUNT);

  return (
    <div className="overflow-hidden rounded-xl border border-border bg-card">
      {shown.map((p) => (
        <ProductCard key={p.id} product={p} />
      ))}

      {hasMore && (
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          className={cn(
            "flex w-full items-center justify-center gap-1 border-t border-border bg-muted/30 py-2",
            "text-xs font-medium text-primary transition-colors hover:bg-muted/60",
          )}
        >
          {expanded ? "Weniger anzeigen" : `${items.length - PRODUCTS_PREVIEW_COUNT} weitere anzeigen`}
          <CaretDownIcon
            className={cn("h-3.5 w-3.5 transition-transform", expanded && "rotate-180")}
            weight="bold"
          />
        </button>
      )}
    </div>
  );
}

/** A navigational hand-off card: a short message + a deep-link button into the partner's own search. */
export function RouteCard({
  message,
  deeplink,
  partnerName,
}: {
  message: string;
  deeplink: string;
  partnerName: string;
}) {
  return (
    <div className="rounded-xl border border-border bg-card p-3">
      <p className="text-sm leading-snug text-foreground">{message}</p>
      <a
        href={deeplink}
        target="_blank"
        rel="noopener noreferrer"
        className={cn(
          "mt-2 inline-flex items-center gap-1.5 rounded-lg bg-primary px-3 py-1.5",
          "text-sm font-medium text-primary-foreground transition-colors hover:bg-primary-hover",
        )}
      >
        Bei {partnerName} suchen
        <ArrowUpRightIcon className="h-4 w-4" weight="bold" />
      </a>
    </div>
  );
}
