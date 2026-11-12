/* ==========================================================================
 * Administrator profile: account details, a secure password change that
 * re-verifies the current password server-side, and the admin's own recent
 * activity from the audit trail.
 * ========================================================================= */
(function () {
  "use strict";

  var ui = window.ADMIN.UI;
  var Api = window.ADMIN.Api;

  var me = null;
  var bound = false;

  function row(k, v) {
    return '<div class="item"><div class="k">' + ui.escapeHtml(k) + "</div><div class='v'>" +
      ui.escapeHtml(v == null || v === "" ? "\u2014" : v) + "</div></div>";
  }

  function actionLabel(action) {
    var labels = {
      admin_login: "Signed in to the admin console",
      admin_password_change: "Password changed",
      application_status_change: "Application status updated",
      document_verify: "Document verification updated",
      course_create: "Course added",
      course_update: "Course updated",
      course_activate: "Course activated",
      course_deactivate: "Course deactivated",
      course_delete: "Course deleted",
      student_activate: "Student account activated",
      student_deactivate: "Student account deactivated"
    };
    return labels[action] || (action || "Action").replace(/_/g, " ");
  }

  function renderDetails(p) {
    if (!p) return;
    document.getElementById("profile-details").innerHTML =
      row("Full name", p.full_name) +
      row("Email", p.email) +
      row("Role", p.role) +
      row("Member since", ui.formatDate(p.created_at));
  }

  function renderActivity(entries) {
    var el = document.getElementById("profile-activity");
    if (!entries.length) {
      el.innerHTML = '<p class="muted small">No recent activity for your account.</p>';
      return;
    }
    el.innerHTML = '<div class="timeline">' + entries.map(function (e) {
      return '<div class="event"><div class="flex between"><strong>' +
        ui.escapeHtml(actionLabel(e.action)) + "</strong>" +
        '<span class="when">' + ui.escapeHtml(ui.formatDate(e.created_at)) + "</span></div></div>";
    }).join("") + "</div>";
  }

  // ---------- Password form ------------------------------------------------
  function clearErrors() {
    document.querySelectorAll("#password-form .field-error").forEach(function (el) {
      el.classList.add("hidden");
      el.textContent = "";
    });
    document.querySelectorAll("#password-form .form-field").forEach(function (f) {
      f.classList.remove("has-error");
    });
  }

  function showError(fieldId, message) {
    var field = document.getElementById(fieldId);
    if (!field) return;
    field.classList.add("has-error");
    var err = field.querySelector(".field-error");
    err.textContent = message;
    err.classList.remove("hidden");
  }

  function bindForm() {
    var form = document.getElementById("password-form");
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      clearErrors();

      var payload = {
        current_password: document.getElementById("current_password").value,
        new_password: document.getElementById("new_password").value,
        confirm_password: document.getElementById("confirm_password").value
      };

      if (!payload.current_password) {
        showError("pf-current", "Enter your current password.");
        return;
      }
      if (payload.new_password !== payload.confirm_password) {
        showError("pf-confirm", "The new passwords do not match.");
        return;
      }

      var btn = document.getElementById("password-submit");
      btn.disabled = true;
      btn.textContent = "Updating\u2026";

      Api.post(ADMIN.ENDPOINTS.profilePassword, payload)
        .then(function () {
          ui.success("Your password has been updated.");
          form.reset();
        })
        .catch(function (err) {
          if (err && err.errors && typeof err.errors === "object") {
            var map = {
              current_password: "pf-current",
              new_password: "pf-new",
              confirm_password: "pf-confirm"
            };
            Object.keys(err.errors).forEach(function (key) {
              if (map[key]) showError(map[key], err.errors[key]);
            });
          } else {
            ui.error(err.message || "Could not update your password.");
          }
        })
        .finally(function () {
          btn.disabled = false;
          btn.textContent = "Update password";
        });
    });
  }

  // ---------- Load ---------------------------------------------------------
  function load() {
    if (!bound) { bindForm(); bound = true; }

    Api.get(ADMIN.ENDPOINTS.profile)
      .then(function (body) {
        me = body.profile;
        renderDetails(me);
        return Api.get(ADMIN.ENDPOINTS.audit + "?limit=30");
      })
      .then(function (body) {
        var mine = (body.entries || []).filter(function (e) {
          return me && String(e.actor_id) === String(me.id);
        });
        renderActivity(mine.slice(0, 15));
      })
      .catch(function (err) {
        ui.error(err.message || "Could not load your profile.");
      });
  }

  window.ADMIN.Profile = { load: load };
})();
