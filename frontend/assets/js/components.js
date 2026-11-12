/* =========================================================================
   components.js — reusable HTML renderers shared by pages.
   ========================================================================= */
window.Components = (function () {
  "use strict";
  const e = UI.escapeHtml;

  function courseCard(course) {
    course = course || {};
    // The Flask API calls these duration_years / seats_total / tuition_fee /
    // program_type, while the sample data uses duration / seats / fees /
    // department. Accept both so a course never renders blank.
    const seats = course.seats != null ? course.seats : course.seats_total;
    const filled = course.filled != null ? course.filled : 0;
    const pct = seats ? Math.round((filled / seats) * 100) : 0;
    const level = pct >= 90 ? "danger" : pct >= 70 ? "warn" : "";
    const department = course.department ||
      (course.program_type === "diploma" ? "Diploma / Polytechnic" : "Degree");
    const duration = course.duration != null ? course.duration : course.duration_years;
    const fees = course.fees != null ? course.fees : course.tuition_fee;
    const eligibility = course.eligibility || "Contact the admissions office.";
    return `
      <article class="card card-hover course-card">
        <div class="course-top">
          <span class="badge">${e(course.code)}</span>
          <span class="small muted">${e(department)}</span>
        </div>
        <h3>${e(course.name)}</h3>
        <p class="course-desc">${e(course.description)}</p>
        <ul class="course-meta">
          <li><span>Duration</span><span>${e(duration)} year(s)</span></li>
          <li><span>Eligibility</span><span title="${e(eligibility)}">${e(eligibility.length > 38 ? eligibility.slice(0, 38) + "…" : eligibility)}</span></li>
          <li><span>Annual fees</span><span>${UI.formatCurrency(fees)}</span></li>
          <li><span>Seats</span><span>${filled}/${seats}</span></li>
        </ul>
        <div class="progress ${level}" aria-label="Seats filled"><span style="width:${pct}%"></span></div>
        <div class="flex-between mt-2">
          <span class="small muted">${pct}% filled</span>
          <a class="btn btn-sm" href="admission.html?course=${encodeURIComponent(course.id)}">Apply</a>
        </div>
      </article>`;
  }

  function timeline(history) {
    const order = ["draft", "submitted", "under_review", "approved"];
    const items = (history || []).slice();
    if (!items.length) return '<p class="muted">No activity yet.</p>';
    const last = items[items.length - 1];
    return `<ul class="timeline">${items.map((h) => {
      const isCurrent = h === last;
      const cls = h.status === "rejected" ? "done" : isCurrent ? "current" : "done";
      return `<li class="${cls}">
        <div class="t-title">${e(UI.statusLabel(h.status))}</div>
        ${h.note ? `<div class="small">${e(h.note)}</div>` : ""}
        <div class="t-time">${e(UI.formatDateTime(h.at))}</div>
      </li>`;
    }).join("")}</ul>`;
  }

  function applicationRow(app, { admin = false } = {}) {
    const course = app.courseName || "—";
    return `<tr>
      <td><span class="track-number">${e(app.number || "(draft)")}</span></td>
      ${admin ? `<td>${e(app.applicantName)}<div class="small muted">${e(app.email)}</div></td>` : ""}
      <td>${e(course)}</td>
      <td>${app.percentage != null ? e(app.percentage) + "%" : "—"}</td>
      <td>${UI.statusPill(app.status)}</td>
      <td>${e(UI.formatDate(app.submittedAt || app.updatedAt))}</td>
      <td><div class="row-actions">
        <a class="btn btn-sm btn-outline" href="application_details.html?id=${encodeURIComponent(app.id)}">Review</a>
      </div></td>
    </tr>`;
  }

  return { courseCard, timeline, applicationRow };
})();
