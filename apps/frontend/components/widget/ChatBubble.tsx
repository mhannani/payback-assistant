import { cn } from "@/lib/utils";
import type { Msg } from "@/lib/types";
import { ProductList, RouteCard } from "./ProductCard";
import { CompareCard } from "./CompareCard";

/** Render one message. User + plain-text/clarify/decline assistant messages are speech bubbles;
 * product, compare, and route messages render their richer cards inside an assistant-aligned column. */
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

  // Assistant speech bubbles: plain text, a clarifying question, or an out-of-scope decline (a helpful
  // hand-off / polite refusal — message only, no button).
  if (msg.kind === "text" || msg.kind === "clarify" || msg.kind === "decline") {
    const text = msg.kind === "clarify" ? msg.question : msg.kind === "text" ? msg.text : msg.message;
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

  // Rich assistant content (cards / table) spans wider than a bubble.
  return (
    <div className="flex flex-col gap-2">
      {msg.kind === "products" && <ProductList items={msg.items} />}
      {msg.kind === "compare" && (
        <>
          {msg.message && (
            <div className="rounded-2xl rounded-bl-md bg-accent px-4 py-2.5 text-sm text-foreground">
              {msg.message}
            </div>
          )}
          <CompareCard items={msg.items} cheapestId={msg.cheapestId} />
        </>
      )}
      {msg.kind === "route" && (
        <RouteCard message={msg.message} deeplink={msg.deeplink} partnerName={msg.partnerName} />
      )}
    </div>
  );
}
