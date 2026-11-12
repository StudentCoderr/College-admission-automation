/* admission.js — multi-section admission form with stepper + validation */
(function () {
  "use strict";

  const MAX_FILE_BYTES = 5 * 1024 * 1024;
  const ALLOWED_EXT = ["pdf", "jpg", "jpeg", "png"];
  let steps = [];
  let stepNodes = [];
  let current = 0;
  let courseCache = [];

  function validateScope(root) {
    let valid = true;
    let first = null;
    root.querySelectorAll("[data-validate]").forEach((field) => {
      const list = field.getAttribute("data-validate").split(/\s+/).filter(Boolean);
      const msg = Validation.validateField(field, list);
      Validation.setFieldError(field, msg);
      if (msg) { valid = false; if (!first) first = field; }
    });
    if (first) first.focus();
    return valid;
  }

  function showStep(index) {
    current = index;
    stepNodes.forEach((node, i) => { node.hidden = i !== index; });
    steps.forEach((node, i) => {
      node.classList.toggle("active", i === index);
      node.classList.toggle("done", i < index);
    });

    const prev = document.getElementById("prevBtn");
    const next = document.getElementById("nextBtn");
    const submit = document.getElementById("submitBtn");
    prev.disabled = index === 0;
    const last = index === steps.length - 1;
    next.classList.toggle("hidden", last);
    submit.classList.toggle("hidden", !last);

    if (last) renderSummary();
    window.scrollTo({ top: (document.getElementById("admissionForm").offsetTop - 90), behavior: "smooth" });
  }

  function collectPayload() {
    const form = document.getElementById("admissionForm");
    const val = (name) => {
      const el = form.elements[name];
      return el && el.value != null ? String(el.value).trim() : "";
    };
    const marksObtained = parseFloat(val("marksObtained")) || null;
    const marksTotal = parseFloat(val("marksTotal")) || null;
    let percentage = parseFloat(val("percentage")) || null;
    if (!percentage && marksObtained && marksTotal) {
      percentage = Math.round((marksObtained / marksTotal) * 10000) / 100;
    }
    return {
      firstName: val("firstName"), middleName: val("middleName"), lastName: val("lastName"),
      dateOfBirth: val("dateOfBirth"), gender: val("gender"),
      category: val("category"), nationality: val("nationality") || "Indian",
      email: val("email"), phone: val("phone"),
      address: val("address"), city: val("city"), state: val("state"),
      postalCode: val("postalCode"), country: val("country") || "India",
      qualifyingExam: val("qualifyingExam"), board: val("board"), school: val("school"),
      passingYear: val("passingYear"), marksObtained, marksTotal, percentage,
      courseId: val("courseId")
    };
  }

  function courseNameFromSelect() {
    const select = document.getElementById("courseId");
    const opt = select && select.selectedOptions[0];
    return opt && opt.value ? opt.textContent.trim() : "";
  }

  function renderSummary() {
    const host = document.getElementById("reviewSummary");
    if (!host) return;
    const p = collectPayload();
    const row = (k, v) => `<div class="summary-row"><span class="k">${UI.escapeHtml(k)}</span><span class="v">${UI.escapeHtml(v || "—")}</span></div>`;
    host.innerHTML =
      row("Name", [p.firstName, p.middleName, p.lastName].filter(Boolean).join(" ")) +
      row("Date of birth", p.dateOfBirth) +
      row("Gender", p.gender) +
      row("Category", (p.category || "").toUpperCase()) +
      row("Email", p.email) +
      row("Phone", p.phone) +
      row("Address", `${p.address}, ${p.city}, ${p.state} ${p.postalCode}`) +
      row("Qualifying exam", p.qualifyingExam) +
      row("Board / University", p.board) +
      row("Passing year", p.passingYear) +
      row("Marks", `${p.marksObtained || "—"} / ${p.marksTotal || "—"}`) +
      row("Percentage", p.percentage != null ? p.percentage + "%" : "—") +
      row("Preferred course", courseNameFromSelect());
  }

  async function fillCourses() {
    const select = document.getElementById("courseId");
    try {
      const { courses } = await Api.getCourses();
      courseCache = courses;
      select.innerHTML = '<option value="">Select a programme…</option>' +
        courses.map((c) => `<option value="${UI.escapeHtml(c.id)}">${UI.escapeHtml(c.name)} (${UI.escapeHtml(c.code)})</option>`).join("");
      const preselect = App.getQueryParam("course");
      if (preselect) select.value = preselect;
      renderCoursePreview();
    } catch (err) {
      select.innerHTML = '<option value="">Could not load courses — please retry</option>';
    }
  }

  function renderCoursePreview() {
    const select = document.getElementById("courseId");
    const host = document.getElementById("coursePreview");
    if (!host) return;
    const course = courseCache.find((c) => c.id === select.value);
    if (!course) { host.innerHTML = ""; return; }
    host.innerHTML = Components.courseCard(course);
  }

  function attachFileInputs() {
    document.querySelectorAll("[data-file-input]").forEach((input) => {
      const wrapper = input.closest(".form-group");
      const listHost = wrapper.querySelector(".file-list");
      const errorEl = wrapper.querySelector(".form-error");

      input.addEventListener("change", () => {
        const files = Array.from(input.files || []);
        let error = "";
        files.forEach((f) => {
          const ext = f.name.split(".").pop().toLowerCase();
          if (!ALLOWED_EXT.includes(ext)) error = "Only PDF, JPG and PNG files are allowed.";
          else if (f.size > MAX_FILE_BYTES) error = "Each file must be 5 MB or smaller.";
        });
        if (error) {
          input.value = "";
          if (errorEl) { errorEl.textContent = error; errorEl.style.display = "block"; }
          wrapper.classList.add("is-invalid");
          listHost.innerHTML = "";
          return;
        }
        if (errorEl) { errorEl.textContent = ""; errorEl.style.display = "none"; }
        wrapper.classList.remove("is-invalid");
        listHost.innerHTML = files.map((f) => `
          <li><span>📎 ${UI.escapeHtml(f.name)}</span>
          <span class="small muted">${(f.size / 1024).toFixed(0)} KB</span></li>`).join("");
      });
    });
  }

  async function submitApplication(ev) {
    ev.preventDefault();
    const alertEl = document.getElementById("formAlert");
    UI.hideAlert(alertEl);

    // Validate every step.
    for (let i = 0; i < stepNodes.length - 1; i++) {
      if (!validateScope(stepNodes[i])) {
        showStep(i);
        UI.showAlert(alertEl, "Please complete the highlighted fields.", "error");
        return;
      }
    }
    const marksCard = document.getElementById("docMarks");
    if (!marksCard.files || !marksCard.files.length) {
      showStep(4);
      UI.toast("Please upload your marks card before submitting.", "error");
      return;
    }

    const submit = document.getElementById("submitBtn");
    const payload = collectPayload();
    UI.setLoading(submit, true);
    try {
      const { application } = await Api.createApplication(payload);
      await Api.uploadDocuments(application.id);          // real mode posts files
      await Api.submitApplication(application.id);
      UI.showAlert(alertEl, `Application ${application.number} submitted successfully! Redirecting…`, "success");
      UI.toast("Application submitted.", "success");
      setTimeout(() => { window.location.href = "student_dashboard.html"; }, 1100);
    } catch (err) {
      UI.showAlert(alertEl, err.message || "Could not submit your application.", "error");
      UI.setLoading(submit, false);
    }
  }

  async function saveDraft() {
    const alertEl = document.getElementById("formAlert");
    const payload = collectPayload();
    if (!payload.email || !payload.courseId) {
      UI.showAlert(alertEl, "Add at least your email and preferred course to save a draft.", "warning");
      return;
    }
    const btn = document.getElementById("draftBtn");
    UI.setLoading(btn, true);
    try {
      const { application } = await Api.createApplication(payload);
      UI.toast(`Draft ${application.number} saved.`, "success");
      setTimeout(() => { window.location.href = "student_dashboard.html"; }, 700);
    } catch (err) {
      UI.showAlert(alertEl, err.message, "error");
      UI.setLoading(btn, false);
    }
  }

  function init() {
    const form = document.getElementById("admissionForm");
    if (!form) return;
    steps = UI.$$("#stepper .step");
    stepNodes = UI.$$(".form-step");

    Validation.bindLiveValidation(form);
    attachFileInputs();
    fillCourses();

    document.getElementById("nextBtn").addEventListener("click", () => {
      if (!validateScope(stepNodes[current])) {
        UI.toast("Please fix the highlighted fields.", "error");
        return;
      }
      if (current < stepNodes.length - 1) showStep(current + 1);
    });
    document.getElementById("prevBtn").addEventListener("click", () => {
      if (current > 0) showStep(current - 1);
    });
    document.getElementById("draftBtn").addEventListener("click", saveDraft);
    form.addEventListener("submit", submitApplication);
    form.elements["courseId"].addEventListener("change", renderCoursePreview);

    // Prefill from session where possible.
    const user = Auth.currentUser();
    if (user) {
      if (!form.elements.email.value) form.elements.email.value = user.email;
      if (form.elements.phone && !form.elements.phone.value && user.phone) form.elements.phone.value = user.phone;
    }

    showStep(0);
  }

  document.addEventListener("DOMContentLoaded", init);
})();
