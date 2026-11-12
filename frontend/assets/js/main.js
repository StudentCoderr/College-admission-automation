/* =========================================================================
   main.js — shared page bootstrap (runs on every page).
   -------------------------------------------------------------------------
   • Renders the shared header and footer.
   • Applies route guards declared with <body data-guard="student|admin|auth">.
   • Shows a dismissible banner while previewing with sample data.
   ========================================================================= */
(function () {
  "use strict";

  function getQueryParam(name, fallback = "") {
    return new URLSearchParams(window.location.search).get(name) || fallback;
  }

  function previewBanner() {
    if (!window.APP_CONFIG.USE_SAMPLE_DATA) return;
    if (sessionStorage.getItem("cas.bannerDismissed")) return;
    const bar = document.createElement("div");
    bar.style.cssText =
      "background:#1e3a8a;color:#dbeafe;font-size:.82rem;text-align:center;" +
      "padding:.45rem 3rem .45rem 1rem;position:relative;z-index:60";
    bar.innerHTML =
      'Preview mode — the built-in sample data set is empty. ' +
      'Set <code style="background:rgba(255,255,255,.15);border:0;color:#fff">USE_SAMPLE_DATA:false</code> ' +
      'in <code style="background:rgba(255,255,255,.15);border:0;color:#fff">assets/js/config.js</code> to use the Flask API.' +
      '<button aria-label="Dismiss" style="position:absolute;right:.6rem;top:50%;transform:translateY(-50%);' +
      'background:transparent;border:0;color:#dbeafe;font-size:1.1rem;cursor:pointer">&times;</button>';
    bar.querySelector("button").addEventListener("click", () => {
      sessionStorage.setItem("cas.bannerDismissed", "1");
      bar.remove();
    });
    document.body.prepend(bar);
  }

  function applyGuard() {
    const guard = document.body.getAttribute("data-guard");
    if (!guard) return;
    if (guard === "auth") Auth.requireAuth();
    else Auth.requireRole(guard);
  }

  document.addEventListener("DOMContentLoaded", function () {
    UI.renderHeader();
    UI.renderFooter();
    applyGuard();
    previewBanner();

    // Close the mobile menu after a navigation click.
    document.addEventListener("click", (e) => {
      const link = e.target.closest("#navMenu a");
      if (link) document.getElementById("navMenu")?.classList.remove("open");
    });
  });

  window.App = { getQueryParam };
})();
