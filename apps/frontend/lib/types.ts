/** Types mirroring the PAYBACK `/assist` API contract (app/schemas.py) plus the widget's own
 * message model. The API returns a discriminated union on `type`; the widget renders a flat list
 * of `Msg`s derived from it. */

// ── The /assist response contract ──────────────────────────────────────────

export type PartnerSlug = "dm" | "edeka" | "amazon";

export interface ProductOut {
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
  // Comparative price normalized to a 100-unit base (the metric "cheapest" really means). null when
  // the product has no parseable size. unit_basis names the base so it's not read as a shelf price.
  unit_price_cents: number | null;
  unit_basis: "per_100g" | "per_100ml" | null;
}

interface AssistBase {
  intent: string;
  action: string;
  language: string;
  usage: { model: string; input_tokens: number; output_tokens: number; cost_usd: number | null } | null;
}

export type AssistResponse =
  | (AssistBase & { type: "products"; items: ProductOut[]; message: string | null })
  | (AssistBase & {
      type: "compare";
      items: ProductOut[];
      cheapest_pick: ProductOut | null;
      message: string | null;
    })
  | (AssistBase & { type: "clarify"; question: string; thread_id: string })
  | (AssistBase & {
      type: "route";
      partner: PartnerSlug;
      partner_name: string;
      search_query: string;
      deeplink: string;
      message: string;
    })
  | (AssistBase & {
      type: "decline";
      message: string;
      partner: PartnerSlug | null;
      partner_name: string | null;
    });

// ── The widget's flat message model (what the conversation UI renders) ──────

export type Msg =
  | { id: string; role: "user"; text: string }
  | { id: string; role: "assistant"; kind: "text"; text: string }
  | { id: string; role: "assistant"; kind: "products"; items: ProductOut[] }
  | {
      id: string;
      role: "assistant";
      kind: "compare";
      items: ProductOut[];
      cheapestId: string | null;
      message: string | null;
    }
  | { id: string; role: "assistant"; kind: "clarify"; question: string }
  | { id: string; role: "assistant"; kind: "route"; message: string; deeplink: string; partnerName: string }
  | { id: string; role: "assistant"; kind: "decline"; message: string };
