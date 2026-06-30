"use client";

/** Product table columns — adapts Helfio's useClientColumns: a flex identity column (image + name),
 * then brand, partner, price, tags, size. CSS-grid sizing via `meta.flex` / `size` (column-sizing.ts). */
import type { ColumnDef } from "@tanstack/react-table";
import { useMemo } from "react";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { DataTableColumnHeader } from "@/components/data-table";
import type { ProductRow } from "@/lib/products";
import { PartnerLogo } from "@/components/partners/partner-logos";

const TAG_LABELS: Record<string, string> = {
  organic: "Bio",
  vegan: "Vegan",
  vegetarian: "Vegetarisch",
  "no-gluten": "Glutenfrei",
  "no-lactose": "Laktosefrei",
  "fair-trade": "Fair Trade",
};

function formatPrice(cents: number, currency: string): string {
  return new Intl.NumberFormat("de-DE", { style: "currency", currency }).format(cents / 100);
}

function formatSize(p: ProductRow): string {
  if (p.weight_g != null) return p.weight_g >= 1000 ? `${(p.weight_g / 1000).toFixed(p.weight_g % 1000 ? 1 : 0)} kg` : `${p.weight_g} g`;
  if (p.volume_ml != null) return p.volume_ml >= 1000 ? `${(p.volume_ml / 1000).toFixed(p.volume_ml % 1000 ? 1 : 0)} l` : `${p.volume_ml} ml`;
  return "—";
}

export function useProductColumns(): {
  columns: ColumnDef<ProductRow>[];
  columnLabels: Record<string, string>;
} {
  const columns = useMemo<ColumnDef<ProductRow>[]>(
    () => [
      // ── Identity: image + name (the flex column) ──
      {
        id: "name",
        size: 280,
        meta: { flex: true },
        accessorFn: (p) => p.name,
        header: ({ column }) => <DataTableColumnHeader column={column} title="Produkt" />,
        cell: ({ row }) => {
          const p = row.original;
          return (
            <div className="flex items-center gap-2.5">
              <Avatar className="h-9 w-9 shrink-0 rounded-md">
                <AvatarImage src={p.image_url ?? undefined} alt="" className="object-contain" />
                <AvatarFallback className="rounded-md bg-primary/10 text-[10px] font-semibold text-primary">
                  {p.name.slice(0, 2).toUpperCase()}
                </AvatarFallback>
              </Avatar>
              {/* Name only — keep it on one truncating line so the long catalog description never
                  forces the grid wider than the viewport (the cause of the horizontal scroll). */}
              <p className="min-w-0 truncate font-medium leading-tight">{p.name}</p>
            </div>
          );
        },
        enableHiding: false,
      },
      // ── Brand ──
      {
        id: "brand",
        accessorKey: "brand",
        size: 112,
        header: ({ column }) => <DataTableColumnHeader column={column} title="Marke" />,
        cell: ({ row }) =>
          row.original.brand ? (
            <span className="text-sm">{row.original.brand}</span>
          ) : (
            <span className="text-sm text-muted-foreground">—</span>
          ),
      },
      // ── Partner ──
      {
        id: "partner",
        accessorKey: "partner_name",
        size: 120,
        header: ({ column }) => <DataTableColumnHeader column={column} title="Partner" />,
        cell: ({ row }) => (
          <PartnerLogo partner={row.original.partner} name={row.original.partner_name} />
        ),
      },
      // ── Price ──
      {
        id: "price",
        accessorKey: "price_cents",
        size: 96,
        header: ({ column }) => <DataTableColumnHeader column={column} title="Preis" />,
        cell: ({ row }) => (
          <span className="text-sm font-semibold tabular-nums text-primary">
            {formatPrice(row.original.price_cents, row.original.currency)}
          </span>
        ),
      },
      // ── Size ──
      {
        id: "size",
        size: 84,
        accessorFn: (p) => p.weight_g ?? p.volume_ml ?? -1,
        header: ({ column }) => <DataTableColumnHeader column={column} title="Größe" />,
        cell: ({ row }) => (
          <span className="text-sm tabular-nums text-muted-foreground">{formatSize(row.original)}</span>
        ),
      },
      // ── Tags ──
      {
        id: "tags",
        size: 150,
        accessorFn: (p) => p.tags.join(" "),
        enableSorting: false,
        header: ({ column }) => <DataTableColumnHeader column={column} title="Eigenschaften" />,
        cell: ({ row }) =>
          row.original.tags.length ? (
            <div className="flex flex-wrap gap-1">
              {row.original.tags.slice(0, 3).map((t) => (
                <span
                  key={t}
                  className="rounded-full border border-primary/20 bg-accent px-2 py-0.5 text-[10px] font-medium text-primary"
                >
                  {TAG_LABELS[t] ?? t}
                </span>
              ))}
            </div>
          ) : (
            <span className="text-sm text-muted-foreground">—</span>
          ),
      },
    ],
    [],
  );

  const columnLabels = useMemo<Record<string, string>>(
    () => ({ name: "Produkt", brand: "Marke", partner: "Partner", price: "Preis", size: "Größe", tags: "Eigenschaften" }),
    [],
  );

  return { columns, columnLabels };
}
