/* ==========================================================================
 * Students management: a searchable / sortable / paginated table of every
 * registered student. Administrators can add a student (a one-time password
 * setup link is issued — no password is ever shown), edit details, change the
 * account status (active / inactive / withdrawn), resend a setup link and
 * permanently delete a student with a typed second confirmation.
 * ========================================================================= */
(function () {
  "use strict";

  var ui = window.ADMIN.UI;
  var Api = window.ADMIN.Api;

  var state = { q: "", status: "", sort: "created_at", order: "desc", page: 1, perPage: 10 };
  var students = [];
  var totalCount = 0;
  var totalPages = 1;
  var bound = false;
  var courseCache = null;

  var STATUS_LABELS = { active: "Active", inactive: "Inactive", withdrawn: "Withdrawn" };
  var STATUS_TONES = { active: "green", inactive: "gray", withdrawn: "amber" };

  var COLUMNS = [
    { key: "name", label: "Student", sortable: true },
    { key: "email", label: "Email", sortable: true },
    { key: "phone", label: "Phone", sortable: false },
    { key: "registration_number", label: "Reg. No.", sortable: false },
    { key: "applications_count", label: "Applications", sortable: false },
    { key: "created_at", label: "Registered", sortable: true },
    { key: "status", label: "Status", sortable: true },
    { key: "actions", label: "Actions", sortable: false }
  ];

  function queryString() {
    var p = new URLSearchParams();
    if (state.q) p.set("q", state.q);
    if (state.status) p.set("status", state.status);
    p.set("sort", state.sort);
    p.set("order", state.order);
    p.set("page", state.page);
    p.set("per_page", state.perPage);
    return p.toString();
  }

  function statusOf(student) {
    return student.status || (student.is_active ? "active" : "inactive");
  }

  function statusBadge(state_) {
    var tone = STATUS_TONES[state_] || "gray";
    return '<span class="badge badge-' + tone + '">' +
      ui.escapeHtml(STATUS_LABELS[state_] || state_) + "</span>";
  }

  function getCourses() {
    if (courseCache) return Promise.resolve(courseCache);
    return Api.get(ADMIN.ENDPOINTS.courses)
      .then(function (body) { courseCache = body.courses || []; return courseCache; })
      .catch(function () { courseCache = []; return courseCache; });
  }

  function courseName(id) {
    if (!id || !courseCache) return "\u2014";
    var found = courseCache.filter(function (c) { return String(c.id) === String(id); })[0];
    return found ? (found.name + " (" + found.code + ")") : "\u2014";
  }

  // ---------- Table --------------------------------------------------------
  function renderHeaders() {
    var row = COLUMNS.map(function (col) {
      if (!col.sortable) return "<th>" + ui.escapeHtml(col.label) + "</th>";
      var arrow = state.sort === col.key ? (state.order === "asc" ? "\u2191" : "\u2193") : "";
      return '<th class="sortable" data-sort="' + col.key + '">' + ui.escapeHtml(col.label) +
        ' <span class="sort-arrow">' + arrow + "</span></th>";
    }).join("");
    var thead = document.querySelector("#students-table thead");
    thead.innerHTML = "<tr>" + row + "</tr>";
    thead.querySelectorAll("th.sortable").forEach(function (th) {
      th.addEventListener("click", function () {
        var key = th.getAttribute("data-sort");
        if (state.sort === key) {
          state.order = state.order === "asc" ? "desc" : "asc";
        } else {
          state.sort = key;
          state.order = "desc";
        }
        state.page = 1;
        load();
      });
    });
  }

  function renderRows(rows) {
    var tbody = document.getElementById("students-body");
    if (!rows.length) {
      tbody.innerHTML = '<tr class="loading-row"><td colspan="99">' +
        '<div class="empty-state"><div class="icon">\U0001F50D</div>' +
        "<p>No students match the current filters.</p></div></td></tr>";
      return;
    }
    tbody.innerHTML = rows.map(function (s) {
      return "<tr>" +
        '<td class="applicant"><strong>' + ui.escapeHtml(s.full_name || s.name || "\u2014") + "</strong>" +
        "<span>" + ui.escapeHtml(s.role || "student") + "</span></td>" +
        "<td>" + ui.escapeHtml(s.email || "\u2014") + "</td>" +
        "<td>" + ui.escapeHtml(s.phone || "\u2014") + "</td>" +
        "<td>" + ui.escapeHtml(s.registration_number || "\u2014") + "</td>" +
        "<td>" + ui.escapeHtml(s.applications_count == null ? 0 : s.applications_count) + "</td>" +
        '<td class="muted">' + ui.escapeHtml(ui.formatDateOnly(s.created_at)) + "</td>" +
        "<td>" + statusBadge(statusOf(s)) + "</td>" +
        '<td class="actions-cell">' +
        '<button class="btn-secondary btn-sm btn-view" data-id="' + ui.escapeHtml(s.id) + '">View</button>' +
        '<button class="btn-secondary btn-sm btn-edit" data-id="' + ui.escapeHtml(s.id) + '">Edit</button>' +
        '<button class="btn-danger btn-sm btn-delete" data-id="' + ui.escapeHtml(s.id) + '">Delete</button>' +
        "</td></tr>";
    }).join("");
    tbody.querySelectorAll(".btn-view").forEach(function (btn) {
      btn.addEventListener("click", function () { openDetail(btn.getAttribute("data-id")); });
    });
    tbody.querySelectorAll(".btn-edit").forEach(function (btn) {
      btn.addEventListener("click", function () {
        findStudent(btn.getAttribute("data-id")).then(openForm);
      });
    });
    tbody.querySelectorAll(".btn-delete").forEach(function (btn) {
      btn.addEventListener("click", function () {
        findStudent(btn.getAttribute("data-id")).then(confirmDelete);
      });
    });
  }

  function findStudent(id) {
    var local = students.filter(function (s) { return String(s.id) === String(id); })[0];
    if (local) return Promise.resolve(local);
    return Api.get(ADMIN.ENDPOINTS.student(id)).then(function (body) { return body.student; });
  }

  function renderPagination() {
    document.getElementById("students-meta").textContent = totalCount
      ? "Showing " + ((state.page - 1) * state.perPage + 1) + "\u2013" +
        Math.min(state.page * state.perPage, totalCount) + " of " + totalCount + " students"
      : "No students";
    var controls = document.getElementById("students-controls");
    controls.innerHTML =
      '<button id="students-prev" ' + (state.page <= 1 ? "disabled" : "") + ">&#9664; Prev</button>" +
      '<span class="current">Page ' + state.page + " / " + Math.max(totalPages, 1) + "</span>" +
      '<button id="students-next" ' + (state.page >= totalPages ? "disabled" : "") + ">Next &#9654;</button>";
    var prev = document.getElementById("students-prev");
    var next = document.getElementById("students-next");
    if (prev) prev.addEventListener("click", function () { if (state.page > 1) { state.page -= 1; load(); } });
    if (next) next.addEventListener("click", function () { if (state.page < totalPages) { state.page += 1; load(); } });
  }

  function load() {
    var tbody = document.getElementById("students-body");
    ui.setLoading(tbody.id, true, "Loading students\u2026");
    getCourses();
    Api.get(ADMIN.ENDPOINTS.students + "?" + queryString())
      .then(function (body) {
        students = body.students || [];
        totalCount = body.total || 0;
        totalPages = body.pages || Math.ceil(totalCount / state.perPage) || 1;
        if (state.page > totalPages && totalPages > 0) {
          state.page = totalPages;
          return load();
        }
        renderHeaders();
        renderRows(students);
        renderPagination();
        document.getElementById("students-status").classList.add("hidden");
        document.getElementById("students-wrap").classList.remove("hidden");
      })
      .catch(function (err) {
        ui.setLoading(tbody.id, false);
        document.getElementById("students-wrap").classList.add("hidden");
        var box = document.getElementById("students-status");
        box.classList.remove("hidden");
        box.innerHTML = '<div class="empty-state"><div class="icon">\u26A0\uFE0F</div><p>' +
          ui.escapeHtml(err.message || "Could not load students.") + "</p></div>";
      });
  }

  // ---------- Add / edit form ----------------------------------------------
  function openForm(student) {
    var editing = !!student;
    var s = student || {};
    getCourses().then(function (courses) {
      var options = ['<option value="">\u2014 None \u2014</option>'].concat(
        courses.map(function (c) {
          var selected = String(s.assigned_course_id) === String(c.id) ? " selected" : "";
          return '<option value="' + ui.escapeHtml(c.id) + '"' + selected + ">" +
            ui.escapeHtml(c.name + " (" + c.code + ")") + "</option>";
        })
      ).join("");

      var currentStatus = statusOf(s);
      var statusOptions = ["active", "inactive", "withdrawn"].map(function (key) {
        return '<option value="' + key + '"' + (currentStatus === key ? " selected" : "") + ">" +
          STATUS_LABELS[key] + "</option>";
      }).join("");

      var bodyHtml =
        '<div class="form-grid">' +
        '<div class="form-field" id="f-full_name"><label>Full name *</label>' +
        '<input type="text" id="student-fname" maxlength="120" value="' +
        ui.escapeHtml(s.full_name || "") + '"><div class="field-error hidden"></div></div>' +
        '<div class="form-field" id="f-email"><label>Email *</label>' +
        '<input type="email" id="student-email" maxlength="254" value="' +
        ui.escapeHtml(s.email || "") + '"><div class="field-error hidden"></div></div>' +
        '<div class="form-field" id="f-phone"><label>Phone</label>' +
        '<input type="text" id="student-phone" maxlength="20" value="' +
        ui.escapeHtml(s.phone || "") + '"><div class="field-error hidden"></div></div>' +
        '<div class="form-field" id="f-registration_number"><label>Registration number</label>' +
        '<input type="text" id="student-regno" maxlength="40" value="' +
        ui.escapeHtml(s.registration_number || "") + '"><div class="field-error hidden"></div></div>' +
        '<div class="form-field full" id="f-assigned_course_id"><label>Assigned course</label>' +
        '<select id="student-course">' + options + '</select><div class="field-error hidden"></div></div>' +
        '<div class="form-field" id="f-status"><label>Account status</label>' +
        '<select id="student-form-status">' + statusOptions + '</select>' +
        '<div class="field-error hidden"></div></div>' +
        "</div>";

      var foot =
        '<button type="button" class="btn-secondary" id="student-form-cancel">Cancel</button>' +
        '<button type="button" class="btn-primary" id="student-form-save">' +
        (editing ? "Save changes" : "Add student") + "</button>";

      var overlay = ui.openModal(
        editing ? "Edit student" : "Add a new student",
        bodyHtml, foot, { locked: true }
      );
      overlay.querySelector(".modal").dataset.locked = "1";
      overlay.querySelector("#student-form-cancel").addEventListener("click", ui.closeModal);
      overlay.querySelector("#student-form-save").addEventListener("click", function () { save(student); });
    });
  }

  function save(original) {
    var overlay = document.querySelector(".modal-overlay");
    if (!overlay || !overlay.classList.contains("show")) return;
    document.querySelectorAll(".modal-body .field-error").forEach(function (el) {
      el.classList.add("hidden");
      el.parentElement.classList.remove("has-error");
    });

    var payload = {
      full_name: document.getElementById("student-fname").value.trim(),
      email: document.getElementById("student-email").value.trim(),
      phone: document.getElementById("student-phone").value.trim(),
      registration_number: document.getElementById("student-regno").value.trim(),
      assigned_course_id: document.getElementById("student-course").value || null,
      status: document.getElementById("student-form-status").value
    };

    var btn = overlay.querySelector("#student-form-save");
    btn.disabled = true;
    btn.textContent = "Saving\u2026";

    (original
      ? Api.patch(ADMIN.ENDPOINTS.student(original.id), payload)
      : Api.post(ADMIN.ENDPOINTS.students, payload))
      .then(function (body) {
        ui.closeModal();
        ui.success(original ? "Student updated." : "Student added.");
        load();
        if (window.ADMIN.Overview) window.ADMIN.Overview.load();
        if (!original && body && body.setup_url) showSetupLink(body.student, body.setup_url);
      })
      .catch(function (err) {
        btn.disabled = false;
        btn.textContent = original ? "Save changes" : "Add student";
        if (err && err.errors && typeof err.errors === "object") {
          var map = {
            full_name: "student-fname", email: "student-email", phone: "student-phone",
            registration_number: "student-regno", assigned_course_id: "student-course",
            status: "student-form-status"
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
          ui.error((err && err.message) || "Could not save the student.");
        }
      });
  }

  // ---------- One-time setup link ------------------------------------------
  function showSetupLink(student, url) {
    var name = student ? (student.full_name || student.email) : "the student";
    var html =
      "<p>Share this one-time link with <strong>" + ui.escapeHtml(name) +
      "</strong> through a trusted channel. It expires in 7 days, can be used " +
      "once, and lets them choose their own password. No password is ever shown here.</p>" +
      '<div class="form-field mt"><input type="text" id="setup-url" readonly value="' +
      ui.escapeHtml(url) + '"></div>';
    var foot =
      '<button type="button" class="btn-secondary" id="setup-copy">Copy link</button>' +
      '<button type="button" class="btn-primary" id="setup-close">Done</button>';
    var overlay = ui.openModal("Student created", html, foot, { locked: false });
    overlay.querySelector("#setup-close").addEventListener("click", ui.closeModal);
    overlay.querySelector("#setup-copy").addEventListener("click", function () {
      var input = document.getElementById("setup-url");
      input.select();
      var copied = false;
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(input.value).then(function () {
          ui.success("Setup link copied.");
        }).catch(function () {
          try { document.execCommand("copy"); copied = true; } catch (e) { /* ignore */ }
          ui.success(copied ? "Setup link copied." : "Select and copy the link above.");
        });
      } else {
        ui.info("Select and copy the link above.");
      }
    });
  }

  // ---------- Detail -------------------------------------------------------
  function kv(k, v, raw) {
    return '<div class="item"><div class="k">' + ui.escapeHtml(k) + "</div><div class='v'>" +
      (raw ? v : ui.escapeHtml(v == null || v === "" ? "\u2014" : v)) + "</div></div>";
  }

  function openDetail(id) {
    ui.openModal("Student profile",
      '<div class="screen"><div><div class="spinner"></div><p class="mt">Loading student\u2026</p></div></div>',
      "", { locked: true });
    document.querySelector(".modal-overlay .modal").dataset.locked = "1";
    getCourses().then(function () {
      Api.get(ADMIN.ENDPOINTS.student(id))
        .then(function (body) { renderDetail(body.student, body.applications || []); })
        .catch(function (err) {
          document.querySelector(".modal-body").innerHTML =
            '<div class="empty-state"><div class="icon">\u26A0\uFE0F</div><p>' +
            ui.escapeHtml(err.message || "Could not load this student.") + "</p></div>";
        });
    });
  }

  function renderDetail(s, apps) {
    var overlay = document.querySelector(".modal-overlay");
    overlay.querySelector(".modal h3").textContent = s.full_name || "Student";

    var current = statusOf(s);
    var html = '<div class="kv">' +
      kv("Full name", s.full_name) +
      kv("Email", s.email) +
      kv("Phone", s.phone) +
      kv("Registration no.", s.registration_number) +
      kv("Assigned course", courseName(s.assigned_course_id)) +
      kv("Account status", statusBadge(current), true) +
      kv("Registered", ui.formatDate(s.created_at)) +
      "</div>";

    html += '<div class="section-title">Admission applications (' + apps.length + ")</div>";
    if (!apps.length) {
      html += '<p class="muted small">This student has not submitted any applications yet.</p>';
    } else {
      html += '<div class="table-wrap"><table class="data-table"><thead><tr>' +
        "<th>No.</th><th>Course</th><th>Status</th><th>Submitted</th><th></th></tr></thead><tbody>" +
        apps.map(function (a) {
          var course = a.courseName
            ? ((a.courseCode ? a.courseCode + " \u2014 " : "") + a.courseName)
            : "\u2014";
          return "<tr><td class='app-no'>" + ui.escapeHtml(a.application_number || "(draft)") + "</td>" +
            "<td>" + ui.escapeHtml(course) + "</td>" +
            "<td>" + ui.badge(a.status) + "</td>" +
            '<td class="muted nowrap">' + ui.escapeHtml(ui.formatDateOnly(a.submitted_at || a.created_at)) + "</td>" +
            '<td class="actions-cell"><button class="btn-secondary btn-sm btn-open-app" data-id="' +
            ui.escapeHtml(a.id) + '">Open</button></td></tr>';
        }).join("") + "</tbody></table></div>";
    }

    overlay.querySelector(".modal-body").innerHTML = html;

    var toggleLabel = current === "active" ? "Deactivate" : "Reactivate";
    overlay.querySelector(".modal-foot").innerHTML =
      '<button type="button" class="btn-danger btn-sm" id="student-delete">Delete\u2026</button>' +
      '<button type="button" class="btn-secondary btn-sm" id="student-invite">Resend setup link</button>' +
      '<button type="button" class="btn-secondary btn-sm" id="student-edit">Edit</button>' +
      '<button type="button" class="' + (current === "active" ? "btn-secondary" : "btn-primary") +
      ' btn-sm" id="student-toggle">' + toggleLabel + "</button>" +
      '<button type="button" class="btn-secondary btn-sm" id="student-close">Close</button>';

    overlay.querySelector(".modal").dataset.locked = "";

    overlay.querySelector("#student-close").addEventListener("click", ui.closeModal);
    overlay.querySelector("#student-edit").addEventListener("click", function () { openForm(s); });
    overlay.querySelector("#student-toggle").addEventListener("click", function () { changeStatus(s); });
    overlay.querySelector("#student-invite").addEventListener("click", function () { resendInvite(s); });
    overlay.querySelector("#student-delete").addEventListener("click", function () { confirmDelete(s); });
    overlay.querySelectorAll(".btn-open-app").forEach(function (btn) {
      btn.addEventListener("click", function () {
        ui.closeModal();
        var link = document.querySelector('.sidebar nav a[data-tab="panel-applications"]');
        if (link) link.click();
        window.ADMIN.Detail.open(btn.getAttribute("data-id"));
      });
    });
  }

  function changeStatus(s) {
    var current = statusOf(s);
    var activating = current !== "active";
    var next = activating ? "active" : "inactive";
    ui.confirm({
      title: activating ? "Reactivate account" : "Deactivate account",
      message: "Set " + (s.full_name || s.email) + " to " + STATUS_LABELS[next] + "?" +
        (activating ? "" : " They will no longer be able to sign in; existing records are preserved."),
      confirmText: activating ? "Reactivate" : "Deactivate",
      danger: !activating
    }).then(function (result) {
      if (!result) return;
      updateStatus(s, next);
    });
  }

  function updateStatus(s, status) {
    Api.post(ADMIN.ENDPOINTS.studentStatus(s.id), { status: status })
      .then(function () {
        ui.success("Account marked " + STATUS_LABELS[status] + ".");
        ui.closeModal();
        load();
        if (window.ADMIN.Overview) window.ADMIN.Overview.load();
      })
      .catch(function (err) {
        ui.error(err.message || "Could not update the account.");
      });
  }

  function resendInvite(s) {
    ui.confirm({
      title: "Resend password setup link",
      message: "Generate a fresh one-time setup link for " + (s.full_name || s.email) +
        "? The previous link will stop working.",
      confirmText: "Generate link"
    }).then(function (result) {
      if (!result) return;
      Api.post(ADMIN.ENDPOINTS.studentInvite(s.id), {})
        .then(function (body) {
          ui.closeModal();
          showSetupLink(s, body.setup_url);
        })
        .catch(function (err) {
          ui.error(err.message || "Could not create a setup link.");
        });
    });
  }

  // ---------- Permanent deletion -------------------------------------------
  function confirmDelete(s) {
    var name = s.full_name || s.email;
    ui.confirm({
      title: "Delete " + name + "?",
      message: "Permanently deleting this student also removes their admission " +
        "applications, uploaded documents and review history. This cannot be " +
        "undone. If they simply withdrew, set the status to Withdrawn instead.",
      confirmText: "Permanently delete",
      danger: true
    }).then(function (result) {
      if (!result) return;
      promptDeleteConfirmation(s);
    });
  }

  function promptDeleteConfirmation(s) {
    var name = s.full_name || s.email;
    var html =
      "<p>You are about to permanently delete <strong>" + ui.escapeHtml(name) +
      "</strong>. Type <strong>DELETE</strong> and give a reason to confirm.</p>" +
      '<div class="form-field mt" id="delete-reason-field"><label>Reason (required)</label>' +
      '<input type="text" id="delete-reason" maxlength="300" ' +
      'placeholder="e.g. duplicate record; retention period elapsed">' +
      '<div class="field-error hidden"></div></div>' +
      '<div class="form-field" id="delete-confirm-field"><label>Type DELETE to confirm</label>' +
      '<input type="text" id="delete-confirm" autocomplete="off" placeholder="DELETE">' +
      '<div class="field-error hidden"></div></div>';
    var foot =
      '<button type="button" class="btn-secondary" id="delete-cancel">Cancel</button>' +
      '<button type="button" class="btn-danger" id="delete-confirm-btn">Permanently delete</button>';
    var overlay = ui.openModal("Confirm permanent deletion", html, foot, { locked: true });
    overlay.querySelector(".modal").dataset.locked = "1";

    overlay.querySelector("#delete-cancel").addEventListener("click", ui.closeModal);
    overlay.querySelector("#delete-confirm-btn").addEventListener("click", function () {
      var reason = document.getElementById("delete-reason").value.trim();
      var word = document.getElementById("delete-confirm").value.trim();
      var ok = true;
      if (!reason) {
        showFieldError("delete-reason-field", "A reason is required.");
        ok = false;
      }
      if (word !== "DELETE") {
        showFieldError("delete-confirm-field", "Type DELETE exactly to confirm.");
        ok = false;
      }
      if (!ok) return;

      var btn = overlay.querySelector("#delete-confirm-btn");
      btn.disabled = true;
      btn.textContent = "Deleting\u2026";
      Api.request(ADMIN.ENDPOINTS.student(s.id), {
        method: "DELETE", body: { confirm: "DELETE", reason: reason }
      }).then(function () {
        ui.closeModal();
        ui.success("Student and associated records deleted.");
        load();
        if (window.ADMIN.Overview) window.ADMIN.Overview.load();
      }).catch(function (err) {
        btn.disabled = false;
        btn.textContent = "Permanently delete";
        ui.error(err.message || "Could not delete the student.");
      });
    });
  }

  function showFieldError(fieldId, message) {
    var field = document.getElementById(fieldId);
    if (!field) return;
    field.classList.add("has-error");
    var el = field.querySelector(".field-error");
    if (el) { el.textContent = message; el.classList.remove("hidden"); }
  }

  // ---------- Filters ------------------------------------------------------
  function bindFilters() {
    var search = document.getElementById("student-search");
    search.addEventListener("input", ui.debounce(function () {
      state.q = search.value.trim();
      state.page = 1;
      load();
    }, 450));

    document.getElementById("student-status").addEventListener("change", function (e) {
      state.status = e.target.value;
      state.page = 1;
      load();
    });
    document.getElementById("student-sort").addEventListener("change", function (e) {
      state.sort = e.target.value;
      state.page = 1;
      load();
    });
    document.getElementById("student-order").addEventListener("change", function (e) {
      state.order = e.target.value;
      state.page = 1;
      load();
    });
    document.getElementById("student-per-page").addEventListener("change", function (e) {
      state.perPage = parseInt(e.target.value, 10) || 10;
      state.page = 1;
      load();
    });
    document.getElementById("students-reset").addEventListener("click", function () {
      state.q = ""; state.status = ""; state.sort = "created_at"; state.order = "desc"; state.page = 1;
      search.value = "";
      document.getElementById("student-status").value = "";
      document.getElementById("student-sort").value = "created_at";
      document.getElementById("student-order").value = "desc";
      load();
    });

    var addBtn = document.getElementById("add-student-button");
    if (addBtn) addBtn.addEventListener("click", function () { openForm(null); });
  }

  function init() {
    if (!bound) { bindFilters(); bound = true; }
    load();
  }

  window.ADMIN.Students = { load: init, openForm: openForm };
})();
