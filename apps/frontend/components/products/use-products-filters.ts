"use client";

/** Products table state — Helfio's URL-synced filter hook, adapted for SERVER-side pagination.
 *
 * Filters/search/sort + the page number live in the URL (shareable, back-button-friendly). Search is
 * debounced (400 ms) like Helfio. Unlike Helfio's client-side slice, the backend paginates: each
 * change refetches GET /products with page/page_size and returns {items, total, page} — so the table
 * never holds the whole catalog. */

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  fetchProducts,
  type ProductRow,
  type ProductSort,
} from "@/lib/products";
import type { PartnerSlug } from "@/lib/types";

export const PAGE_SIZE = 24;

const VALID_PARTNERS = new Set(["dm", "edeka", "amazon"]);
const VALID_SORTS = new Set(["name", "price_low", "price_high"]);

export function useProductsFilters() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();

  // ── Initial state from the URL ──
  const urlPartner = searchParams.get("partner");
  const urlTag = searchParams.get("tag");
  const urlSort = searchParams.get("sort");
  const urlSearch = searchParams.get("q");
  const urlPage = searchParams.get("page");

  const [partner, setPartnerState] = useState<string>(
    urlPartner && VALID_PARTNERS.has(urlPartner) ? urlPartner : "all",
  );
  const [tag, setTagState] = useState<string>(urlTag || "all");
  const [sort, setSortState] = useState<ProductSort>(
    urlSort && VALID_SORTS.has(urlSort) ? (urlSort as ProductSort) : "name",
  );
  const [searchInput, setSearchInput] = useState<string>(urlSearch || "");
  const [debouncedSearch, setDebouncedSearch] = useState<string>(urlSearch || "");
  const [page, setPageState] = useState<number>(urlPage ? Math.max(1, Number(urlPage)) : 1);

  // ── URL sync ──
  const updateUrl = useCallback(
    (params: Record<string, string | null>) => {
      const current = new URLSearchParams(searchParams.toString());
      for (const [key, value] of Object.entries(params)) {
        if (value === null || value === "all" || value === "" || (key === "page" && value === "1")) {
          current.delete(key);
        } else {
          current.set(key, value);
        }
      }
      const query = current.toString();
      router.replace(`${pathname}${query ? `?${query}` : ""}`, { scroll: false });
    },
    [searchParams, router, pathname],
  );

  // Debounce search → reset to page 1.
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearch(searchInput);
      setPageState(1);
      updateUrl({ q: searchInput || null, page: null });
    }, 400);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchInput]);

  // Filter setters reset to page 1 + sync URL.
  const setPartner = useCallback((v: string) => {
    setPartnerState(v);
    setPageState(1);
    updateUrl({ partner: v, page: null });
  }, [updateUrl]);
  const setTag = useCallback((v: string) => {
    setTagState(v);
    setPageState(1);
    updateUrl({ tag: v, page: null });
  }, [updateUrl]);
  const setSort = useCallback((v: ProductSort) => {
    setSortState(v);
    setPageState(1);
    updateUrl({ sort: v, page: null });
  }, [updateUrl]);
  const setPage = useCallback((p: number) => {
    setPageState(p);
    updateUrl({ page: String(p) });
  }, [updateUrl]);

  // ── Fetch the current page (server-side filter/sort/paginate) ──
  const [items, setItems] = useState<ProductRow[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [fetching, setFetching] = useState(false);
  const reqRef = useRef(0);

  useEffect(() => {
    const reqId = ++reqRef.current;
    setFetching(true);
    fetchProducts({
      search: debouncedSearch || undefined,
      partner: partner === "all" ? "" : (partner as PartnerSlug),
      tag: tag === "all" ? "" : tag,
      sort,
      page,
      pageSize: PAGE_SIZE,
    })
      .then((res) => {
        if (reqId !== reqRef.current) return; // a newer request superseded this one
        setItems(res.items);
        setTotal(res.total);
      })
      .catch(() => {
        if (reqId !== reqRef.current) return;
        setItems([]);
        setTotal(0);
      })
      .finally(() => {
        if (reqId !== reqRef.current) return;
        setLoading(false);
        setFetching(false);
      });
  }, [debouncedSearch, partner, tag, sort, page]);

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const hasActiveFilters = partner !== "all" || tag !== "all" || sort !== "name" || debouncedSearch !== "";
  const activeFilterCount = useMemo(
    () => [partner !== "all", tag !== "all", sort !== "name"].filter(Boolean).length,
    [partner, tag, sort],
  );

  const clearFilters = useCallback(() => {
    setPartnerState("all");
    setTagState("all");
    setSortState("name");
    setSearchInput("");
    setDebouncedSearch("");
    setPageState(1);
    updateUrl({ partner: null, tag: null, sort: null, q: null, page: null });
  }, [updateUrl]);

  return {
    // filter state
    partner, setPartner, tag, setTag, sort, setSort,
    searchInput, setSearchInput, fetching,
    hasActiveFilters, activeFilterCount, clearFilters,
    // data + pagination
    items, total, loading, page, setPage, totalPages,
  };
}
