/* home.js — homepage: featured courses + announcements */
(function () {
  "use strict";

  function announcementItem(a) {
    const d = new Date(a.date);
    const day = isNaN(d.getTime()) ? "--" : String(d.getDate()).padStart(2, "0");
    const mon = isNaN(d.getTime()) ? "" : d.toLocaleString("en-US", { month: "short" });
    return `
      <div class="card announcement mb-2">
        <div class="date-chip"><div class="d">${day}</div><div class="m">${mon}</div></div>
        <div class="grow">
          <div class="flex-between flex-wrap">
            <h3 style="margin:0">${UI.escapeHtml(a.title)}</h3>
            <span class="badge">${UI.escapeHtml(a.tag)}</span>
          </div>
          <p class="small muted mb-0 mt-2">${UI.escapeHtml(a.body)}</p>
        </div>
      </div>`;
  }

  async function init() {
    const coursesHost = document.getElementById("featuredCourses");
    const annHost = document.getElementById("announcementList");
    const statsHost = document.getElementById("heroStats");
    const aboutText = document.getElementById("aboutText");

    // Static, presentational college content (not from the database).
    if (statsHost) {
      statsHost.innerHTML = SampleData.college.stats
        .map((s) => `<div><div class="s-value">${UI.escapeHtml(s.value)}</div><div class="s-label">${UI.escapeHtml(s.label)}</div></div>`)
        .join("");
    }
    if (aboutText) aboutText.textContent = SampleData.college.about;

    if (coursesHost) coursesHost.innerHTML = UI.loadingBlock("Loading courses…");
    if (annHost) annHost.innerHTML = UI.loadingBlock("Loading announcements…");

    try {
      const [coursesRes, annRes] = await Promise.all([Api.getCourses(), Api.getAnnouncements()]);
      if (coursesHost) {
        coursesHost.innerHTML = coursesRes.courses.slice(0, 3).map(Components.courseCard).join("");
      }
      if (annHost) {
        annHost.innerHTML = annRes.announcements.map(announcementItem).join("");
      }
    } catch (err) {
      const message = UI.emptyState({ icon: "⚠️", title: "Could not load content", text: err.message });
      if (coursesHost) coursesHost.innerHTML = message;
      if (annHost) annHost.innerHTML = message;
    }
  }

  document.addEventListener("DOMContentLoaded", init);
})();
