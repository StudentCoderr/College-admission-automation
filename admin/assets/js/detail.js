/* ==========================================================================
 * Application detail drawer: student details, academic records, uploaded
 * documents (signed URLs), status history, and admin review actions.
 * ========================================================================= */
(function () {
  "use strict";

  var ui = window.ADMIN.UI;
  var Api = window.ADMIN.Api;

  var currentId = null;
  var currentApp = null;

  function open(applicationId) {
    currentId = applicationId;
    showDrawer();
    renderLoading();
    fetchDetail(applicationId);
  }

  function showDrawer() {
    document.getElementById("drawer-overlay").style.display = "block";
    document.getElementById("drawer").classList.add("open");
    document.body.style.overflow = "hidden";
  }

  function closeDrawer() {
    document.getElementById("drawer-overlay").style.display = "none";
    document.getElementById("drawer").classList.remove("open");
    document.body.style.overflow = "";
    currentId = null;
    currentApp = null;
  }

  function renderLoading() {
    var body = document.getElementById("drawer-body");
    body.innerHTML = '<div class="screen"><div><div class="spinner"></div>' +
      "<p class='mt'>Loading application\u2026</p></div></div>";
  }

  function fetchDetail(applicationId) {
    Api.get(ADMIN.ENDPOINTS.application(applicationId))
      .then(function (body) {
        currentApp = body.application;
        document.getElementById("drawer-title").textContent =
          currentApp.application_number || "Draft application";
        document.getElementById("drawer-sub").innerHTML =
          ui.badge(currentApp.status) + ' <span class="muted" style="color:#bfdbfe">' +
          ui.escapeHtml(ui.formatDate(currentApp.updated_at)) + "</span>";
        renderBody();
      })
      .catch(function (err) {
        document.getElementById("drawer-title").textContent = "Application";
        document.getElementById("drawer-sub").innerHTML = "";
        var body = document.getElementById("drawer-body");
        body.innerHTML = '<div class="empty-state"><div class="icon">\u26A0\uFE0F</div>' +
          "<p>" + ui.escapeHtml(err.message || "Could not load this application.") +
          "</p><button class='btn-secondary' id='drawer-close-btn'>Close</button></div>";
        body.querySelector("#drawer-close-btn").addEventListener("click", closeDrawer);
      });
  }

  function kvItem(k, v) {
    return '<div class="item"><div class="k">' + ui.escapeHtml(k) + "</div><div class='v'>" +
      ui.escapeHtml(v == null || v === "" ? "\u2014" : v) + "</div></div>";
  }

  function renderBody() {
    var a = currentApp;
    var body = document.getElementById("drawer-body");

    var html = "";

    // --- Personal details ------------------------------------------------
    html += '<div class="section-title">Applicant details</div>';
    html += '<div class="kv">' +
      kvItem("Full name", (a.first_name + " " + (a.last_name || "")).trim()) +
      kvItem("Date of birth", a.date_of_birth) +
      kvItem("Gender", a.gender) +
      kvItem("Category", a.category) +
      kvItem("Nationality", a.nationality) +
      kvItem("Email", a.email) +
      kvItem("Phone", a.phone) +
      kvItem("Address", (a.address_line || "") + (a.city ? ", " + a.city : "")) +
      kvItem("City / State", [a.city, a.state].filter(Boolean).join(", ")) +
      kvItem("Postal code", a.postal_code) +
      kvItem("Country", a.country) +
      "</div>";

    // --- Academics --------------------------------------------------------
    var qualKey = String(a.qualifying_exam || "").toLowerCase();
    var qualLabels = { sslc: "SSLC", puc: "PUC", iti: "ITI" };
    var instLabels = { sslc: "School name", puc: "College name", iti: "ITI institute name" };
    html += '<div class="section-title">Academic records</div>';
    html += '<div class="kv">' +
      kvItem("Qualification", qualLabels[qualKey] || a.qualifying_exam || "\u2014") +
      kvItem(instLabels[qualKey] || "School / Institution",
        a.institution_name || a.school_name) +
      ((qualKey === "sslc" || qualKey === "puc")
        ? kvItem("Board", a.board_university) : "") +
      (qualKey === "puc" ? kvItem("Stream", a.stream) : "") +
      (qualKey === "iti" ? kvItem("Trade / specialization", a.trade) : "") +
      (qualKey === "iti"
        ? kvItem("Affiliation", a.affiliation || "Not applicable") : "") +
      kvItem("Registration / roll number", a.roll_number) +
      kvItem("Passing year", a.passing_year) +
      kvItem("Marks", (a.marks_obtained != null ? a.marks_obtained : "\u2014") + " / " +
        (a.marks_total != null ? a.marks_total : "\u2014")) +
      kvItem("Percentage", a.percentage != null ? a.percentage + "%" : "\u2014") +
      (a.courseName ? kvItem("Applied course", a.courseCode + " \u2014 " + a.courseName) : "") +
      "</div>";

    // --- Admin note --------------------------------------------------------
    if (a.admin_note) {
      html += '<div class="section-title">Admin note</div>';
      html += "<p class='small'>" + ui.escapeHtml(a.admin_note) + "</p>";
    }

    // --- Documents ---------------------------------------------------------
    html += '<div class="section-title">Uploaded documents (' + (a.documents || []).length + ")</div>";
    var docs = a.documents || [];
    if (!docs.length) {
      html += "<p class='muted small'>No documents uploaded.</p>";
    } else {
      html += docs.map(function (d) {
        var verified = d.verified
          ? '<span class="badge badge-green">Verified</span>'
          : '<span class="badge badge-gray">Unverified</span>';
        var openLink = d.url
          ? '<a class="btn-secondary btn-sm" target="_blank" rel="noopener" href="' +
            ui.escapeHtml(d.url) + '">Open</a>'
          : "";
        return '<div class="doc-row">' +
          '<div class="doc-icon">' + ui.escapeHtml(fileIcon(d.type || "other")) + "</div>" +
          '<div class="doc-name"><strong>' + ui.escapeHtml(d.name || d.file_name) + "</strong>" +
          "<span>" + ui.escapeHtml(docTypeLabel(d.type)) + " \u00b7 " +
          ui.escapeHtml(ui.formatBytes(d.size)) + "</span></div>" +
          "<div>" + verified + "</div>" +
          (openLink ? "<div>" + openLink + "</div>" : "") +
          '<div><button class="btn-sm btn-ghost btn-verify" data-id="' +
          ui.escapeHtml(d.id) + '" data-verified="' + (d.verified ? "1" : "0") + '">' +
          (d.verified ? "Unverify" : "Verify") + "</button></div>" +
          "</div>";
      }).join("");
    }

    // --- Status history -----------------------------------------------------
    html += '<div class="section-title">Status history</div>';
    var history = a.history || [];
    if (!history.length) {
      html += "<p class='muted small'>No status changes recorded.</p>";
    } else {
      html += '<div class="timeline">' + history.map(function (h) {
        var who = h.changed_by_name ? h.changed_by_name : (h.changed_by_role === "admin" ? "Administrator" : "Student");
        return '<div class="event">' +
          '<div class="flex between">' + ui.badge(h.status) +
          '<span class="when">' + ui.escapeHtml(ui.formatDate(h.at || h.created_at)) + "</span></div>" +
          '<p>' + ui.escapeHtml(h.note || h.status) + "</p>" +
          '<div class="who">by ' + ui.escapeHtml(who) + "</div></div>";
      }).join("") + "</div>";
    }

    // --- Review actions ------------------------------------------------------
    html += '<div class="section-title">Review</div>';
    html += '<div class="review-actions">' +
      '<button class="btn-success" id="act-approved" data-status="approved">Approve</button>' +
      '<button class="btn-warn" id="act-correction_requested" data-status="correction_requested">Request Correction</button>' +
      '<button class="btn-danger" id="act-rejected" data-status="rejected">Reject</button>' +
      "</div>";

    body.innerHTML = html;

    body.querySelectorAll(".btn-verify").forEach(function (btn) {
      btn.addEventListener("click", function () {
        toggleVerify(btn.getAttribute("data-id"), btn.getAttribute("data-verified") === "1");
      });
    });
    body.querySelectorAll(".review-actions button").forEach(function (btn) {
      btn.addEventListener("click", function () { reviewAction(btn.getAttribute("data-status")); });
    });
  }

  function docTypeLabel(type) {
    var labels = {
      marks_card: "Marks Card",
      id_proof: "Government ID",
      photo: "Photograph",
      signature: "Signature",
      transfer_certificate: "Transfer Certificate",
      other: "Document"
    };
    return labels[type] || "Document";
  }

  function fileIcon(type) {
    var icons = {
      marks_card: "\U0001F4DA",
      id_proof: "\U0001F464",
      photo: "\U0001F4F8",
      signature: "\u270D\uFE0F",
      transfer_certificate: "\U0001F4C4",
      other: "\U0001F4C1"
    };
    return icons[type] || "\U0001F4C1";
  }

  // ---------- Review actions ------------------------------------------------
  function reviewAction(status) {
    var action = ADMIN.REVIEW_ACTIONS[status];
    var a = currentApp;
    ui.confirm({
      title: action.label + " application",
      message: "This will change the status of " +
        ((a.application_number || "this draft") + " to \u201c" + action.label + "\u201d."),
      confirmText: action.label,
      needsNote: action.needsNote,
      noteLabel: "Note to the applicant",
      danger: status === "rejected"
    }).then(function (result) {
      if (!result) return;
      var payload = { status: status };
      if (action.needsNote) payload.note = result.note;
      Api.patch(ADMIN.ENDPOINTS.status(currentId), payload)
        .then(function (body) {
          ui.success("Application " + (body.application.status || status) + ".");
          if (window.ADMIN.Dashboard) window.ADMIN.Dashboard.refresh();
          fetchDetail(currentId);
        })
        .catch(function (err) {
          ui.error(err.message || "Could not update the status.");
        });
    });
  }

  // ---------- Document verification -----------------------------------------
  function toggleVerify(documentId, currentlyVerified) {
    Api.post(ADMIN.ENDPOINTS.documentVerify(documentId), { verified: !currentlyVerified })
      .then(function () {
        ui.success(currentlyVerified ? "Verification removed." : "Document verified.");
        if (window.ADMIN.Dashboard) window.ADMIN.Dashboard.refreshStats();
        fetchDetail(currentId);
      })
      .catch(function (err) {
        ui.error(err.message || "Could not update the document.");
      });
  }

  function wireClose() {
    document.getElementById("drawer-overlay").addEventListener("click", closeDrawer);
    document.getElementById("drawer-close").addEventListener("click", closeDrawer);
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") closeDrawer();
    });
  }

  window.ADMIN.Detail = { open: open, close: closeDrawer, wireClose: wireClose };
})();