import { Toaster } from "sonner";
import { WidgetPanel } from "@/components/widget/WidgetPanel";

/** The embed iframe target. The panel fills the iframe viewport — here the panel IS the page.
 * The Toaster renders voice/dictation snackbars inside the widget. */
export default function WidgetPage() {
  return (
    <main className="h-screen w-screen">
      <WidgetPanel />
      <Toaster position="top-center" richColors closeButton />
    </main>
  );
}
