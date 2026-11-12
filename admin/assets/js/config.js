/* ==========================================================================
 * Admin console configuration.
 * Overrides (in priority order):
 *   1. ?api=... query parameter
 *   2. same origin (when served from Flask at /admin-console)
 *   3. localStorage "admin_api_base" (standalone mode only)
 * ========================================================================= */
(function () {
  "use strict";

  var params = new URLSearchParams(window.location.search);
  var stored = null;
  try { stored = localStorage.getItem("admin_api_base"); } catch (e) { /* private mode */ }

  // When Flask serves the console at /admin-console, same-origin is always the
  // correct API. Ignore a stale localStorage value from an earlier standalone
  // session (for example a dead port or a different host) so it cannot break
  // the sign-in request.
  var servedByFlask = window.location.pathname.indexOf("/admin-console") === 0;
  var apiBase = params.get("api") || (!servedByFlask ? stored : "") || "";
  apiBase = apiBase.replace(/\/+$/, "");

  window.ADMIN = {
    API_BASE: apiBase,

    ENDPOINTS: {
      csrf: "/auth/csrf",
      me: "/auth/me",
      login: "/auth/login",
      logout: "/auth/logout",
      stats: "/admin/stats",
      applications: "/admin/applications",
      application: function (id) { return "/admin/applications/" + encodeURIComponent(id); },
      status: function (id) { return "/admin/applications/" + encodeURIComponent(id) + "/status"; },
      courses: "/admin/courses",
      course: function (id) { return "/admin/courses/" + encodeURIComponent(id); },
      courseToggle: function (id) { return "/admin/courses/" + encodeURIComponent(id) + "/toggle"; },
      students: "/admin/students",
      student: function (id) { return "/admin/students/" + encodeURIComponent(id); },
      studentStatus: function (id) { return "/admin/students/" + encodeURIComponent(id) + "/status"; },
      studentInvite: function (id) { return "/admin/students/" + encodeURIComponent(id) + "/invite"; },
      audit: "/admin/audit",
      profile: "/admin/profile",
      profilePassword: "/admin/profile/password",
      documentVerify: function (id) { return "/admin/documents/" + encodeURIComponent(id) + "/verify"; },
      exportCsv: "/admin/export/applications.csv"
    },

    // Status metadata used across the console.
    STATUSES: [
      { key: "draft", label: "Draft", tone: "gray" },
      { key: "submitted", label: "Submitted", tone: "blue" },
      { key: "under_review", label: "Under Review", tone: "indigo" },
      { key: "correction_requested", label: "Correction Requested", tone: "amber" },
      { key: "approved", label: "Approved", tone: "green" },
      { key: "rejected", label: "Rejected", tone: "red" }
    ],

    STATUS_META: (function () {
      var meta = {};
      window.ADMIN.STATUSES.forEach(function (s) { meta[s.key] = s; });
      return meta;
    })(),

    // Review actions available to the administrator.
    REVIEW_ACTIONS: {
      approved: { label: "Approve", tone: "green", needsNote: false },
      rejected: { label: "Reject", tone: "red", needsNote: true },
      correction_requested: { label: "Request Correction", tone: "amber", needsNote: true }
    },

    csvBaseUrl: function (filters) {
      var p = new URLSearchParams();
      if (filters.status) p.set("status", filters.status);
      if (filters.courseId) p.set("course_id", filters.courseId);
      if (filters.q) p.set("q", filters.q);
      if (filters.from) p.set("from", filters.from);
      if (filters.to) p.set("to", filters.to);
      var qs = p.toString();
      return window.ADMIN.API_BASE + window.ADMIN.ENDPOINTS.exportCsv + (qs ? "?" + qs : "");
    },

    url: function (path) {
      return window.ADMIN.API_BASE + "/api" + path;
    }
  };
})();