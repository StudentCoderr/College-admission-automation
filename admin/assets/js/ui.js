/* ==========================================================================
 * Small UI helpers: toasts, modal dialogs, confirm dialogs, formatting.
 * ========================================================================= */
(function () {
  "use strict";

  var ui = {};

  ui.escapeHtml = function (value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  };

  ui.formatDate = function (value) {
    if (!value) return "\u2014";
    var d = new Date(value);
    if (isNaN(d.getTime())) return String(value);
    return d.toLocaleString(undefined, {
      year: "numeric", month: "short", day: "numeric",
      hour: "2-digit", minute: "2-digit"
    });
  };

  ui.formatDateOnly = function (value) {
    if (!value) return "\u2014";
    var d = new Date(value);
    if (isNaN(d.getTime())) return String(value);
    return d.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
  };

  ui.formatBytes = function (bytes) {
    if (bytes == null) return "\u2014";
    if (bytes < 1024) return bytes + " B";
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
    return (bytes / 1024 / 1024).toFixed(1) + " MB";
  };

  ui.badge = function (status) {
    var meta = ADMIN.STATUS_META[status] || { label: status, tone: "gray" };
    return '<span class="badge badge-' + meta.tone + '">' + ui.escapeHtml(meta.label) + "</span>";
  };

  // ---------- Toasts ----------------------------------------------------
  function toast(message, type) {
    var container = document.querySelector(".toast-container");
    if (!container) {
      container = document.createElement("div");
      container.className = "toast-container";
      document.body.appendChild(container);
    }
    var el = document.createElement("div");
    el.className = "toast " + (type || "info");
    el.textContent = message;
    container.appendChild(el);
    setTimeout(function () {
      el.style.opacity = "0";
      el.style.transition = "opacity 0.3s ease";
      setTimeout(function () { el.remove(); }, 320);
    }, 3500);
  }
  ui.toast = toast;
  ui.success = function (m) { toast(m, "success"); };
  ui.error = function (m) { toast(m, "error"); };
  ui.info = function (m) { toast(m, "info"); };

  // ---------- Modal ------------------------------------------------------
  function modalElement() {
    var overlay = document.querySelector(".modal-overlay");
    if (!overlay) {
      overlay = document.createElement("div");
      overlay.className = "modal-overlay";
      overlay.innerHTML =
        '<div class="modal" role="dialog" aria-modal="true">' +
        '  <div class="modal-head"><h3></h3>' +
        '    <button type="button" class="close btn-ghost" aria-label="Close">&times;</button></div>' +
        '  <div class="modal-body"></div>' +
        '  <div class="modal-foot"></div>' +
        "</div>";
      document.body.appendChild(overlay);
      overlay.addEventListener("click", function (e) {
        if (e.target === overlay) ui.closeModal();
      });
      overlay.querySelector(".close").addEventListener("click", function () {
        if (!overlay.querySelector(".modal").dataset.locked) ui.closeModal();
      });
    }
    return overlay;
  }

  ui.openModal = function (title, bodyHtml, footHtml, options) {
    options = options || {};
    var overlay = modalElement();
    overlay.querySelector(".modal h3").textContent = title;
    overlay.querySelector(".modal-body").innerHTML = bodyHtml;
    overlay.querySelector(".modal-foot").innerHTML = footHtml || "";
    overlay.querySelector(".modal").dataset.locked = options.locked ? "1" : "";
    overlay.classList.add("show");
    var first = overlay.querySelector("input, select, textarea, button:not(.close)");
    if (first) setTimeout(function () { first.focus(); }, 30);
    return overlay;
  };

  ui.closeModal = function () {
    var overlay = modalElement();
    overlay.classList.remove("show");
    overlay.querySelector(".modal-body").innerHTML = "";
    overlay.querySelector(".modal-foot").innerHTML = "";
    overlay.querySelector(".modal").dataset.locked = "";
  };

  // ---------- Confirm dialog ----------------------------------------------
  ui.confirm = function (opts) {
    return new Promise(function (resolve) {
      opts = opts || {};
      var noteRequired = !!opts.needsNote;
      var body =
        (opts.message ? "<p>" + ui.escapeHtml(opts.message) + "</p>" : "") +
        (opts.noteLabel
          ? '<div class="form-field mt" id="confirm-note-field">' +
            "  <label>" + ui.escapeHtml(opts.noteLabel) + " <span class='muted'>(required)</span></label>" +
            '  <textarea id="confirm-note" placeholder="Explain the decision to the applicant"></textarea>' +
            '  <div class="field-error hidden" id="confirm-note-error"></div>' +
            "</div>"
          : "");

      var foot =
        '<button type="button" class="btn-secondary" id="confirm-cancel">Cancel</button>' +
        '<button type="button" class="' + (opts.danger ? "btn-danger" : "btn-primary") +
        '" id="confirm-ok">' + ui.escapeHtml(opts.confirmText || "Confirm") + "</button>";

      var overlay = ui.openModal(opts.title || "Are you sure?", body, foot, { locked: true });
      overlay.querySelector(".modal").dataset.locked = "1";

      function finish(value) {
        overlay.classList.remove("show");
        overlay.querySelector(".modal-body").innerHTML = "";
        overlay.querySelector(".modal-foot").innerHTML = "";
        overlay.querySelector(".modal").dataset.locked = "";
        resolve(value);
      }

      overlay.querySelector("#confirm-cancel").addEventListener("click", function () { finish(null); });
      overlay.querySelector("#confirm-ok").addEventListener("click", function () {
        var noteEl = overlay.querySelector("#confirm-note");
        var errEl = overlay.querySelector("#confirm-note-error");
        if (noteRequired && noteEl && !noteEl.value.trim()) {
          errEl.textContent = "A note is required for this decision.";
          errEl.classList.remove("hidden");
          noteEl.focus();
          return;
        }
        finish({ note: noteEl ? noteEl.value.trim() : "" });
      });
      // Enter in the note field confirms; Escape is handled globally below.
      var noteEl = overlay.querySelector("#confirm-note");
      if (noteEl) {
        noteEl.addEventListener("keydown", function (e) {
          if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            overlay.querySelector("#confirm-ok").click();
          }
        });
      }
    });
  };

  // ---------- Loading helpers --------------------------------------------
  function setLoading(containerId, loading, message) {
    var el = document.getElementById(containerId);
    if (!el) return;
    if (loading) {
      el.setAttribute("data-was-empty", el.innerHTML === "" ? "1" : "0");
      el.innerHTML = '<tr class="loading-row"><td colspan="99">' +
        '<div class="spinner"></div><p class="mt">' + ui.escapeHtml(message || "Loading\u2026") +
        "</p></td></tr>";
    } else if (el.getAttribute("data-was-empty") === "1") {
      el.removeAttribute("data-was-empty");
      el.innerHTML = "";
    }
  }
  ui.setLoading = setLoading;

  ui.debounce = function (fn, wait) {
    var timer = null;
    return function () {
      var args = arguments;
      var ctx = this;
      clearTimeout(timer);
      timer = setTimeout(function () { fn.apply(ctx, args); }, wait || 400);
    };
  };

  window.ADMIN.UI = ui;
})();