"use client";

import { ArrowLeftIcon, SpinnerIcon } from "@phosphor-icons/react";
import Link from "next/link";
import { PaybackLogo } from "@/components/PaybackLogo";
import { DataTable } from "@/components/data-table";
import { useProductColumns } from "@/components/products/products-columns";
import { ProductsToolbar } from "@/components/products/products-toolbar";
import { useProductsFilters } from "@/components/products/use-products-filters";

/** The product catalog table — Helfio's clients-page orchestration adapted: header + toolbar +
 * DataTable with server-side pagination. Shows the real dm/EDEKA/Amazon catalog the assistant
 * searches over. */
export default function ProductsPage() {
  const filters = useProductsFilters();
  const { columns, columnLabels } = useProductColumns();

  return (
    <div className="flex h-screen w-full flex-col gap-4 px-6 py-6">
      {/* Header */}
      <header className="flex items-center gap-3">
        <Link
          href="/"
          aria-label="Zurück zur Startseite"
          className="flex h-9 w-9 items-center justify-center rounded-full text-muted-foreground transition-colors hover:bg-muted"
        >
          <ArrowLeftIcon size={18} weight="bold" />
        </Link>
        <PaybackLogo className="h-7 w-auto" />
        <div className="min-w-0 flex-1">
          <h1 className="text-lg font-semibold leading-tight text-foreground">Produktkatalog</h1>
          <p className="text-xs text-muted-foreground">
            {filters.total.toLocaleString("de-DE")} Produkte bei dm, EDEKA &amp; Amazon
          </p>
        </div>
      </header>

      {/* Toolbar */}
      <ProductsToolbar {...filters} />

      {/* Table — fills the remaining height; the footer pages server-side. */}
      <div className="min-h-0 flex-1">
        {filters.loading ? (
          <div className="flex h-full items-center justify-center">
            <SpinnerIcon className="h-6 w-6 animate-spin text-muted-foreground" weight="bold" />
          </div>
        ) : (
          <DataTable
            columns={columns}
            data={filters.items}
            columnLabels={columnLabels}
            getRowId={(row) => row.id}
            emptyMessage="Keine Produkte gefunden."
            pageSize={filters.items.length || 1}
            pagination={{
              page: filters.page,
              totalPages: filters.totalPages,
              onPageChange: filters.setPage,
            }}
          />
        )}
      </div>
    </div>
  );
}
