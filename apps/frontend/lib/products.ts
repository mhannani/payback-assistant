/** Types + fetch for the products catalog table (GET /products). Mirrors the backend ProductPage. */

import type { PartnerSlug } from "@/lib/types";

export interface ProductRow {
  id: string;
  partner: PartnerSlug;
  partner_name: string;
  name: string;
  brand: string | null;
  description: string | null;
  price_cents: number;
  currency: string;
  image_url: string | null;
  tags: string[];
  weight_g: number | null;
  volume_ml: number | null;
}

export interface ProductPage {
  items: ProductRow[];
  total: number;
  page: number;
  page_size: number;
}

export type ProductSort = "name" | "price_low" | "price_high";

export interface ProductQuery {
  search?: string;
  partner?: PartnerSlug | "";
  tag?: string;
  sort?: ProductSort;
  page: number;
  pageSize: number;
}

const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "";

/** Build the /products query string from the filter state and fetch one page. */
export async function fetchProducts(q: ProductQuery): Promise<ProductPage> {
  const params = new URLSearchParams();
  if (q.search) params.set("search", q.search);
  if (q.partner) params.set("partner", q.partner);
  if (q.tag) params.append("tags", q.tag);
  if (q.sort) params.set("sort", q.sort);
  params.set("page", String(q.page));
  params.set("page_size", String(q.pageSize));

  const res = await fetch(`${API_BASE}/products?${params.toString()}`);
  if (!res.ok) throw new Error(`products ${res.status}`);
  return res.json();
}

/** The dietary tags the filter offers (the curated set the catalog uses). */
export const TAG_OPTIONS = [
  "organic",
  "vegan",
  "vegetarian",
  "no-gluten",
  "no-lactose",
  "fair-trade",
] as const;

export const PARTNER_OPTIONS: { value: PartnerSlug; label: string }[] = [
  { value: "dm", label: "dm" },
  { value: "edeka", label: "EDEKA" },
  { value: "amazon", label: "Amazon" },
];
