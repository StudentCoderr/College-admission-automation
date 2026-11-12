/* College Admission Automation System — shared UI behaviours.
   Progressive enhancement only; all real logic stays on the server. */
(function () {
  "use strict";

  document.addEventListener("DOMContentLoaded", function () {
    // ------------------------------------------------------------ mobile nav
    var toggle = document.querySelector(".nav-toggle");
    var links = document.querySelector(".nav-links");
    if (toggle && links) {
      toggle.addEventListener("click", function () {
        links.classList.toggle("open");
        var open = links.classList.contains("open");
        toggle.setAttribute("aria-expanded", open ? "true" : "false");
      });
      links.querySelectorAll("a").forEach(function (a) {
        a.addEventListener("click", function () {
          if (window.innerWidth <= 860) links.classList.remove("open");
        });
      });
    }

    // ---------------------------------------------------------------- FAQ
    document.querySelectorAll(".faq-q").forEach(function (q) {
      q.addEventListener("click", function () {
        q.closest(".faq-item").classList.toggle("open");
      });
    });
    // Auto-open the first FAQ item if it contains an anchor target.
    if (window.location.hash) {
      var target = document.querySelector(window.location.hash);
      if (target) {
        var item = target.closest(".faq-item");
        if (item) item.classList.add("open");
      }
    }

    // -------------------------------------------------- password visibility
    document.querySelectorAll("[data-pw-toggle]").forEach(function (btn) {
      btn.addEventListener("click", function (e) {
        e.preventDefault();
        var input = document.getElementById(btn.getAttribute("data-pw-toggle"));
        if (!input) return;
        var showing = input.type === "text";
        input.type = showing ? "password" : "text";
        btn.classList.toggle("showing", !showing);
        btn.setAttribute("aria-pressed", showing ? "false" : "true");
        input.focus();
      });
    });

    // ------------------------------------------- submit loading indicators
    document.querySelectorAll("button[data-loading]").forEach(function (btn) {
      var form = btn.closest("form");
      if (!form) return;
      // Confirmed forms switch to their loading state only after the user
      // confirms; doing it here first would disable the button and make the
      // confirmation handler below treat the click as a double-submit.
      // Forms with a custom confirmation flow (e.g. the application review
      // decision form) manage their own submit/loading state too.
      if (
        form.hasAttribute("data-confirm-message") ||
        form.hasAttribute("data-review-confirm")
      ) return;
      var original = btn.textContent;
      form.addEventListener("submit", function () {
        btn.disabled = true;
        btn.textContent = btn.getAttribute("data-loading") || original;
      });
    });

    // ------------------------------------------------------------ toasts
    window.showToast = function (message, kind) {
      var stack = document.querySelector(".toast-stack");
      if (!stack) {
        stack = document.createElement("div");
        stack.className = "toast-stack";
        document.body.appendChild(stack);
      }
      var toast = document.createElement("div");
      toast.className = "toast toast-" + (kind || "info");
      var icon = kind === "success" ? "\u2713" : kind === "danger" ? "\u26A0" : "\u24D8";
      toast.innerHTML =
        '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" ' +
        'stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle>' +
        (kind === "success"
          ? '<path d="M8 12l3 3 5-6"></path>'
          : kind === "danger"
          ? '<path d="M12 8v4m0 4h.01"></path>'
          : '<path d="M12 16v-4m0-4h.01"></path>') +
        "</svg><span></span>";
      toast.querySelector("span").textContent = message;
      stack.appendChild(toast);
      setTimeout(function () {
        toast.classList.add("out");
        setTimeout(function () { toast.remove(); }, 250);
      }, 4200);
    };

    // --------------------------------------------------- confirm dialog
    function askConfirm(options) {
      return new Promise(function (resolve) {
        var backdrop = document.createElement("div");
        backdrop.className = "confirm-backdrop open";
        backdrop.innerHTML =
          '<div class="confirm-box" role="alertdialog" aria-modal="true" aria-labelledby="cf-title">' +
          '<h3 id="cf-title"></h3><p></p><div class="row">' +
          '<button type="button" class="btn btn-outline" data-cancel>Cancel</button>' +
          '<button type="button" class="btn btn-danger" data-ok>Delete</button></div></div>';
        backdrop.querySelector("#cf-title").textContent = options.title || "Are you sure?";
        backdrop.querySelector("p").textContent = options.message || "";
        backdrop.querySelector("[data-ok]").textContent = options.confirmLabel || "Confirm";
        backdrop.querySelector("[data-ok]").className = "btn " + (options.okClass || "btn-danger");
        document.body.appendChild(backdrop);
        backdrop.addEventListener("click", function (e) {
          if (e.target === backdrop) { close(false); return; }
          if (e.target.closest("[data-cancel]")) close(false);
          if (e.target.closest("[data-ok]")) close(true);
        });
        function close(value) {
          backdrop.remove();
          resolve(value);
        }
      });
    }

    // Confirmed destructive forms that opt in via data-confirm-message.
    document.querySelectorAll("form[data-confirm-message]").forEach(function (form) {
      form.addEventListener("submit", function (e) {
        e.preventDefault();
        // Ignore repeated clicks while the confirmation dialog is already open.
        if (form.getAttribute("data-confirm-pending") === "1") return;
        form.setAttribute("data-confirm-pending", "1");

        var btn = form.querySelector('button[type="submit"]');
        askConfirm({
          title: form.getAttribute("data-confirm-title") || "Please confirm",
          message: form.getAttribute("data-confirm-message"),
          confirmLabel: form.getAttribute("data-confirm-label") || "Confirm",
          okClass: form.getAttribute("data-confirm-kind") || "btn-danger",
        }).then(function (ok) {
          form.removeAttribute("data-confirm-pending");
          if (!ok) return;
          if (btn) {
            btn.disabled = true;
            if (btn.hasAttribute("data-loading")) {
              btn.textContent = btn.getAttribute("data-loading") || btn.textContent;
            }
          }
          form.submit();
        });
      });
    });

    // Global access so page scripts (e.g. application review) can open the
    // same styled confirmation dialog with dynamic wording.
    window.askConfirm = askConfirm;
  });
})();