/* PAYBACK chat widget embed.
 *
 * Drop `<script src="https://payback.mhannani.me/widget.js" defer></script>` on any page and a
 * floating chat bubble appears bottom-right; clicking it opens the assistant in an iframe.
 *
 * Single-tenant demo — everything is hardcoded (color, logo, iframe URL). No per-org config fetch,
 * no widget key, no resume token (the SaaS multi-tenant plumbing the source had is stripped).
 * Ported from Empfio's widget.js. */
(function () {
  if (window.__PAYBACK_WIDGET__) return;
  window.__PAYBACK_WIDGET__ = true;

  var COLOR = "#0046AA"; // PAYBACK blue
  // The widget app lives on the same origin that served this script.
  var scriptTag =
    document.currentScript || document.querySelector('script[src*="widget.js"]');
  var origin = scriptTag
    ? new URL(scriptTag.src).origin
    : window.location.origin;
  var IFRAME_SRC = origin + "/widget";

  // The PAYBACK mark — the 2×2 domino (three outlined + top-right filled), white on the blue bubble.
  var ICON_LOGO =
    '<svg viewBox="0 0 64 64" width="26" height="26" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">' +
    '<circle cx="18" cy="18" r="9.5" fill="none" stroke="#fff" stroke-width="3"/>' +
    '<circle cx="46" cy="18" r="11" fill="#fff"/>' +
    '<circle cx="18" cy="46" r="9.5" fill="none" stroke="#fff" stroke-width="3"/>' +
    '<circle cx="46" cy="46" r="9.5" fill="none" stroke="#fff" stroke-width="3"/>' +
    '</svg>';

  function build() {
    var iframeOrigin = new URL(IFRAME_SRC).origin;

    // ----- Container -----
    // The panel stacks ABOVE the bubble (Empfio layout): a column flex, right-aligned, the iframe on
    // top and the persistent bubble at the bottom with a gap between them.
    var container = document.createElement("div");
    container.id = "payback-widget-container";
    container.style.cssText =
      "position:fixed;bottom:20px;right:20px;z-index:2147483000;display:flex;flex-direction:column;align-items:flex-end;gap:12px";

    // Caret-down icon shown on the bubble while the panel is open (Empfio's open-state affordance).
    var ICON_CARET =
      '<svg viewBox="0 0 256 256" width="24" height="24" fill="#fff" aria-hidden="true"><path d="M213.66,101.66l-80,80a8,8,0,0,1-11.32,0l-80-80A8,8,0,0,1,53.66,90.34L128,164.69l74.34-74.35a8,8,0,0,1,11.32,11.32Z"/></svg>';

    // ----- Bubble button -----
    var button = document.createElement("button");
    button.type = "button";
    button.setAttribute("aria-label", "Chat with the PAYBACK assistant");
    button.innerHTML = ICON_LOGO;
    button.style.cssText = [
      "width:48px",
      "height:48px",
      "border-radius:9999px",
      "border:none",
      "cursor:pointer",
      "background-color:" + COLOR,
      "box-shadow:0 4px 16px rgba(0,0,0,0.20)",
      "display:flex",
      "align-items:center",
      "justify-content:center",
      "transition:transform 0.15s ease,box-shadow 0.15s ease",
    ].join(";");
    button.addEventListener("mouseenter", function () {
      button.style.transform = "scale(1.08)";
      button.style.boxShadow = "0 6px 24px rgba(0,0,0,0.28)";
    });
    button.addEventListener("mouseleave", function () {
      button.style.transform = "scale(1)";
      button.style.boxShadow = "0 4px 16px rgba(0,0,0,0.20)";
    });

    // ----- Chat iframe -----
    var iframeWrap = document.createElement("div");
    iframeWrap.style.cssText = [
      "display:none",
      "width:400px",
      "height:720px",
      "border-radius:24px",
      "overflow:hidden",
      "box-shadow:0 12px 34px rgba(0,0,0,0.30)",
      "background:#fff",
    ].join(";");

    var iframe = document.createElement("iframe");
    iframe.title = "PAYBACK Chat";
    iframe.style.cssText = "width:100%;height:100%;border:0;";
    // Allow the mic for voice dictation; sandbox blocks top-navigation/popups.
    iframe.setAttribute("allow", "microphone; clipboard-write");
    iframe.setAttribute(
      "sandbox",
      "allow-forms allow-modals allow-same-origin allow-scripts",
    );
    var iframeLoaded = false;
    iframeWrap.appendChild(iframe);

    function isMobile() {
      return window.innerWidth < 480;
    }
    function applyMobileLayout() {
      iframeWrap.style.cssText +=
        ";position:fixed;top:0;left:0;right:0;bottom:0;width:100vw;height:100vh;border-radius:0";
    }
    function applyDesktopLayout() {
      iframeWrap.style.position = "relative";
      iframeWrap.style.top = iframeWrap.style.left = iframeWrap.style.right = iframeWrap.style.bottom = "";
      iframeWrap.style.width = "400px";
      iframeWrap.style.height = "720px";
      iframeWrap.style.borderRadius = "24px";
    }

    // ----- Open / close -----
    var isOpen = false;
    function openChat() {
      isOpen = true;
      if (!iframeLoaded) {
        iframe.src = IFRAME_SRC;
        iframeLoaded = true;
      }
      iframeWrap.style.display = "block";
      if (isMobile()) {
        // Mobile: the panel goes fullscreen, so hide the bubble underneath.
        applyMobileLayout();
        button.style.display = "none";
      } else {
        // Desktop: the panel floats ABOVE a persistent bubble, which becomes a caret-down.
        applyDesktopLayout();
        button.style.display = "flex";
        button.innerHTML = ICON_CARET;
      }
    }
    function closeChat() {
      isOpen = false;
      iframeWrap.style.display = "none";
      button.style.display = "flex";
      button.innerHTML = ICON_LOGO;
    }
    button.addEventListener("click", function () {
      if (isOpen) closeChat();
      else openChat();
    });

    // The in-iframe close button posts this; accept it only from our own iframe origin.
    window.addEventListener("message", function (event) {
      if (!event || !event.data) return;
      if (event.origin !== iframeOrigin) return;
      if (event.data === "PAYBACK_CLOSE") closeChat();
    });
    window.addEventListener("resize", function () {
      if (iframeWrap.style.display !== "none") {
        if (isMobile()) applyMobileLayout();
        else applyDesktopLayout();
      }
    });

    container.appendChild(iframeWrap);
    container.appendChild(button);
    document.body.appendChild(container);

    // Minimal public API so the host page can open the widget (e.g. from an example chip).
    window.PaybackChat = { open: openChat, close: closeChat };
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", build);
  } else {
    build();
  }
})();
