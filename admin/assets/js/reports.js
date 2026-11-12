/* ==========================================================================
 * Reports: live admission statistics, applications-by-status and
 * applications-by-course breakdowns, and the administrator audit trail.
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

  function bars(containerId, items) {
    var el = document.getElementById(containerId);
    if (!items.length) {
      el.innerHTML = '<p class="muted small">No data recorded yet.</p>';
      return;
    }
    var max = 0;
    items.forEach(function (i) { if (i.value > max) max = i.value; });
    max = max || 1;
    el.innerHTML = '<div class="chart-bars">' + items.map(function (i) {
      var pct = Math.round((i.value / max) * 100);
      return '<div class="bar-row">' +
        '<div class="bar-label" title="' + ui.escapeHtml(i.label) + '">' + ui.escapeHtml(i.label) + "</div>" +
        '<div class="bar-track"><div class="bar-fill ' + (i.cls || "") +
        '" style="width:' + pct + '%"></div></div>' +
        '<div class="bar-value">' + ui.escapeHtml(i.value) + "</div></div>";
    }).join("") + "</div>";
  }

  function auditRow(e) {
    return "<tr>" +
      '<td class="muted nowrap">' + ui.escapeHtml(ui.formatDate(e.created_at)) + "</td>" +
      "<td>" + ui.escapeHtml(e.actor_email || "System") + "</td>" +
      "<td>" + ui.escapeHtml(actionLabel(e.action)) + "</td>" +
      '<td class="muted">' + ui.escapeHtml(e.details || "\u2014") + "</td></tr>";
  }

  function load() {
    document.getElementById("report-cards").innerHTML =
      '<div class="stat-card"><div class="stat-label">Loading&hellip;</div></div>';

    Promise.all([
      Api.get(ADMIN.ENDPOINTS.stats),
      Api.get(ADMIN.ENDPOINTS.courses),
      Api.get(ADMIN.ENDPOINTS.audit + "?limit=20")
    ]).then(function (results) {
      var s = results[0].stats || {};

      document.getElementById("report-cards").innerHTML =
        card("Total applications", s.total, "stat-total") +
        card("Pending", s.pending, "stat-pending") +
        card("Approved", s.approved, "stat-approved") +
        card("Rejected", s.rejected, "stat-rejected") +
        card("Registered students", s.students_total, "stat-total") +
        card("Active Polytechnic courses", s.diploma_active, "stat-correction");

      bars("report-status-bars", [
        { label: "Submitted", value: s.submitted || 0, cls: "bar-blue" },
        { label: "Under review", value: s.under_review || 0, cls: "bar-indigo" },
        { label: "Correction requested", value: s.correction_requested || 0, cls: "bar-amber" },
        { label: "Approved", value: s.approved || 0, cls: "bar-green" },
        { label: "Rejected", value: s.rejected || 0, cls: "bar-red" }
      ]);

      var courses = (results[1].courses || []).slice().sort(function (a, b) {
        return (b.application_count || 0) - (a.application_count || 0);
      });
      bars("report-course-bars", courses.map(function (c) {
        return {
          label: c.code + " \u2014 " + c.name,
          value: c.application_count || 0,
          cls: "bar-blue"
        };
      }));

      var entries = results[2].entries || [];
      document.getElementById("report-audit-body").innerHTML = entries.length
        ? entries.map(auditRow).join("")
        : '<tr class="loading-row"><td colspan="4"><div class="empty-state">' +
          "<p>No administrator activity recorded yet.</p></div></td></tr>";
    }).catch(function (err) {
      ui.error(err.message || "Could not load reports.");
    });
  }

  window.ADMIN.Reports = { load: load };
})();
