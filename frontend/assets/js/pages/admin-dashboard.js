/* admin-dashboard.js — statistics, bar chart and review table */
(function () {
  "use strict";

  let allApplications = [];

  function renderStats(stats) {
    const host = document.getElementById("statsRow");
    host.innerHTML = `
      <div class="stat stat-info"><div class="stat-value">${stats.total}</div><div class="stat-label">Total applications</div><div class="stat-foot">All submissions</div></div>
      <div class="stat stat-warning"><div class="stat-value">${stats.pending}</div><div class="stat-label">Pending review</div><div class="stat-foot">Submitted + under review</div></div>
      <div class="stat stat-success"><div class="stat-value">${stats.approved}</div><div class="stat-label">Approved</div><div class="stat-foot">Offers issued</div></div>
      <div class="stat stat-danger"><div class="stat-value">${stats.rejected}</div><div class="stat-label">Rejected</div><div class="stat-foot">Did not qualify</div></div>`;
  }

  function renderChart(stats) {
    const host = document.getElementById("statusChart");
    const rows = [
      { label: "Draft", value: stats.draft, color: "#94a3b8" },
      { label: "Submitted", value: stats.submitted, color: "#3b82f6" },
      { label: "Under review", value: stats.under_review, color: "#f59e0b" },
      { label: "Corrections", value: stats.correction_requested, color: "#fb923c" },
      { label: "Approved", value: stats.approved, color: "#16a34a" },
      { label: "Rejected", value: stats.rejected, color: "#dc2626" }
    ];
    const max = Math.max(1, ...rows.map((r) => r.value));
    host.innerHTML = rows.map((r) => `
      <div class="bar-col">
        <span class="bar-value">${r.value}</span>
        <div class="bar" style="height:${Math.max(4, (r.value / max) * 150)}px;background:${r.color}"></div>
        <span class="bar-label">${r.label}</span>
      </div>`).join("");
  }

  function renderTable() {
    const host = document.getElementById("applicationsHost");
    const search = (document.getElementById("adminSearch").value || "").toLowerCase().trim();
    const status = document.getElementById("statusFilter").value;

    let list = allApplications.slice();
    if (status) list = list.filter((a) => a.status === status);
    if (search) {
      list = list.filter((a) =>
        (a.number || "").toLowerCase().includes(search) ||
        (a.applicantName || "").toLowerCase().includes(search) ||
        (a.email || "").toLowerCase().includes(search));
    }
    document.getElementById("resultCount").textContent = `${list.length} application(s)`;

    if (!list.length) {
      host.innerHTML = UI.emptyState({
        icon: "🔍", title: "No applications found",
        text: "Adjust the search text or status filter to see more results."
      });
      return;
    }
    host.innerHTML = `
      <div class="table-wrap">
        <table class="table">
          <thead><tr>
            <th>Application #</th><th>Applicant</th><th>Course</th><th>Marks</th><th>Status</th><th>Submitted</th><th></th>
          </tr></thead>
          <tbody>${list.map((a) => Components.applicationRow(a, { admin: true })).join("")}</tbody>
        </table>
      </div>`;
  }

  async function init() {
    if (!Auth.currentUser()) return;
    const host = document.getElementById("applicationsHost");
    host.innerHTML = UI.skeletonRows(4);

    try {
      const [statsRes, appsRes] = await Promise.all([
        Api.getAdminStats(),
        Api.getApplications({ scope: "all" })
      ]);
      renderStats(statsRes.stats);
      renderChart(statsRes.stats);
      allApplications = appsRes.applications;
      renderTable();
    } catch (err) {
      host.innerHTML = UI.emptyState({ icon: "⚠️", title: "Could not load data", text: err.message });
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    const search = document.getElementById("adminSearch");
    const status = document.getElementById("statusFilter");
    if (search) search.addEventListener("input", renderTable);
    if (status) status.addEventListener("change", renderTable);

    const exportBtn = document.getElementById("exportBtn");
    if (exportBtn) {
      exportBtn.addEventListener("click", () => {
        if (window.APP_CONFIG.USE_SAMPLE_DATA) {
          UI.toast("CSV export is provided by the Flask backend (/admin/export/applications.csv).", "info", 6000);
        } else {
          window.location.href = window.APP_CONFIG.API_BASE_URL + "/admin/export/applications.csv";
        }
      });
    }
    init();
  });
})();
