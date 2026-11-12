/* status.js — public application tracking */
(function () {
  "use strict";

  function renderResult(container, app) {
    container.innerHTML = `
      <div class="card card-pad-lg mt-3">
        <div class="track-result-head">
          <div>
            <div class="small muted">Application number</div>
            <div class="track-number">${UI.escapeHtml(app.number)}</div>
          </div>
          <div>${UI.statusPill(app.status)}</div>
        </div>
        <div class="grid grid-2">
          <div>
            <div class="summary-row"><span class="k">Applicant</span><span class="v">${UI.escapeHtml(app.applicantName)}</span></div>
            <div class="summary-row"><span class="k">Course</span><span class="v">${UI.escapeHtml(app.courseName)}</span></div>
            <div class="summary-row"><span class="k">Submitted on</span><span class="v">${UI.escapeHtml(UI.formatDate(app.submittedAt))}</span></div>
            <div class="summary-row"><span class="k">Last update</span><span class="v">${UI.escapeHtml(UI.formatDate(app.updatedAt))}</span></div>
          </div>
          <div>
            <h3>Progress</h3>
            ${Components.timeline(app.history)}
          </div>
        </div>
        ${app.adminNote ? `<div class="alert alert-info mt-2"><strong>Note from admissions:</strong> ${UI.escapeHtml(app.adminNote)}</div>` : ""}
      </div>`;
  }

  function renderMyList(container, apps) {
    if (!apps.length) {
      container.innerHTML = UI.emptyState({
        icon: "🗂️", title: "No applications on this account",
        text: "Once you submit an application it will appear here.",
        action: '<a class="btn mt-2" href="admission.html">Apply now</a>'
      });
      return;
    }
    container.innerHTML = `<h2 class="mt-3">Your applications</h2><div class="grid grid-2">
      ${apps.map((a) => `
        <button type="button" class="card card-hover" data-track-id="${UI.escapeHtml(a.id)}" style="text-align:left;cursor:pointer">
          <div class="flex-between"><span class="track-number">${UI.escapeHtml(a.number || "(draft)")}</span>${UI.statusPill(a.status)}</div>
          <p class="mb-0 mt-2" style="font-weight:600">${UI.escapeHtml(a.courseName)}</p>
          <span class="small muted">Updated ${UI.escapeHtml(UI.formatDate(a.updatedAt))}</span>
        </button>`).join("")}
    </div>`;
    container.querySelectorAll("[data-track-id]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const { application } = await Api.getApplication(btn.getAttribute("data-track-id"));
        document.getElementById("statusResult").scrollIntoView({ behavior: "smooth" });
        renderResult(document.getElementById("statusResult"), application);
      });
    });
  }

  async function init() {
    const form = document.getElementById("trackForm");
    if (!form) return;
    const alertEl = document.getElementById("trackAlert");
    const resultEl = document.getElementById("statusResult");
    const myEl = document.getElementById("myApplications");
    const submit = form.querySelector('button[type="submit"]');

    Validation.bindLiveValidation(form);

    // Prefill from query string or session.
    const qNumber = App.getQueryParam("number");
    if (qNumber) form.number.value = qNumber;

    const user = Auth.currentUser();
    if (user) {
      if (!form.email.value) form.email.value = user.email;
      try {
        const res = await Api.getApplications({ scope: "mine" });
        renderMyList(myEl, res.applications);
      } catch (e) { /* ignore */ }
    }

    form.addEventListener("submit", async (ev) => {
      ev.preventDefault();
      UI.hideAlert(alertEl);
      resultEl.innerHTML = "";
      const { valid, data } = Validation.validateForm(form);
      if (!valid) { UI.showAlert(alertEl, "Enter a valid application number and email.", "error"); return; }

      UI.setLoading(submit, true);
      try {
        const { application } = await Api.trackApplication({ number: data.number, email: data.email });
        renderResult(resultEl, application);
        resultEl.scrollIntoView({ behavior: "smooth" });
      } catch (err) {
        UI.showAlert(alertEl, err.message, "error");
      } finally {
        UI.setLoading(submit, false);
      }
    });
  }

  document.addEventListener("DOMContentLoaded", init);
})();
