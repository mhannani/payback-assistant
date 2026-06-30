"use client";

/**
 * Grid header + body rows for DataTable. Each row is a CSS grid that shares the
 * same ``grid-template-columns`` (from column-sizing), so header and body cells
 * stay column-aligned with a single scroll container (no two-table sync).
 *
 * A cell is a flex box with ``min-w-0 overflow-hidden`` so its track width is
 * authoritative: overflowing content clips instead of widening the track or
 * wrapping. Cells render their column's own content verbatim — we do NOT wrap
 * it in a truncating span (that would clip composite cells like avatar+name);
 * text columns truncate inside their own cell renderer.
 */

import { flexRender, type HeaderGroup, type Row } from "@tanstack/react-table";

import { cn } from "@/lib/utils";
import type { ColumnMeta } from "./column-sizing";

/**
 * Per-cell flex/padding/alignment shared by header and body.
 * ``clip`` adds ``overflow-hidden`` (body cells — so data clips to the track);
 * header cells pass ``clip=false`` so the sortable button's ``-ms-3`` negative
 * margin isn't cut off (which clipped the first letter of each title).
 */
function cellClass(columnId: string, clip: boolean, extra?: string): string {
  return cn(
    "flex min-w-0 items-center px-3",
    clip && "overflow-hidden",
    columnId === "select" && "justify-center px-0",
    columnId === "actions" && "justify-end pe-3 ps-0",
    extra,
  );
}

function metaClass(meta: unknown): string | undefined {
  return (meta as ColumnMeta | undefined)?.className;
}

interface HeaderRowProps<TData, TValue> {
  headerGroup: HeaderGroup<TData>;
  gridTemplateColumns: string;
  /** Rendered into the ``actions`` header cell (the column view-options gear). */
  renderActionsHeader: () => React.ReactNode;
}

export function DataTableHeaderRow<TData, TValue>({
  headerGroup,
  gridTemplateColumns,
  renderActionsHeader,
}: HeaderRowProps<TData, TValue>) {
  return (
    <div
      role="row"
      style={{ gridTemplateColumns }}
      // ``w-full min-w-max``: ``w-full`` fills the scroller so the ``fr`` tracks
      // distribute slack on desktop; ``min-w-max`` lets the row grow PAST the
      // viewport when the column min-widths sum wider (mobile) so it scrolls
      // horizontally AND the sticky header's background spans the full table
      // width (not just the viewport, which left titles over bare background).
      className="sticky top-0 z-10 grid w-full min-w-max border-b bg-muted"
    >
      {headerGroup.headers.map((header) => (
        <div
          key={header.id}
          role="columnheader"
          className={cn(
            "h-10 whitespace-nowrap text-sm font-medium text-muted-foreground",
            cellClass(header.column.id, false),
            metaClass(header.column.columnDef.meta),
          )}
        >
          {header.column.id === "actions" ? (
            <div className="hidden sm:flex">{renderActionsHeader()}</div>
          ) : header.isPlaceholder ? null : (
            flexRender(header.column.columnDef.header, header.getContext())
          )}
        </div>
      ))}
    </div>
  );
}

interface BodyRowProps<TData> {
  row: Row<TData>;
  gridTemplateColumns: string;
  onRowClick?: (row: TData) => void;
}

export function DataTableBodyRow<TData>({
  row,
  gridTemplateColumns,
  onRowClick,
}: BodyRowProps<TData>) {
  return (
    <div
      role="row"
      data-state={row.getIsSelected() && "selected"}
      style={{ gridTemplateColumns }}
      onClick={() => onRowClick?.(row.original)}
      className={cn(
        // ``w-full min-w-max`` — same as the header row, so body rows fill the
        // scroller on desktop and stay aligned with the header under horizontal
        // scroll on mobile.
        "group/row grid w-full min-w-max border-b border-border/40 transition-colors",
        "hover:bg-muted/50 data-[state=selected]:bg-muted",
        onRowClick && "cursor-pointer",
      )}
    >
      {row.getVisibleCells().map((cell) => (
        <div
          key={cell.id}
          role="cell"
          onClick={
            cell.column.id === "select" || cell.column.id === "actions"
              ? (e) => e.stopPropagation()
              : undefined
          }
          className={cn(
            "min-h-[3.25rem] py-2 text-sm",
            cellClass(cell.column.id, true),
            metaClass(cell.column.columnDef.meta),
          )}
        >
          {flexRender(cell.column.columnDef.cell, cell.getContext())}
        </div>
      ))}
    </div>
  );
}
