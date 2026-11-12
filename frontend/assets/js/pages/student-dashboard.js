/* student-dashboard.js — profile, summary statistics and applications table */
(function () {
  "use strict";

  function renderProfile(user) {
    const host = document.getElementById("profileCard");
    if (!host) return;
    host.innerHTML = `
      <div class="profile-card">
        <div class="profile-avatar">${UI.escapeHtml(UI.initials(user.name))}</div>
        <div class="grow">
          <h3 class="mb-0">${UI.escapeHtml(user.name)}</h3>
          <p class="muted mb-0 small">${UI.escapeHtml(user.email)}</p>
          <p class="muted mb-0 small">${UI.escapeHtml(user.phone || "No phone on record")} · Student account</p>
        </div>
        <a class="btn btn-outline btn-sm" href="admission.html">+ New application</a>
      </div>`;
  }

  function renderStats(applications) {
    const counts = { total: applications.length, progress: 0, approved: 0, rejected: 0 };
    applications.forEach((a) => {
      if (["submitted", "under_review", "correction_requested"].includes(a.status)) counts.progress++;
      if (a.status === "approved") counts.approved++;
      if (a.status === "rejected") counts.rejected++;
    });
    const host = document.getElementById("statsRow");
    host.innerHTML = `
      <div class="stat stat-info"><div class="stat-value">${counts.total}</div><div class="stat-label">Total applications</div></div>
      <div class="stat stat-warning"><div class="stat-value">${counts.progress}</div><div class="stat-label">In progress</div></div>
      <div class="stat stat-success"><div class="stat-value">${counts.approved}</div><div class="stat-label">Approved</div></div>
      <div class="stat stat-danger"><div class="stat-value">${counts.rejected}</div><div class="stat-label">Rejected</div></div>`;
  }

  function renderTable(applications) {
    const host = document.getElementById("applicationsHost");
    if (!applications.length) {
      host.innerHTML = UI.emptyState({
        icon: "📝",
        title: "You have not applied yet",
        text: "Start your admission application — it only takes a few minutes and you can save it as a draft.",
        action: '<a class="btn mt-2" href="admission.html">Start your first application</a>'
      });
      return;
    }
    host.innerHTML = `
      <div class="table-wrap">
        <table class="table">
          <thead>
            <tr>
              <th>Application #</th><th>Course</th><th>Marks</th>
              <th>Status</th><th>Submitted</th><th></th>
            </tr>
          </thead>
          <tbody>${applications.map((a) => Components.applicationRow(a)).join("")}</tbody>
        </table>
      </div>`;
  }

  async function init() {
    const user = Auth.currentUser();
    if (!user) return; // main.js guard is redirecting

    renderProfile(user);
    const host = document.getElementById("applicationsHost");
    host.innerHTML = UI.skeletonRows(3);

    try {
      const res = await Api.getApplications({ scope: "mine" });
      renderStats(res.applications);
      renderTable(res.applications);
    } catch (err) {
      host.innerHTML = UI.emptyState({ icon: "⚠️", title: "Could not load applications", text: err.message });
    }
  }

  document.addEventListener("DOMContentLoaded", init);
})();
