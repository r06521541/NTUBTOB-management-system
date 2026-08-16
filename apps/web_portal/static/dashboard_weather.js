(() => {
  "use strict";
  const target = document.querySelector("[data-dashboard-weather-url]");
  if (!target) return;
  fetch(target.dataset.dashboardWeatherUrl, { credentials: "same-origin", headers: { Accept: "text/html" } })
    .then((response) => response.ok && response.status !== 204 ? response.text() : "")
    .then((markup) => { if (markup) target.outerHTML = markup; else target.remove(); })
    .catch(() => target.remove());
})();
