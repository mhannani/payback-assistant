"use client";

/**
 * DataTableFooter — server-side pagination pinned to the bottom of the
 * DataTable's bordered box. Keeps the exact visual design the per-page
 * paginators used (a rounded-border prev / ``page / total`` / next
 * cluster, right-aligned), restyled as a ``border-t`` footer row so it
 * reads as part of the table and reclaims the vertical space a separate
 * sibling block used to take.
 *
 * Driven by server-side ``{ page, totalPages, onPageChange }`` — NOT by
 * TanStack's internal pagination — because the dashboard list pages
 * page on the backend. Hidden when there is a single page.
 */
import {
  CaretLeftIcon as CaretLeft,
  CaretRightIcon as CaretRight,
} from "@phosphor-icons/react";

import { Button } from "@/components/ui/button";

export interface DataTableFooterProps {
  page: number;
  totalPages: number;
  onPageChange: (page: number) => void;
}

export function DataTableFooter({ page, totalPages, onPageChange }: DataTableFooterProps) {
  if (totalPages <= 1) return null;

  return (
    <div className="flex shrink-0 items-center justify-end border-t border-border/50 px-2 py-1.5">
      <div className="flex items-center rounded-md border">
        <Button
          variant="ghost"
          size="icon"
          className="h-8 w-8 rounded-none rounded-l-md"
          onClick={() => onPageChange(Math.max(1, page - 1))}
          disabled={page <= 1}
          aria-label="Vorherige Seite"
        >
          <CaretLeft className="h-4 w-4" />
        </Button>
        <span className="flex h-8 items-center px-3 text-xs text-muted-foreground border-x" aria-live="polite">
          {page} / {totalPages}
        </span>
        <Button
          variant="ghost"
          size="icon"
          className="h-8 w-8 rounded-none rounded-r-md"
          onClick={() => onPageChange(Math.min(totalPages, page + 1))}
          disabled={page >= totalPages}
          aria-label="Nächste Seite"
        >
          <CaretRight className="h-4 w-4" />
        </Button>
      </div>
    </div>
  );
}
