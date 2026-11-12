/* ==========================================================================
 * Dashboard overview: live summary cards (students, applications, active
 * Polytechnic courses) plus the most recent administrator activity.
 * Every figure comes from the real /api endpoints - nothing is hard-coded.
 * ========================================================================= */
(function () {
  "use strict";

  var ui = window.ADMIN.UI;
  var Api = window.ADMIN.Api;

  function card(label, value, cls) {
    return '<div class="stat-card ' + (cls || "") + '">' +
      '<div class="stat-label">' + ui.escapeHtml(label) + "</div>" +
      '<div class="stat-value">' + ui.escapeHtml(value == null ? 0 : value) + "</div></div>";
  }

  function renderCards(stats) {
    var el = document.getElementById("overview-cards");
    el.innerHTML =
      card("Registered students", stats.students_total, "stat-total") +
      card("Total applications", stats.total, "stat-total") +
      card("Pending applications", stats.pending, "stat-pending") +
      card("Approved applications", stats.approved, "stat-approved") +
      card("Rejected applications", stats.rejected, "stat-rejected") +
      card("Active Polytechnic courses", stats.diploma_active, "stat-correction");
  }

  function actionLabel(action) {
    var labels = {
      admin_login: "Administrator signed in",
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

  function renderRecent(entries) {
    var el = document.getElementById("overview-recent");
    if (!entries.length) {
      el.innerHTML = '<p class="muted small">No administrator activity recorded yet.</p>';
      return;
    }
    el.innerHTML = '<div class="timeline">' + entries.map(function (e) {
      return '<div class="event">' +
        '<div class="flex between"><strong>' + ui.escapeHtml(actionLabel(e.action)) + "</strong>" +
        '<span class="when">' + ui.escapeHtml(ui.formatDate(e.created_at)) + "</span></div>" +
        '<div class="who">' + ui.escapeHtml(e.actor_email || "System") + "</div></div>";
    }).join("") + "</div>";
  }

  function load() {
    var el = document.getElementById("overview-cards");
    el.innerHTML = '<div class="stat-card"><div class="stat-label">Loading&hellip;</div></div>';
    Promise.all([
      Api.get(ADMIN.ENDPOINTS.stats),
      Api.get(ADMIN.ENDPOINTS.audit + "?limit=8")
    ]).then(function (results) {
      renderCards(results[0].stats || {});
      renderRecent(results[1].entries || []);
    }).catch(function (err) {
      el.innerHTML = '<div class="empty-state"><div class="icon">\u26A0\uFE0F</div><p>' +
        ui.escapeHtml(err.message || "Could not load the dashboard.") + "</p></div>";
      ui.error(err.message || "Could not load the dashboard.");
    });
  }

  window.ADMIN.Overview = { load: load };
})();
