import type { ComponentType, SVGProps } from "react";
import { cn } from "@/lib/utils";
import type { PartnerSlug } from "@/lib/types";
import { AmazonIcon } from "./icons/amazon";
import { DmIcon } from "./icons/dm";
import { EdekaIcon } from "./icons/edeka";

/* Partner brand marks — mirrors Helfio's FundLogo pattern (insurance funds → brand marks). Each SVG
 * keeps its OWN brand fills (never recolored to currentColor); the container provides contrast.
 * Keyed by partner slug for a direct lookup; an unmapped partner falls back to its name as text. */

export const PARTNER_LOGOS: Partial<Record<PartnerSlug, ComponentType<SVGProps<SVGSVGElement>>>> = {
  dm: DmIcon,
  edeka: EdekaIcon,
  amazon: AmazonIcon,
};

/** The brand mark for a partner, or null when none is registered yet (caller renders text instead). */
export function partnerLogoFor(
  partner: PartnerSlug,
): ComponentType<SVGProps<SVGSVGElement>> | null {
  return PARTNER_LOGOS[partner] ?? null;
}

/** Renders a partner's brand mark (bounded, brand colors preserved), or its name as a fallback. */
export function PartnerLogo({
  partner,
  name,
  className,
}: {
  partner: PartnerSlug;
  name: string;
  className?: string;
}) {
  const Icon = partnerLogoFor(partner);
  if (Icon) {
    return <Icon className={cn("h-4 w-auto max-w-[88px] object-contain", className)} aria-label={name} />;
  }
  return <span className={cn("truncate text-sm", className)}>{name}</span>;
}
