/* College Admission Automation System - progressive front-end enhancements.
   All real validation happens on the server; this only improves UX. */
(function () {
  "use strict";

  document.addEventListener("DOMContentLoaded", function () {
    // Auto-calculate percentage from marks obtained / total where possible.
    var obtained = document.getElementById("marks_obtained");
    var total = document.getElementById("marks_total");
    var percentage = document.getElementById("percentage");

    function recalc() {
      if (!obtained || !total || !percentage) return;
      var o = parseFloat(obtained.value);
      var t = parseFloat(total.value);
      if (!isNaN(o) && !isNaN(t) && t > 0 && o <= t && !percentage.value) {
        percentage.value = ((o / t) * 100).toFixed(2);
      }
    }
    if (obtained && total) {
      obtained.addEventListener("input", recalc);
      total.addEventListener("input", recalc);
    }

    // Prevent double submission of forms.
    // Forms that ask for confirmation are handled by ui.js: it disables the
    // button only after the user confirms. Disabling it here first would make
    // ui.js treat the click as a double-submit and block the form entirely.
    document.querySelectorAll("form").forEach(function (form) {
      if (
        form.hasAttribute("data-confirm-message") ||
        form.hasAttribute("data-review-confirm")
      ) return;
      form.addEventListener("submit", function () {
        var btn = form.querySelector('button[type="submit"]');
        if (btn) {
          btn.disabled = true;
          setTimeout(function () { btn.disabled = false; }, 4000);
        }
      });
    });

    // ------------------------------------------------------------- filters
    // Course search / programme-type / course-status filter.
    // Used by the public course listing and the student course picker.
    document.querySelectorAll("[data-course-search], [data-course-type], [data-course-status]").forEach(function () {
      var scope = document.querySelector("[data-course-grid]") ||
                  document.querySelector("[data-course-options]");
      if (!scope) return;
      var root = scope.closest("[data-course-toolbar]") ||
                 scope.closest("[data-course-picker]") || document;
      var search = root.querySelector("[data-course-search]");
      var type = root.querySelector("[data-course-type]");
      var status = root.querySelector("[data-course-status]");
      var empty = root.querySelector("[data-course-empty]");

      function apply() {
        var term = search ? search.value.trim().toLowerCase() : "";
        var want = type ? type.value : "";
        var wantStatus = status ? status.value : "";
        var visible = 0;
        scope.querySelectorAll("[data-course-card]").forEach(function (card) {
          var haystack = card.getAttribute("data-search") || "";
          var matchesTerm = !term || haystack.indexOf(term) !== -1;
          var matchesType = !want || card.getAttribute("data-type") === want;
          var cardStatus = card.getAttribute("data-status") || "active";
          var matchesStatus = !wantStatus || wantStatus === "all" || cardStatus === wantStatus;
          var show = matchesTerm && matchesType && matchesStatus;
          card.hidden = !show;
          if (show) visible += 1;
        });
        if (empty) empty.hidden = visible !== 0;
      }

      if (search) search.addEventListener("input", apply);
      if (type) type.addEventListener("change", apply);
      if (status) status.addEventListener("change", apply);
    });

    // Highlight the selected course picker option (radio inside a label).
    document.querySelectorAll("[data-course-options] input[type=radio]").forEach(function (radio) {
      radio.addEventListener("change", function () {
        var scope = radio.closest("[data-course-options]");
        scope.querySelectorAll(".course-option").forEach(function (option) {
          option.classList.toggle("is-selected", option.contains(radio) && radio.checked);
        });
      });
    });

    // ------------------------------------------------------ password meter
    var pw = document.getElementById("password");
    var confirmPw = document.getElementById("confirm_password");
    if (pw && confirmPw) {
      var field = pw.closest(".field");
      var meter = document.createElement("div");
      meter.className = "pw-meter";
      meter.setAttribute("role", "status");
      meter.setAttribute("aria-live", "polite");
      meter.innerHTML =
        '<span class="pw-meter-bar weak"></span>' +
        '<span class="pw-meter-bar medium"></span>' +
        '<span class="pw-meter-bar strong"></span>' +
        '<small class="pw-meter-label">Password strength</small>';
      if (field) field.appendChild(meter);

      var matchHint = document.createElement("small");
      matchHint.className = "pw-match";
      matchHint.hidden = true;
      field.appendChild(matchHint);

      var bars = meter.querySelectorAll(".pw-meter-bar");
      var label = meter.querySelector(".pw-meter-label");

      function score(value) {
        var s = 0;
        if (!value) return 0;
        if (value.length >= 8) s += 1;
        if (/[a-z]/.test(value) && /[A-Z]/.test(value)) s += 1;
        if (/\d/.test(value)) s += 1;
        if (/[^A-Za-z0-9]/.test(value)) s += 1;
        return s;
      }

      function paint(value) {
        var s = score(value);
        var level = s >= 4 ? "strong" : s >= 3 ? "medium" : s >= 2 ? "weak" : "";
        bars.forEach(function (bar) {
          bar.classList.remove("on", "weak", "medium", "strong");
          if (level) bar.classList.add("on", level);
        });
        label.textContent =
          !value ? "Password strength" :
          level === "strong" ? "Strong password" :
          level === "medium" ? "Good password" : "Weak password — add a mix of cases, numbers and symbols";
        label.classList.toggle("strong", level === "strong");
        label.classList.toggle("medium", level === "medium");
        label.classList.toggle("weak", level === "weak");
      }

      function paintMatch() {
        var shown = pw.value.length > 0 && confirmPw.value.length > 0;
        matchHint.hidden = !shown;
        if (!shown) return;
        var ok = pw.value === confirmPw.value;
        matchHint.textContent = ok ? "Passwords match." : "Passwords do not match yet.";
        matchHint.classList.toggle("ok", ok);
      }

      pw.addEventListener("input", function () { paint(pw.value); paintMatch(); });
      confirmPw.addEventListener("input", paintMatch);
    }
  });
})();