import { Toaster } from "sonner";
import { WidgetPanel } from "@/components/widget/WidgetPanel";

/** The embed iframe target. The panel fills the iframe viewport — here the panel IS the page.
 * The Toaster renders voice/dictation snackbars inside the widget.
 *
 * h-dvh (dynamic viewport height), not h-screen (100vh): on mobile, 100vh sits behind the browser
 * chrome, so the panel overflows and the input box at its bottom gets buried. h-dvh tracks the
 * visible area, keeping the prompt reachable. */
export default function WidgetPage() {
  return (
    <main className="h-dvh w-screen">
      <WidgetPanel />
      <Toaster position="top-center" richColors closeButton />
    </main>
  );
}
