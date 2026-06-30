"use client";

/**
 * Reusable DataTable (CSS-grid layout).
 *
 * Why grid, not <table>: the width requirement is "the checkbox is first at a
 * fixed width, the name column starts right after it and takes the available
 * space, and any leftover space is split across the other columns." That is a
 * fractional distribution — trivial and bug-free with ``grid-template-columns``
 * (``32px minmax(200px,2fr) minmax(140px,1fr) … 40px``) and fragile/impossible
 * with <table> width hints (which is what caused the wrap / shift / balloon
 * churn). The whole width model is isolated in ``column-sizing.ts``; the rows
 * live in ``data-table-row.tsx``; this file only owns state + composition.
 *
 * One scroll container: sticky header rows, scrolling body, optional pinned
 * footer. Rows/cells carry ARIA table roles so semantics survive the move off
 * the native <table>.
 */

import { useEffect, useState } from "react";
import {
  useReactTable,
  getCoreRowModel,
  getSortedRowModel,
  getPaginationRowModel,
  type ColumnDef,
  type SortingState,
  type RowSelectionState,
  type VisibilityState,
} from "@tanstack/react-table";

import { useIsMobile } from "@/hooks/use-mobile";

import { DataTableViewOptions } from "./data-table-view-options";
import { DataTableFooter, type DataTableFooterProps } from "./data-table-footer";
import { DataTableHeaderRow, DataTableBodyRow } from "./data-table-row";
import { buildGridTemplate, type ColumnMeta } from "./column-sizing";

// ─── Props ────────────────────────────────────────────────────────────────────

interface DataTableProps<TData, TValue> {
  columns: ColumnDef<TData, TValue>[];
  data: TData[];
  pageSize?: number;
  onRowClick?: (row: TData) => void;
  rowSelection?: RowSelectionState;
  onRowSelectionChange?: (selection: RowSelectionState) => void;
  /**
   * Derive a stable row id (defaults to the row index when omitted). Pass
   * a real entity id so `rowSelection` keys are entity ids, not indices —
   * then a controlled selection survives pagination, sorting, and data
   * invalidation instead of silently pointing at whatever row now sits at
   * that index. Required for any table whose bulk selection must persist
   * across page changes.
   */
  getRowId?: (row: TData, index: number) => string;
  columnLabels?: Record<string, string>;
  initialColumnVisibility?: VisibilityState;
  emptyMessage?: string;
  /**
   * Persist the user's column-visibility choices in localStorage under
   * this key. Without it the table behaves exactly as before (session-
   * only state, resets on reload). Bump the version suffix when the
   * column set changes incompatibly so old stored choices don't hide
   * newly-added columns forever.
   */
  storageKey?: string;
  /**
   * Per-column "is this column worth showing by default?" predicate
   * applied once on first mount (and re-applied when `data` shape
   * changes if the user has not interacted with the gear). The default
   * rule: hide a column if no row in `data` has a non-empty value for
   * it. This keeps empty optional columns out of the table while still
   * letting owners opt them in from the gear.
   *
   * Columns where `enableHiding === false` (select, actions, primary
   * identity) are always visible regardless of what this returns.
   */
  defaultVisibility?: (columnId: string, data: TData[]) => boolean;
  /**
   * Server-side pagination. When provided, the table renders a footer
   * pinned to the bottom INSIDE its bordered box (controls right-
   * aligned) and only the row area scrolls above it — so pagination no
   * longer costs a separate sibling row of vertical space. Omit it for
   * static / non-paginated tables (no footer renders). Driven by the
   * page's own ``{ page, totalPages, onPageChange }`` state, not by
   * TanStack's internal pagination model.
   */
  pagination?: DataTableFooterProps;
}

const VISIBILITY_STORAGE_VERSION = 1;

function readStoredVisibility(storageKey: string): VisibilityState | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(storageKey);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as { v?: number; cols?: VisibilityState };
    if (parsed.v !== VISIBILITY_STORAGE_VERSION) return null;
    return parsed.cols ?? null;
  } catch {
    // Corrupt JSON, quota exceeded, private mode — fall through to
    // default. This must never throw and break the table render.
    return null;
  }
}

function writeStoredVisibility(storageKey: string, cols: VisibilityState): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(
      storageKey,
      JSON.stringify({ v: VISIBILITY_STORAGE_VERSION, cols }),
    );
  } catch {
    // Quota exceeded / private mode — silent. Persistence is best-
    // effort; the table still works without it.
  }
}

// ─── Component ────────────────────────────────────────────────────────────────

