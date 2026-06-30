import { ArrowUpRightIcon, StorefrontIcon } from "@phosphor-icons/react";
import { cn } from "@/lib/utils";
import type { ProductOut } from "@/lib/types";

/** Format integer cents as a localized price (German locale — the catalog is EUR). */
function formatPrice(cents: number, currency: string): string {
  return new Intl.NumberFormat("de-DE", { style: "currency", currency }).format(cents / 100);
}

/** One product result — image, name, brand, partner, price, tags. The Empfio card look, recolored. */
export function ProductCard({ product }: { product: ProductOut }) {
  return (
    <div className="flex gap-3 rounded-xl border border-border bg-card p-3 transition-shadow hover:shadow-md">
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

/** A list of product cards plus a trailing "find more" affordance is rendered by the bubble. */
export function ProductList({ items }: { items: ProductOut[] }) {
  return (
    <div className="flex flex-col gap-2">
      {items.map((p) => (
        <ProductCard key={p.id} product={p} />
      ))}
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
