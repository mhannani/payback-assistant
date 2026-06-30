"use client";

/** Products toolbar — Helfio's two-cluster layout: [search] [filters] on the left. */
import { ProductsMoreFiltersPopover } from "./toolbar/more-filters-popover";
import { ProductsSearchInput } from "./toolbar/search-input";
import type { useProductsFilters } from "./use-products-filters";

type FiltersState = ReturnType<typeof useProductsFilters>;

export function ProductsToolbar(f: FiltersState) {
  return (
    <div className="flex items-center gap-2">
      <ProductsSearchInput value={f.searchInput} onValueChange={f.setSearchInput} fetching={f.fetching} />
      <ProductsMoreFiltersPopover
        partner={f.partner}
        setPartner={f.setPartner}
        tag={f.tag}
        setTag={f.setTag}
        sort={f.sort}
        setSort={f.setSort}
        hasActiveFilters={f.hasActiveFilters}
        clearFilters={f.clearFilters}
        activeFilterCount={f.activeFilterCount}
      />
    </div>
  );
}
