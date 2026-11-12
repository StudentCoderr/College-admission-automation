/* application-details.js — administrator review page */
(function () {
  "use strict";

  let applicationId = "";
  let currentApp = null;

  function docRow(doc) {
    const label = UI.DOC_LABELS[doc.type] || doc.type;
    return `<tr>
      <td>${UI.escapeHtml(label)}</td>
      <td>${UI.escapeHtml(doc.name)}</td>
      <td>${(doc.size / 1024).toFixed(0)} KB</td>
      <td>${doc.verified ? '<span class="pill pill-approved">Verified</span>' : '<span class="pill pill-neutral">Pending</span>'}</td>
      <td><button class="btn btn-sm btn-outline" data-doc="${UI.escapeHtml(doc.name)}">View</button></td>
    </tr>`;
  }

  function render(app) {
    currentApp = app;
    document.getElementById("appTitle").textContent = app.number || "(draft)";
    document.getElementById("appStatusPill").innerHTML = UI.statusPill(app.status);

    document.getElementById("personalHost").innerHTML = `
      <dl class="dl">
        <dt>Full name</dt><dd>${UI.escapeHtml(app.applicantName)}</dd>
        <dt>Date of birth</dt><dd>${UI.escapeHtml(UI.formatDate(app.dateOfBirth))}</dd>
        <dt>Gender</dt><dd>${UI.escapeHtml(app.gender)}</dd>
        <dt>Category</dt><dd>${UI.escapeHtml(app.category)}</dd>
        <dt>Nationality</dt><dd>${UI.escapeHtml(app.nationality)}</dd>
        <dt>Email</dt><dd>${UI.escapeHtml(app.email)}</dd>
        <dt>Phone</dt><dd>${UI.escapeHtml(app.phone)}</dd>
        <dt>Address</dt><dd>${UI.escapeHtml(`${app.address}, ${app.city}, ${app.state} ${app.postalCode}`)}</dd>
      </dl>`;

    document.getElementById("academicHost").innerHTML = `
      <dl class="dl">
        <dt>Qualifying exam</dt><dd>${UI.escapeHtml(app.qualifyingExam)}</dd>
        <dt>Board / University</dt><dd>${UI.escapeHtml(app.board)}</dd>
        <dt>School</dt><dd>${UI.escapeHtml(app.school)}</dd>
        <dt>Passing year</dt><dd>${UI.escapeHtml(app.passingYear)}</dd>
        <dt>Marks</dt><dd>${UI.escapeHtml(app.marksObtained)} / ${UI.escapeHtml(app.marksTotal)}</dd>
        <dt>Percentage</dt><dd>${app.percentage != null ? UI.escapeHtml(app.percentage) + "%" : "—"}</dd>
        <dt>Preferred course</dt><dd>${UI.escapeHtml(app.courseName)} (${UI.escapeHtml(app.courseCode)})</dd>
      </dl>`;

    const docHost = document.getElementById("documentsHost");
    docHost.innerHTML = (app.documents && app.documents.length)
      ? `<div class="table-wrap"><table class="table"><thead><tr><th>Type</th><th>File</th><th>Size</th><th>Status</th><th></th></tr></thead><tbody>${app.documents.map(docRow).join("")}</tbody></table></div>`
      : '<p class="muted">No documents uploaded.</p>';

    document.getElementById("historyHost").innerHTML = Components.timeline(app.history);

    const note = document.getElementById("adminNoteBox");
    if (app.adminNote) { note.hidden = false; note.textContent = "Note on file: " + app.adminNote; }
    else { note.hidden = true; }

    docHost.querySelectorAll("[data-doc]").forEach((btn) => {
      btn.addEventListener("click", () => UI.toast(`Opening ${btn.getAttribute("data-doc")} (signed URL from backend).`, "info"));
    });

    updateActionButtons(app.status);
  }

  function updateActionButtons(status) {
    const decided = status === "approved" || status === "rejected";
    document.getElementById("reviewActions").classList.toggle("hidden", decided);
  }

  async function applyDecision(status, note) {
    try {
      await Api.updateApplicationStatus(currentApp.id, status, note);
      UI.toast(`Application ${UI.statusLabel(status)}.`, "success");
      const { application } = await Api.getApplication(currentApp.id);
      render(application);
    } catch (err) {
      UI.toast(err.message || "Could not update the application.", "error");
    }
  }

  function decisionModal(status) {
    const needsNote = status === "rejected" || status === "correction_requested";
    const danger = status === "rejected";
    const labels = { under_review: "Mark under review?", approved: "Approve this application?", rejected: "Reject this application?", correction_requested: "Request a correction?" };
    UI.openModal({
      title: labels[status] || "Confirm",
      danger,
      confirmText: UI.statusLabel(status),
      body: `<p class="small muted">${status === "approved" ? "The applicant will be notified that their application is approved." : "This action is recorded in the application history."}</p>
        <div class="form-group">
          <label class="form-label" for="decisionNote">Note to applicant ${needsNote ? '<span class="req">*</span>' : ""}</label>
          <textarea class="form-control" id="decisionNote" rows="3" placeholder="${needsNote ? "Explain what is required…" : "Optional note…"}">${currentApp.adminNote ? UI.escapeHtml(currentApp.adminNote) : ""}</textarea>
          <span class="form-error" id="decisionNoteError"></span>
        </div>`,
      onConfirm: async () => {
        const noteEl = document.getElementById("decisionNote");
        const note = noteEl.value.trim();
        if (needsNote && !note) {
          document.getElementById("decisionNoteError").textContent = "A note is required for this action.";
          document.getElementById("decisionNoteError").style.display = "block";
          throw new Error("note required");
        }
        await applyDecision(status, note);
      }
    });
  }

  async function init() {
    if (!Auth.currentUser()) return;
    applicationId = App.getQueryParam("id");
    const host = document.getElementById("detailsHost");
    if (!applicationId) {
      host.innerHTML = UI.emptyState({ icon: "❓", title: "No application selected", text: "Open an application from the dashboard.", action: '<a class="btn mt-2" href="admin_dashboard.html">Back to dashboard</a>' });
      return;
    }
    host.innerHTML = UI.loadingBlock("Loading application…");
    try {
      const { application } = await Api.getApplication(applicationId);
      document.getElementById("detailsHost").innerHTML = document.getElementById("detailsTemplate").innerHTML;
      render(application);
      UI.$("#reviewActions").addEventListener("click", (e) => {
        const btn = e.target.closest("[data-decision]");
        if (btn) decisionModal(btn.getAttribute("data-decision"));
      });
    } catch (err) {
      document.getElementById("detailsHost").innerHTML = UI.emptyState({ icon: "⚠️", title: "Application not found", text: err.message, action: '<a class="btn mt-2" href="admin_dashboard.html">Back to dashboard</a>' });
    }
  }

  document.addEventListener("DOMContentLoaded", init);
})();
