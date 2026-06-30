"use client";

/** Debounced product search — Helfio's search-input shape (spinner-while-fetching, md:max-w-md). */
import { MagnifyingGlassIcon as MagnifyingGlass, SpinnerIcon as Spinner } from "@phosphor-icons/react";
import { Input } from "@/components/ui/input";

interface ProductsSearchInputProps {
  value: string;
  onValueChange: (value: string) => void;
  fetching: boolean;
}

export function ProductsSearchInput({ value, onValueChange, fetching }: ProductsSearchInputProps) {
  return (
    <div className="relative flex-1 md:max-w-md">
      {fetching ? (
        <Spinner
          className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 animate-spin text-muted-foreground"
          weight="bold"
        />
      ) : (
        <MagnifyingGlass className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
      )}
      <Input
        placeholder="Produkte durchsuchen…"
        value={value}
        onChange={(e) => onValueChange(e.target.value)}
        className="h-8 w-full pl-8 text-xs"
      />
    </div>
  );
}
