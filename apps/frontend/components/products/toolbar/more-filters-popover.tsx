"use client";

/** Product filters popover — Helfio's more-filters-popover shape: a single Funnel trigger (fill +
 * count badge) over Select dropdowns (partner, tag, sort), apply-on-change, clear at the bottom. */
import { FunnelIcon as Funnel } from "@phosphor-icons/react";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { PARTNER_OPTIONS, type ProductSort, TAG_OPTIONS } from "@/lib/products";

const SORT_LABELS: Record<ProductSort, string> = {
  name: "Name (A–Z)",
  price_low: "Preis (aufsteigend)",
  price_high: "Preis (absteigend)",
};

const TAG_LABELS: Record<string, string> = {
  organic: "Bio",
  vegan: "Vegan",
  vegetarian: "Vegetarisch",
  "no-gluten": "Glutenfrei",
  "no-lactose": "Laktosefrei",
  "fair-trade": "Fair Trade",
};

interface ProductsMoreFiltersPopoverProps {
  partner: string;
  setPartner: (value: string) => void;
  tag: string;
  setTag: (value: string) => void;
  sort: ProductSort;
  setSort: (value: ProductSort) => void;
  hasActiveFilters: boolean;
  clearFilters: () => void;
  activeFilterCount: number;
}

export function ProductsMoreFiltersPopover({
  partner,
  setPartner,
  tag,
  setTag,
  sort,
  setSort,
  hasActiveFilters,
  clearFilters,
  activeFilterCount,
}: ProductsMoreFiltersPopoverProps) {
  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button variant="outline" size="sm" className="h-8 shrink-0 gap-1.5 px-2.5 text-xs">
          <Funnel className="h-3.5 w-3.5" weight={hasActiveFilters ? "fill" : "regular"} />
          <span>Filter</span>
          {activeFilterCount > 0 && (
            <span className="rounded-full bg-primary/10 px-1.5 py-0.5 text-[10px] font-semibold tabular-nums text-primary">
              {activeFilterCount}
            </span>
          )}
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-80 space-y-3 p-3">
        {/* Partner */}
        <div className="space-y-1.5">
          <label className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
            Partner
          </label>
          <Select value={partner} onValueChange={setPartner}>
            <SelectTrigger className="h-8 text-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Alle Partner</SelectItem>
              {PARTNER_OPTIONS.map((p) => (
                <SelectItem key={p.value} value={p.value}>
                  {p.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        {/* Tag */}
        <div className="space-y-1.5">
          <label className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
            Eigenschaft
          </label>
          <Select value={tag} onValueChange={setTag}>
            <SelectTrigger className="h-8 text-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Alle Eigenschaften</SelectItem>
              {TAG_OPTIONS.map((tg) => (
                <SelectItem key={tg} value={tg}>
                  {TAG_LABELS[tg] ?? tg}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        {/* Sort */}
        <div className="space-y-1.5">
          <label className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
            Sortierung
          </label>
          <Select value={sort} onValueChange={(v) => setSort(v as ProductSort)}>
            <SelectTrigger className="h-8 text-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {(Object.keys(SORT_LABELS) as ProductSort[]).map((s) => (
                <SelectItem key={s} value={s}>
                  {SORT_LABELS[s]}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <Button
          variant="default"
          size="sm"
          className="h-8 w-full text-xs"
          onClick={clearFilters}
          disabled={!hasActiveFilters}
        >
          Filter zurücksetzen
        </Button>
      </PopoverContent>
    </Popover>
  );
}
