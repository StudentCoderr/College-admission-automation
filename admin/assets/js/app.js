/* ==========================================================================
 * Boot script: session guard, navigation tabs, and module wiring.
 * ========================================================================= */
(function () {
  "use strict";

  var ui = window.ADMIN.UI;

  var TITLES = {
    "panel-overview": "Dashboard",
    "panel-students": "Students",
    "panel-applications": "Applications",
    "panel-courses": "Courses",
    "panel-reports": "Reports",
    "panel-profile": "Admin Profile"
  };

  // Panels are loaded lazily the first time they are opened.
  var LOADERS = {
    "panel-courses": function () { window.ADMIN.Courses.load(); },
    "panel-students": function () { window.ADMIN.Students.load(); },
    "panel-reports": function () { window.ADMIN.Reports.load(); },
    "panel-profile": function () { window.ADMIN.Profile.load(); }
  };

  function activateTab(target) {
    if (!target) return;
    var link = document.querySelector('.sidebar nav a[data-tab="' + target + '"]');
    if (!link) return;
    document.querySelectorAll(".sidebar nav a").forEach(function (l) {
      l.classList.toggle("active", l === link);
    });
    document.querySelectorAll(".tab-panel").forEach(function (p) {
      p.classList.toggle("active", p.id === target);
    });
    var title = document.getElementById("page-title");
    if (title && TITLES[target]) title.textContent = TITLES[target];

    if (!link.getAttribute("data-loaded") && LOADERS[target]) {
      link.setAttribute("data-loaded", "1");
      LOADERS[target]();
    }
  }

  function initTabs() {
    var addCourse = document.getElementById("add-course-button");
    if (addCourse) {
      addCourse.addEventListener("click", function () { window.ADMIN.Courses.openForm(null); });
    }
    document.querySelectorAll(".sidebar nav a").forEach(function (link) {
      link.addEventListener("click", function (e) {
        e.preventDefault();
        activateTab(link.getAttribute("data-tab"));
      });
    });
    document.querySelectorAll("[data-goto]").forEach(function (btn) {
      btn.addEventListener("click", function () { activateTab(btn.getAttribute("data-goto")); });
    });
  }

  function setWho(user) {
    var who = document.getElementById("topbar-who");
    if (!who) return;
    var initials = (user.name || user.full_name || "A")
      .split(/\s+/).map(function (w) { return w.charAt(0); }).slice(0, 2).join("").toUpperCase();
    who.innerHTML = '<div class="avatar">' + ui.escapeHtml(initials || "A") + "</div>" +
      "<div class='who'><strong>" + ui.escapeHtml(user.name || user.full_name) + "</strong>" +
      "<span>Administrator</span></div>";
  }

  function boot() {
    window.ADMIN.Detail.wireClose();
    window.ADMIN.Auth.initLogout();
    initTabs();

    window.ADMIN.Auth.guardDashboard().then(function (user) {
      if (!user) return;
      setWho(user);
      window.ADMIN.Dashboard.init();
      window.ADMIN.Overview.load();
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();