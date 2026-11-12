/* courses.js — course listing with search + department filter */
(function () {
  "use strict";

  let allCourses = [];

  function render() {
    const host = document.getElementById("courseList");
    const countEl = document.getElementById("courseCount");
    const search = (document.getElementById("courseSearch").value || "").toLowerCase().trim();
    const dept = document.getElementById("deptFilter").value;

    let list = allCourses.slice();
    if (dept) list = list.filter((c) => String(c.department || "") === dept);
    if (search) {
      list = list.filter((c) =>
        String(c.name || "").toLowerCase().includes(search) ||
        String(c.code || "").toLowerCase().includes(search) ||
        String(c.department || "").toLowerCase().includes(search));
    }

    if (countEl) countEl.textContent = `${list.length} programme${list.length === 1 ? "" : "s"}`;

    if (!list.length) {
      host.innerHTML = UI.emptyState({
        icon: "🔍",
        title: "No courses match your search",
        text: "Try a different keyword or clear the filters to see all programmes.",
        action: '<button class="btn btn-outline mt-2" type="button" id="clearFilters">Clear filters</button>'
      });
      const clear = document.getElementById("clearFilters");
      if (clear) clear.addEventListener("click", () => {
        document.getElementById("courseSearch").value = "";
        document.getElementById("deptFilter").value = "";
        render();
      });
      return;
    }

    host.innerHTML = list.map(Components.courseCard).join("");
  }

  async function init() {
    const host = document.getElementById("courseList");
    host.innerHTML = UI.loadingBlock("Loading programmes…");
    try {
      const res = await Api.getCourses();
      allCourses = res.courses || [];
      const depts = Array.from(
        new Set(allCourses.map((c) => c.department).filter(Boolean))
      ).sort();
      const deptSelect = document.getElementById("deptFilter");
      deptSelect.innerHTML = '<option value="">All departments</option>' +
        depts.map((d) => `<option value="${UI.escapeHtml(d)}">${UI.escapeHtml(d)}</option>`).join("");
      render();
    } catch (err) {
      host.innerHTML = UI.emptyState({ icon: "⚠️", title: "Could not load courses", text: err.message });
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    const search = document.getElementById("courseSearch");
    const dept = document.getElementById("deptFilter");
    if (search) search.addEventListener("input", render);
    if (dept) dept.addEventListener("change", render);
    init();
  });
})();
