(() => {
  "use strict";

  const overlay = document.querySelector("[data-portal-loading]");
  if (!overlay) return;

  let timer = null;
  const show = () => {
    if (timer !== null) return;
    timer = window.setTimeout(() => {
      overlay.hidden = false;
      document.body.classList.add("portal-is-loading");
    }, 180);
  };

  document.addEventListener("click", (event) => {
    const link = event.target.closest("a[href]");
    if (!link || event.defaultPrevented || event.button !== 0) return;
    if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    if (link.target || link.hasAttribute("download")) return;
    const target = new URL(link.href, window.location.href);
    if (target.origin !== window.location.origin) return;
    if (target.pathname === window.location.pathname && target.search === window.location.search && target.hash) return;
    show();
  });

  document.addEventListener("submit", (event) => {
    if (!event.defaultPrevented) show();
  });

  window.addEventListener("pageshow", () => {
    if (timer !== null) window.clearTimeout(timer);
    timer = null;
    overlay.hidden = true;
    document.body.classList.remove("portal-is-loading");
  });
})();
