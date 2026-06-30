"use client";

/**
 * Sortable column header with visual sort indicator.
 * Use as the `header` in column definitions.
 */

import type { Column } from "@tanstack/react-table";
import {
  ArrowUpIcon as ArrowUp,
  ArrowDownIcon as ArrowDown,
  ArrowsDownUpIcon as ArrowsDownUp,
} from "@phosphor-icons/react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";

interface DataTableColumnHeaderProps<TData, TValue> {
  column: Column<TData, TValue>;
  title: string;
  className?: string;
}

export function DataTableColumnHeader<TData, TValue>({
  column,
  title,
  className,
}: DataTableColumnHeaderProps<TData, TValue>) {
  if (!column.getCanSort()) {
    return <span className={cn("text-sm", className)}>{title}</span>;
  }

  const sorted = column.getIsSorted();

  return (
    <Button
      variant="ghost"
      size="sm"
      className={cn("-ms-3 h-8", className)}
      onClick={() => column.toggleSorting(sorted === "asc")}
    >
      {title}
      {sorted === "asc" ? (
        <ArrowUp className="ms-1.5 h-3.5 w-3.5" />
      ) : sorted === "desc" ? (
        <ArrowDown className="ms-1.5 h-3.5 w-3.5" />
      ) : (
        <ArrowsDownUp className="ms-1.5 h-3.5 w-3.5 text-muted-foreground/50" />
      )}
    </Button>
  );
}