export function DataTable<TData, TValue>({
  columns,
  data,
  pageSize = 100,
  onRowClick,
  rowSelection: controlledRowSelection,
  onRowSelectionChange,
  getRowId,
  columnLabels,
  initialColumnVisibility,
  emptyMessage = "No results.",
  storageKey,
  defaultVisibility,
  pagination,
}: DataTableProps<TData, TValue>) {
  const [sorting, setSorting] = useState<SortingState>([]);
  const [internalRowSelection, setInternalRowSelection] = useState<RowSelectionState>({});

  // Lazy init: stored choice wins, then data-driven default-hide, then
  // the explicit initialColumnVisibility prop, then empty. We run
  // `defaultVisibility` only on the FIRST render — once the table is
  // mounted, the user's gear toggles drive state directly so it never
  // flips back to "auto-hidden" when fresh data arrives. To re-derive
  // when there's no stored preference and the underlying entity has
  // genuinely changed (e.g. custom-field added), bump `storageKey`.
  const [columnVisibility, setColumnVisibility] = useState<VisibilityState>(() => {
    if (storageKey) {
      const stored = readStoredVisibility(storageKey);
      if (stored) return stored;
    }
    if (defaultVisibility) {
      const derived: VisibilityState = {};
      for (const col of columns) {
        const id =
          (col as { id?: string }).id ??
          (col as { accessorKey?: string }).accessorKey;
        if (!id) continue;
        if (!defaultVisibility(id, data)) {
          derived[id] = false;
        }
      }
      return { ...derived, ...(initialColumnVisibility ?? {}) };
    }
    return initialColumnVisibility ?? {};
  });

  // Persist on every change. We don't bother debouncing because gear
  // clicks are user-driven (not high-frequency) and localStorage writes
  // on a few-KB payload are sub-millisecond.
  useEffect(() => {
    if (!storageKey) return;
    writeStoredVisibility(storageKey, columnVisibility);
  }, [storageKey, columnVisibility]);

  const rowSelection = controlledRowSelection ?? internalRowSelection;
  const setRowSelection = onRowSelectionChange ?? setInternalRowSelection;

  // Responsive column hiding drives TanStack visibility (NOT a CSS ``hidden``
  // class) so the grid template — built from the visible columns — always
  // matches what's rendered. A CSS-hidden cell would leave a phantom empty
  // grid track and shift every column. Columns opt in with ``meta.hideOnMobile``.
  const isMobile = useIsMobile();
  const effectiveVisibility: VisibilityState = { ...columnVisibility };
  if (isMobile) {
    for (const col of columns) {
      const id = (col as { id?: string }).id ?? (col as { accessorKey?: string }).accessorKey;
      if (!id) continue;
      if ((col.meta as ColumnMeta | undefined)?.hideOnMobile && effectiveVisibility[id] !== true) {
        effectiveVisibility[id] = false;
      }
    }
  }

  const table = useReactTable({
    data,
    columns,
    state: { sorting, rowSelection, columnVisibility: effectiveVisibility },
    enableRowSelection: true,
    ...(getRowId ? { getRowId } : {}),
    onRowSelectionChange: (updater) => {
      const next = typeof updater === "function" ? updater(rowSelection) : updater;
      setRowSelection(next);
    },
    onSortingChange: setSorting,
    onColumnVisibilityChange: setColumnVisibility,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    initialState: { pagination: { pageSize } },
  });

  // One grid template, shared by every header + body row, so columns align
  // with a single scroll container. Recomputed when visibility changes.
  const gridTemplateColumns = buildGridTemplate(table.getVisibleLeafColumns());
  const rows = table.getRowModel().rows;

  return (
    <div role="table" className="flex h-full flex-col overflow-hidden rounded-md border">
      {/* Single scroll container: sticky header rows, scrolling body. The
          footer is a pinned sibling below. ``rounded-[inherit]`` clips content
          to the box radius so nothing paints in the rounded corner band. */}
      <div className="flex-1 overflow-auto rounded-[inherit]">
        {/* The header + body share ONE width context. Without this wrapper each
            row is laid out independently, so when the grid overflows the
            viewport (mobile) the ``fr`` tracks can resolve to slightly
            different widths per row — the right-edge columns (actions) then
            drift out of alignment row-to-row. ``min-w-max`` makes the wrapper
            as wide as the widest row's intrinsic content and every row fills
            it, so all rows resolve their tracks against the same width. */}
        <div className="w-full min-w-max">
          {table.getHeaderGroups().map((headerGroup) => (
            <DataTableHeaderRow
              key={headerGroup.id}
              headerGroup={headerGroup}
              gridTemplateColumns={gridTemplateColumns}
              renderActionsHeader={() => (
                <DataTableViewOptions table={table} columnLabels={columnLabels} />
              )}
            />
          ))}

          {rows.length ? (
            rows.map((row) => (
              <DataTableBodyRow
                key={row.id}
                row={row}
                gridTemplateColumns={gridTemplateColumns}
                onRowClick={onRowClick}
              />
            ))
          ) : (
            <div
              role="row"
              className="flex h-24 items-center justify-center text-sm text-muted-foreground"
            >
              {emptyMessage}
            </div>
          )}
        </div>
      </div>

      {pagination && <DataTableFooter {...pagination} />}
    </div>
  );
}
