/* ==========================================================================
 * Course management: list, create, edit, activate / deactivate, delete.
 * ========================================================================= */
(function () {
  "use strict";

  var ui = window.ADMIN.UI;
  var Api = window.ADMIN.Api;

  var courses = [];

  function load() {
    var tbody = document.getElementById("courses-body");
    ui.setLoading(tbody.id, true, "Loading courses\u2026");
    Api.get(ADMIN.ENDPOINTS.courses)
      .then(function (body) {
        courses = body.courses || [];
        render();
      })
      .catch(function (err) {
        ui.setLoading(tbody.id, false);
        ui.error(err.message || "Could not load courses.");
      });
  }

  function render() {
    var tbody = document.getElementById("courses-body");
    if (!courses.length) {
      tbody.innerHTML = '<tr class="loading-row"><td colspan="99">' +
        '<div class="empty-state"><p>No courses yet. Add one to get started.</p></div></td></tr>';
      return;
    }
    tbody.innerHTML = courses.map(function (c) {
      var badge = c.is_active
        ? '<span class="badge badge-green">Active</span>'
        : '<span class="badge badge-gray">Inactive</span>';
      var type = (c.program_type === "diploma")
        ? '<span class="badge badge-blue">Diploma</span>'
        : '<span class="badge badge-gray">Degree</span>';
      var fee = (c.tuition_fee || c.tuition_fee === 0)
        ? ("&#8377;" + Number(c.tuition_fee).toLocaleString())
        : "\u2014";
      var apps = (c.application_count || c.application_count === 0) ? c.application_count : "\u2014";
      var canDelete = !(c.application_count > 0);
      return "<tr>" +
        "<td><strong>" + ui.escapeHtml(c.code) + "</strong></td>" +
        "<td>" + ui.escapeHtml(c.name) +
          (c.eligibility ? '<div class="muted small">' + ui.escapeHtml(c.eligibility) + "</div>" : "") +
          '<div class="muted small">Eligible for: ' +
          (c.eligible_qualifications && c.eligible_qualifications.length
            ? c.eligible_qualifications.map(function (q) {
                return QUAL_LABELS[String(q).toLowerCase()] || q;
              }).join(", ")
            : "All qualifications") +
          "</div></td>" +
        "<td>" + type + "</td>" +
        "<td>" + fee + "</td>" +
        "<td>" + ui.escapeHtml(c.duration_years) + " yr</td>" +
        "<td>" + ui.escapeHtml(c.seats_total) + "</td>" +
        "<td>" + ui.escapeHtml(apps) + "</td>" +
        "<td>" + badge + "</td>" +
        '<td class="actions-cell nowrap">' +
        '<button class="btn-secondary btn-sm btn-edit" data-id="' + ui.escapeHtml(c.id) + '">Edit</button> ' +
        '<button class="btn-ghost btn-sm btn-toggle" data-id="' + ui.escapeHtml(c.id) +
        '" data-active="' + (c.is_active ? "1" : "0") + '">' +
        (c.is_active ? "Deactivate" : "Activate") + "</button> " +
        '<button class="btn-danger btn-sm btn-delete" data-id="' + ui.escapeHtml(c.id) + '"' +
        (canDelete ? "" : ' disabled title="This course has applications. Deactivate it instead."') +
        ">Delete</button>" +
        "</td></tr>";
    }).join("");

    tbody.querySelectorAll(".btn-edit").forEach(function (btn) {
      btn.addEventListener("click", function () {
        openForm(courses.find(function (c) { return c.id === btn.getAttribute("data-id"); }));
      });
    });
    tbody.querySelectorAll(".btn-toggle").forEach(function (btn) {
      btn.addEventListener("click", function () { toggle(btn); });
    });
    tbody.querySelectorAll(".btn-delete").forEach(function (btn) {
      btn.addEventListener("click", function () { remove(btn); });
    });
  }

  // ---------- Toggle ---------------------------------------------------------
  function toggle(btn) {
    var course = courses.find(function (c) { return c.id === btn.getAttribute("data-id"); });
    var activating = !course.is_active;
    ui.confirm({
      title: activating ? "Activate course" : "Deactivate course",
      message: "Are you sure you want to " + (activating ? "activate" : "deactivate") +
        " \u201c" + course.code + " \u2014 " + course.name + "\u201d?" +
        (activating ? "" : " Inactive courses are hidden from students."),
      confirmText: activating ? "Activate" : "Deactivate"
    }).then(function (result) {
      if (!result) return;
      Api.post(ADMIN.ENDPOINTS.courseToggle(course.id), {})
        .then(function () {
          ui.success(activating ? "Course activated." : "Course deactivated.");
          load();
        })
        .catch(function (err) {
          ui.error(err.message || "Could not update the course.");
        });
    });
  }

  // ---------- Delete ---------------------------------------------------------
  function remove(btn) {
    var course = courses.find(function (c) { return c.id === btn.getAttribute("data-id"); });
    if (!course) return;
    ui.confirm({
      title: "Delete course",
      message: "Permanently delete \u201c" + course.code + " \u2014 " + course.name +
        "\u201d? This cannot be undone.",
      confirmText: "Delete",
      danger: true
    }).then(function (result) {
      if (!result) return;
      Api.request(ADMIN.ENDPOINTS.course(course.id), { method: "DELETE" })
        .then(function () {
          ui.success("Course deleted.");
          load();
          if (window.ADMIN.Dashboard && window.ADMIN.Dashboard.refreshCourses) {
            window.ADMIN.Dashboard.refreshCourses();
          }
        })
        .catch(function (err) {
          ui.error(err.message || "Could not delete the course.");
        });
    });
  }

  // ---------- Create / edit modal --------------------------------------------
  var QUAL_LABELS = { sslc: "SSLC", puc: "PUC", iti: "ITI" };

  function qualCheckboxes(course) {
    var current = {};
    (course && course.eligible_qualifications || []).forEach(function (q) { current[String(q).toLowerCase()] = true; });
    return Object.keys(QUAL_LABELS).map(function (key) {
      return '<label class="checkbox-inline"><input type="checkbox" name="eligible-qual" value="' + key + '"' +
        (current[key] ? " checked" : "") + "> " + QUAL_LABELS[key] + "</label>";
    }).join("");
  }

  function openForm(course) {
    var editing = !!course;
    var isDiploma = course && course.program_type === "diploma";
    var bodyHtml =
      '<div class="form-grid">' +
      '<div class="form-field" id="f-code"><label>Course code *</label>' +
      '<input type="text" id="course-code" maxlength="20" value="' + ui.escapeHtml(course ? course.code : "") +
      '" placeholder="e.g. DIP-CSE"><div class="field-error hidden"></div></div>' +
      '<div class="form-field" id="f-program_type"><label>Programme type *</label>' +
      '<select id="course-type">' +
      '<option value="degree"' + (isDiploma ? "" : " selected") + '>Degree</option>' +
      '<option value="diploma"' + (isDiploma ? " selected" : "") + '>Diploma / Polytechnic</option>' +
      '</select><div class="field-error hidden"></div></div>' +
      '<div class="form-field" id="f-duration"><label>Duration (years) *</label>' +
      '<input type="number" id="course-duration" min="1" max="10" value="' +
      ui.escapeHtml(course ? course.duration_years : 3) + '"><div class="field-error hidden"></div></div>' +
      '<div class="form-field" id="f-seats"><label>Seats *</label>' +
      '<input type="number" id="course-seats" min="1" max="2000" value="' +
      ui.escapeHtml(course ? course.seats_total : 60) + '"><div class="field-error hidden"></div></div>' +
      '<div class="form-field" id="f-tuition_fee"><label>Annual tuition fee</label>' +
      '<input type="number" step="0.01" min="0" id="course-fee" value="' +
      ui.escapeHtml(course && course.tuition_fee !== null && course.tuition_fee !== undefined ? course.tuition_fee : "") +
      '" placeholder="e.g. 25000"><div class="field-error hidden"></div></div>' +
      '<div class="form-field full" id="f-name"><label>Course name *</label>' +
      '<input type="text" id="course-name" maxlength="150" value="' + ui.escapeHtml(course ? course.name : "") +
      '" placeholder="e.g. Diploma in Computer Science and Engineering"><div class="field-error hidden"></div></div>' +
      '<div class="form-field full" id="f-eligibility"><label>Eligibility</label>' +
      '<input type="text" id="course-eligibility" maxlength="600" value="' +
      ui.escapeHtml(course ? course.eligibility || "" : "") +
      '" placeholder="e.g. Pass in SSLC / Class 10 with Mathematics and Science"><div class="field-error hidden"></div></div>' +
      '<div class="form-field full" id="f-eligible_qualifications"><label>Eligible qualifications</label>' +
      '<div class="checkbox-row">' + qualCheckboxes(course) + "</div>" +
      '<div class="muted small">Leave none selected to accept applicants from every qualification.</div>' +
      '<div class="field-error hidden"></div></div>' +
      '<div class="form-field full" id="f-desc"><label>Description</label>' +
      '<textarea id="course-desc" maxlength="500">' + ui.escapeHtml(course ? course.description || "" : "") +
      "</textarea><div class='field-error hidden'></div></div>" +
      "</div>";

    var foot =
      '<button type="button" class="btn-secondary" id="course-cancel">Cancel</button>' +
      '<button type="button" class="btn-primary" id="course-save">' +
      (editing ? "Save changes" : "Add course") + "</button>";

    var overlay = ui.openModal(
      editing ? "Edit course" : "Add a new course",
      bodyHtml, foot, { locked: true }
    );
    overlay.querySelector(".modal").dataset.locked = "1";

    overlay.querySelector("#course-cancel").addEventListener("click", function () { ui.closeModal(); });
    overlay.querySelector("#course-save").addEventListener("click", function () { save(course); });
  }

  function save(original) {
    var overlay = document.querySelector(".modal-overlay");
    if (!overlay || !overlay.classList.contains("show")) return;
    document.querySelectorAll(".modal-body .field-error").forEach(function (el) {
      el.classList.add("hidden");
      el.parentElement.classList.remove("has-error");
    });

    var payload = {
      code: document.getElementById("course-code").value.trim(),
      name: document.getElementById("course-name").value.trim(),
      description: document.getElementById("course-desc").value.trim(),
      program_type: document.getElementById("course-type").value,
      eligibility: document.getElementById("course-eligibility").value.trim(),
      eligible_qualifications: Array.prototype.slice.call(
        document.querySelectorAll('.modal-body input[name="eligible-qual"]:checked')
      ).map(function (box) { return box.value; }),
      tuition_fee: document.getElementById("course-fee").value,
      duration_years: document.getElementById("course-duration").value,
      seats_total: document.getElementById("course-seats").value
    };

    var btn = overlay.querySelector("#course-save");
    btn.disabled = true;
    btn.textContent = "Saving\u2026";

    (original
      ? Api.patch(ADMIN.ENDPOINTS.course(original.id), payload)
      : Api.post(ADMIN.ENDPOINTS.courses, payload))
      .then(function () {
        ui.closeModal();
        ui.success(original ? "Course updated." : "Course added.");
        load();
        // Keep the dashboard filter list fresh.
        if (window.ADMIN.Dashboard && window.ADMIN.Dashboard.refreshCourses) {
          window.ADMIN.Dashboard.refreshCourses();
        }
      })
      .catch(function (err) {
        btn.disabled = false;
        btn.textContent = original ? "Save changes" : "Add course";
        if (err && err.errors && typeof err.errors === "object") {
          var map = {
            code: "course-code", name: "course-name", description: "course-desc",
            program_type: "course-type", eligibility: "course-eligibility",
            eligible_qualifications: "f-eligible_qualifications",
            tuition_fee: "course-fee", duration_years: "course-duration",
            seats_total: "course-seats"
          };
          Object.keys(err.errors).forEach(function (key) {
            var inputId = map[key];
            if (!inputId) return;
            var field = document.getElementById("f-" + key);
            if (field) {
              field.classList.add("has-error");
              var errEl = field.querySelector(".field-error");
              errEl.textContent = err.errors[key];
              errEl.classList.remove("hidden");
            }
            if (inputId) document.getElementById(inputId).focus();
          });
        } else {
          ui.error((err && err.message) || "Could not save the course.");
        }
      });
  }

  window.ADMIN.Courses = { load: load, openForm: openForm };
})();