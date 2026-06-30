import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"
import { Slot } from "radix-ui"

import { cn } from "@/lib/utils"

// Mirrors fresh shadcn's Button primitive (compact h-8 default rhythm
// + visual polish like ``active:translate-y-px`` and
// ``aria-expanded:bg-muted`` outline/secondary/ghost open-state). Two
// intentional deviations from upstream:
//
//   1. Keeps Radix ``Slot`` so the ``asChild`` prop continues to work
//      — 13+ callers across the codebase rely on it (e.g. wrapping
//      Next ``Link`` in a button). Fresh shadcn moved to Base UI's
//      ``<ButtonPrimitive>`` which handles asChild natively but
//      isn't a drop-in: it requires the ``@base-ui/react/button``
//      dependency and changes a few prop semantics. The Slot pattern
//      is well-understood and ships today.
//
//   2. Drops the previous ``data-touch="true"`` /
//      ``min-h-11 min-w-11`` mobile inflation logic. That rule
//      auto-grew icon buttons to 44px on coarse-pointer devices to
//      meet WCAG 2.2 SC 2.5.8, but it created visual mismatches
//      (icon buttons looked "zoomed in" next to non-inflating
//      sibling controls) and forced per-caller opt-outs sprinkled
//      across the toolbar. Touch-friendly tap targets are now a
//      deliberate per-surface design decision: pick ``lg`` /
//      ``icon-lg`` sizes (h-9) where touch matters, or wrap with a
//      larger className. Same pattern shadcn itself uses.
const buttonVariants = cva(
  "inline-flex shrink-0 items-center justify-center rounded-md border border-transparent bg-clip-padding text-sm font-medium whitespace-nowrap transition-all outline-none select-none focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px] active:not-aria-[haspopup]:translate-y-px disabled:pointer-events-none disabled:opacity-50 aria-invalid:border-destructive aria-invalid:ring-destructive/20 aria-invalid:ring-[3px] dark:aria-invalid:border-destructive/50 dark:aria-invalid:ring-destructive/40 [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
  {
    variants: {
      variant: {
        default: "bg-primary text-primary-foreground hover:bg-primary/90",
        outline:
          "border-border bg-background hover:bg-muted hover:text-foreground aria-expanded:bg-muted aria-expanded:text-foreground dark:border-input dark:bg-input/30 dark:hover:bg-input/50",
        secondary:
          "bg-secondary text-secondary-foreground hover:bg-secondary/80 aria-expanded:bg-secondary aria-expanded:text-secondary-foreground",
        ghost:
          "hover:bg-muted hover:text-foreground aria-expanded:bg-muted aria-expanded:text-foreground dark:hover:bg-muted/50",
        destructive:
          "bg-destructive text-white hover:bg-destructive/90 focus-visible:ring-destructive/20 dark:focus-visible:ring-destructive/40 dark:bg-destructive/60",
        link: "text-primary underline-offset-4 hover:underline",
      },
      size: {
        // Fresh-shadcn compact rhythm. ``default`` = h-8 (down from the
        // pre-Tier-34 h-10). ``sm`` = h-7. ``icon`` = size-8.
        default: "h-8 gap-1.5 px-2.5 has-[>svg]:px-2",
        xs: "h-6 gap-1 rounded-md px-2 text-xs has-[>svg]:px-1.5 [&_svg:not([class*='size-'])]:size-3",
        sm: "h-7 gap-1 rounded-md px-2.5 text-[0.8rem] has-[>svg]:px-1.5 [&_svg:not([class*='size-'])]:size-3.5",
        lg: "h-9 gap-1.5 px-2.5 has-[>svg]:px-2",
        icon: "size-8",
        "icon-xs": "size-6 rounded-md [&_svg:not([class*='size-'])]:size-3",
        "icon-sm": "size-7 rounded-md [&_svg:not([class*='size-'])]:size-3.5",
        "icon-lg": "size-9",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
)

function Button({
  className,
  variant = "default",
  size = "default",
  asChild = false,
  ...props
}: React.ComponentProps<"button"> &
  VariantProps<typeof buttonVariants> & {
    asChild?: boolean
  }) {
  const Comp = asChild ? Slot.Root : "button"

  return (
    <Comp
      data-slot="button"
      data-variant={variant}
      data-size={size}
      className={cn(buttonVariants({ variant, size, className }))}
      {...props}
    />
  )
}

export { Button, buttonVariants }
