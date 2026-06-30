import { cn } from "@/lib/utils";
import type { Msg } from "@/lib/types";
import { ProductList, RouteCard } from "./ProductCard";

/** Render one message. User + plain-text/clarify assistant messages are speech bubbles; product and
 * route messages render their richer cards inside an assistant-aligned column. */
export function ChatBubble({ msg }: { msg: Msg }) {
  if (msg.role === "user") {
    return (
      <div className="flex justify-end">
        <div className="max-w-[85%] rounded-2xl rounded-br-md bg-primary px-4 py-2.5 text-sm text-primary-foreground">
          {msg.text}
        </div>
      </div>
    );
  }

  // Assistant side.
  if (msg.kind === "text" || msg.kind === "clarify") {
    const text = msg.kind === "text" ? msg.text : msg.question;
    return (
      <div className="flex justify-start">
        <div
          className={cn(
            "max-w-[85%] rounded-2xl rounded-bl-md bg-accent px-4 py-2.5 text-sm text-foreground",
            msg.kind === "clarify" && "font-medium",
          )}
        >
          {text}
        </div>
      </div>
    );
  }

  // Rich assistant content (cards) spans wider than a bubble.
  return (
    <div className="flex flex-col gap-2">
      {msg.kind === "products" && <ProductList items={msg.items} />}
      {msg.kind === "route" && (
        <RouteCard message={msg.message} deeplink={msg.deeplink} partnerName={msg.partnerName} />
      )}
    </div>
  );
}
