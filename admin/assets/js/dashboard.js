/* ==========================================================================
 * Application dashboard: summary cards, searchable / sortable / filterable
 * table, and pagination. All data comes from the real /api endpoints.
 * ========================================================================= */
(function () {
  "use strict";

  var ui = window.ADMIN.UI;
  var Api = window.ADMIN.Api;

  var state = {
    q: "",
    status: "",
    courseId: "",
    from: "",
    to: "",
    page: 1,
    perPage: 10,
    sort: "created_at",
    order: "desc"
  };

  var coursesCache = [];
  var currentApps = [];
  var totalCount = 0;
  var totalPages = 0;
  var activeCourseTabLoaded = false;

  var COLUMNS = [
    { key: "application_number", label: "No.", sortable: true },
    { key: "first_name", label: "Applicant", sortable: true },
    { key: "email", label: "Email", sortable: false },
    { key: "courseName", label: "Course", sortable: false },
    { key: "percentage", label: "Marks %", sortable: true },
    { key: "status", label: "Status", sortable: true },
    { key: "submitted_at", label: "Submitted", sortable: true },
    { key: "actions", label: "Actions", sortable: false }
  ];

  function queryString() {
    var p = new URLSearchParams();
    if (state.q) p.set("q", state.q);
    if (state.status) p.set("status", state.status);
    if (state.courseId) p.set("course_id", state.courseId);
    if (state.from) p.set("from", state.from);
    if (state.to) p.set("to", state.to);
    p.set("page", state.page);
    p.set("per_page", state.perPage);
    p.set("sort", state.sort);
    p.set("order", state.order);
    return p.toString();
  }

  // ---------- Stats cards ------------------------------------------------
  function fetchStats() {
    return Api.get(ADMIN.ENDPOINTS.stats).then(function (body) { return body.stats; });
  }

  function renderCards(stats, activeStatus) {
    var cards = [
      { key: "total", label: "Total Applications", value: stats.total, cls: "stat-total" },
      { key: "pending", label: "Pending Review", value: stats.pending, cls: "stat-pending" },
      { key: "approved", label: "Approved", value: stats.approved, cls: "stat-approved" },
      { key: "rejected", label: "Rejected", value: stats.rejected, cls: "stat-rejected" },
      { key: "correction_requested", label: "Correction Requested", value: stats.correction_requested, cls: "stat-correction" }
    ];
    var el = document.getElementById("stats-grid");
    el.innerHTML = cards.map(function (c) {
      var active = activeStatus === c.key || (c.key === "total" && !activeStatus);
      return '<div class="stat-card ' + c.cls + (active ? " active-card" : "") +
        '" data-status="' + (c.key === "total" ? "" : c.key) + '">' +
        '<div class="stat-label">' + ui.escapeHtml(c.label) + "</div>" +
        '<div class="stat-value">' + ui.escapeHtml(c.value == null ? 0 : c.value) + "</div></div>";
    }).join("");
    el.querySelectorAll(".stat-card").forEach(function (card) {
      card.addEventListener("click", function () {
        var status = card.getAttribute("data-status");
        state.status = status;
        state.page = 1;
        document.getElementById("filter-status").value = status;
        loadPage();
      });
    });
  }

  // ---------- Courses (for the filter) ------------------------------------
  function fetchCourses() {
    return Api.get(ADMIN.ENDPOINTS.courses).then(function (body) { return body.courses; });
  }

  function renderCourseFilter() {
    var select = document.getElementById("filter-course");
    var html = '<option value="">All courses</option>';
    coursesCache.forEach(function (c) {
      html += '<option value="' + ui.escapeHtml(c.id) + '">' +
        ui.escapeHtml(c.code + " \u2014 " + c.name) + "</option>";
    });
    select.innerHTML = html;
    select.value = state.courseId;
  }

  // ---------- Table --------------------------------------------------------
  function renderHeaders() {
    var row = COLUMNS.map(function (col) {
      if (!col.sortable) return "<th>" + ui.escapeHtml(col.label) + "</th>";
      var arrow = "";
      if (state.sort === col.key) {
        arrow = state.order === "asc" ? "\u2191" : "\u2193";
      }
      return '<th class="sortable" data-sort="' + col.key + '">' +
        ui.escapeHtml(col.label) + ' <span class="sort-arrow">' + arrow + "</span></th>";
    }).join("");
    var thead = document.querySelector("#applications-table thead");
    if (!thead) return;
    thead.innerHTML = "<tr>" + row + "</tr>";
    thead.querySelectorAll("th.sortable").forEach(function (th) {
      th.addEventListener("click", function () {
        var key = th.getAttribute("data-sort");
        if (state.sort === key) {
          state.order = state.order === "asc" ? "desc" : "asc";
        } else {
          state.sort = key;
          state.order = "desc";
        }
        state.page = 1;
        loadPage();
      });
    });
  }

  function findCourseName(app) {
    if (app.courseName) return app.courseName;
    if (app.course && app.course.name) return app.course.name;
    return "\u2014";
  }

  function renderRows(apps) {
    var tbody = document.querySelector("#applications-table tbody");
    if (!apps.length) {
      tbody.innerHTML = '<tr class="loading-row"><td colspan="99">' +
        '<div class="empty-state"><div class="icon">\U0001F50D</div>' +
        "<p>No applications match the current filters.</p></div></td></tr>";
      return;
    }
    tbody.innerHTML = apps.map(function (a) {
      var applicant = (a.first_name + " " + (a.last_name || "")).trim();
      var percent = a.percentage != null ? a.percentage + "%" : "\u2014";
      return "<tr>" +
        '<td class="app-no">' + ui.escapeHtml(a.application_number || "(draft)") + "</td>" +
        '<td class="applicant"><strong>' + ui.escapeHtml(applicant) + "</strong>" +
        '<span>' + ui.escapeHtml(a.gender || "") + "</span></td>" +
        "<td>" + ui.escapeHtml(a.email || "\u2014") + "</td>" +
        "<td>" + ui.escapeHtml(findCourseName(a)) + "</td>" +
        "<td>" + ui.escapeHtml(percent) + "</td>" +
        "<td>" + ui.badge(a.status) + "</td>" +
        "<td class='muted'>" + ui.escapeHtml(ui.formatDate(a.submitted_at || a.created_at)) + "</td>" +
        '<td class="actions-cell"><button class="btn-secondary btn-sm btn-view" data-id="' +
        ui.escapeHtml(a.id) + '">View</button></td>' +
        "</tr>";
    }).join("");

    tbody.querySelectorAll(".btn-view").forEach(function (btn) {
      btn.addEventListener("click", function () {
        window.ADMIN.Detail.open(btn.getAttribute("data-id"));
      });
    });
  }

  // ---------- Pagination ---------------------------------------------------
  function renderPagination() {
    var meta = document.getElementById("page-meta");
    var controls = document.getElementById("page-controls");
    var start = totalCount === 0 ? 0 : (state.page - 1) * state.perPage + 1;
    var end = Math.min(state.page * state.perPage, totalCount);
    meta.textContent = "Showing " + start + "\u2013" + end + " of " + totalCount + " applications";

    var pages = [];
    pages.push('<button id="page-prev" ' + (state.page <= 1 ? "disabled" : "") + ">&#9664; Prev</button>");
    var windowPages = pageWindow(totalPages, state.page);
    windowPages.forEach(function (p) {
      if (p === "…") {
        pages.push('<span class="current muted">\u2026</span>');
      } else {
        pages.push('<button class="page-num ' + (p === state.page ? "btn-primary" : "btn-secondary") +
          '" data-page="' + p + '">' + p + "</button>");
      }
    });
    pages.push('<button id="page-next" ' + (state.page >= totalPages ? "disabled" : "") + ">Next &#9654;</button>");
    controls.innerHTML = pages.join("");

    controls.querySelectorAll(".page-num").forEach(function (b) {
      b.addEventListener("click", function () {
        state.page = parseInt(b.getAttribute("data-page"), 10);
        loadPage();
      });
    });
    var prev = document.getElementById("page-prev");
    var next = document.getElementById("page-next");
    if (prev) prev.addEventListener("click", function () { if (state.page > 1) { state.page -= 1; loadPage(); } });
    if (next) next.addEventListener("click", function () { if (state.page < totalPages) { state.page += 1; loadPage(); } });
  }

  function pageWindow(total, current) {
    if (total <= 7) {
      var all = [];
      for (var i = 1; i <= total; i++) all.push(i);
      return all;
    }
    var pages = [1];
    var start = Math.max(2, current - 1);
    var end = Math.min(total - 1, current + 1);
    if (start > 2) pages.push("…");
    for (var p = start; p <= end; p++) pages.push(p);
    if (end < total - 1) pages.push("…");
    pages.push(total);
    return pages;
  }

  // ---------- Loading -------------------------------------------------------
  function loadPage() {
    var tbody = document.querySelector("#applications-table tbody");
    ui.setLoading(tbody ? tbody.id : "", true, "Loading applications\u2026");
    document.getElementById("export-link").setAttribute("href", ADMIN.csvBaseUrl({
      status: state.status, courseId: state.courseId, q: state.q,
      from: state.from, to: state.to
    }));

    Api.get(ADMIN.ENDPOINTS.applications + "?" + queryString())
      .then(function (body) {
        currentApps = body.applications || [];
        totalCount = body.total || 0;
        totalPages = body.pages || Math.ceil(totalCount / state.perPage) || 1;
        if (state.page > totalPages && totalPages > 0) {
          state.page = totalPages;
          return loadPage();
        }
        renderHeaders();
        renderRows(currentApps);
        renderPagination();
        document.getElementById("table-status").classList.add("hidden");
        document.getElementById("table-wrap").classList.remove("hidden");
      })
      .catch(function (err) {
        ui.setLoading(tbody ? tbody.id : "", false);
        document.getElementById("table-wrap").classList.add("hidden");
        var box = document.getElementById("table-status");
        box.classList.remove("hidden");
        box.innerHTML = '<div class="empty-state"><div class="icon">\u26A0\uFE0F</div>' +
          "<p>" + ui.escapeHtml(err.message || "Could not load applications.") + "</p></div>";
      });
  }

  // ---------- Filters -------------------------------------------------------
  function bindFilters() {
    var search = document.getElementById("filter-search");
    search.addEventListener("input", ui.debounce(function () {
      state.q = search.value.trim();
      state.page = 1;
      loadPage();
    }, 450));

    document.getElementById("filter-status").addEventListener("change", function (e) {
      state.status = e.target.value;
      state.page = 1;
      loadPage();
    });
    document.getElementById("filter-course").addEventListener("change", function (e) {
      state.courseId = e.target.value;
      state.page = 1;
      loadPage();
    });
    document.getElementById("filter-from").addEventListener("change", function (e) {
      state.from = e.target.value;
      state.page = 1;
      loadPage();
    });
    document.getElementById("filter-to").addEventListener("change", function (e) {
      state.to = e.target.value;
      state.page = 1;
      loadPage();
    });
    document.getElementById("filter-per-page").addEventListener("change", function (e) {
      state.perPage = parseInt(e.target.value, 10) || 10;
      state.page = 1;
      loadPage();
    });
    document.getElementById("filter-reset").addEventListener("click", function () {
      state.q = ""; state.status = ""; state.courseId = "";
      state.from = ""; state.to = ""; state.page = 1;
      search.value = "";
      document.getElementById("filter-status").value = "";
      document.getElementById("filter-course").value = "";
      document.getElementById("filter-from").value = "";
      document.getElementById("filter-to").value = "";
      loadPage();
    });
  }

  // ---------- Boot ----------------------------------------------------------
  function init(preserveStatus) {
    bindFilters();
    loadCoursesAndStats(preserveStatus);
  }

  function loadCoursesAndStats(statusFilter) {
    Promise.all([fetchStats(), fetchCourses()])
      .then(function (results) {
        coursesCache = results[1];
        renderCourseFilter();
        renderCards(results[0], statusFilter || "");
        if (statusFilter) {
          state.status = statusFilter;
          document.getElementById("filter-status").value = statusFilter;
        }
        loadPage();
      })
      .catch(function (err) {
        ui.error(err.message || "Could not load dashboard data.");
        document.getElementById("stats-grid").innerHTML =
          '<div class="empty-state"><p>' + ui.escapeHtml(err.message || "Could not load statistics.") + "</p></div>";
      });
  }

  function refreshStats() {
    fetchStats().then(function (stats) {
      renderCards(stats, state.status);
    }).catch(function () { /* non-fatal */ });
  }

  window.ADMIN.Dashboard = {
    init: init,
    refreshStats: refreshStats,
    refreshCourses: function () {
      fetchCourses().then(function (rows) {
        coursesCache = rows;
        renderCourseFilter();
      }).catch(function () { /* non-fatal */ });
    },
    refresh: function () { loadPage(); refreshStats(); }
  };
})();