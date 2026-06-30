import type { Column } from "@tanstack/react-table";

/**
 * The DataTable's entire width model lives here, isolated so it can't be
 * accidentally broken by layout edits elsewhere.
 *
 * Requirement (verbatim): the checkbox comes first at a fixed width, the name
 * column starts right after it and TAKES the available space, and any space
 * left over is split across the other columns. That is a fractional grid:
 *
 *   select  → SELECT_PX        fixed — so the name column always starts at the
 *                              same x (right after the checkbox)
 *   actions → ACTIONS_PX       fixed (kebab / view-options)
 *   flex    → minmax(min, 2fr) the identity column — takes the most slack
 *   other   → minmax(min, 1fr) shares the remaining space equally, but never
 *                              shrinks below its min (so on a narrow viewport
 *                              the grid overflows and scrolls horizontally)
 *
 * A column opts into the flex track with ``meta.flex === true`` (exactly one
 * per table — the identity/name column).
 */

export const SELECT_PX = 32;
export const ACTIONS_PX = 40;
/** Floor for a content column with no declared ``size`` so it never collapses. */
export const DEFAULT_MIN_WIDTH = 140;
/** Floor for the flex (identity) column when it declares no ``size``. */
export const DEFAULT_FLEX_MIN_WIDTH = 200;

export interface ColumnMeta {
  /** Marks the single column that absorbs the most slack (the identity column). */
  flex?: boolean;
  /** Hide this column on mobile. Drives TanStack visibility (so the grid track
   *  is removed too), NOT a CSS ``hidden`` class — otherwise the track lingers
   *  and shifts every column. */
  hideOnMobile?: boolean;
  /** Extra className applied to this column's header + body cells. */
  className?: string;
}

function metaOf<TData, TValue>(c: Column<TData, TValue>): ColumnMeta {
  return (c.columnDef.meta as ColumnMeta | undefined) ?? {};
}

/** One CSS grid track per visible column, in order — the value for
 *  ``grid-template-columns`` on every header + body row. */
export function buildGridTemplate<TData, TValue>(
  columns: Column<TData, TValue>[],
): string {
  return columns
    .map((c) => {
      if (c.id === "select") return `${SELECT_PX}px`;
      // ``actions`` is a fixed track; defaults to one kebab (ACTIONS_PX) but
      // honours an explicit ``size`` when the cell holds more than one button
      // (e.g. invoices' view + download), so they aren't clipped.
      if (c.id === "actions") return `${c.columnDef.size ?? ACTIONS_PX}px`;
      const size = c.columnDef.size;
      if (metaOf(c).flex) return `minmax(${size ?? DEFAULT_FLEX_MIN_WIDTH}px, 2fr)`;
      return `minmax(${size ?? DEFAULT_MIN_WIDTH}px, 1fr)`;
    })
    .join(" ");
}
