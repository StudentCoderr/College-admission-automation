/* =========================================================================
   ui.js — shared UI helpers, header/footer rendering, toasts and modals.
   ========================================================================= */
window.UI = (function () {
  "use strict";

  const STATUS_LABELS = {
    draft: "Draft",
    submitted: "Submitted",
    under_review: "Under Review",
    correction_requested: "Correction Requested",
    approved: "Approved",
    rejected: "Rejected"
  };

  const DOC_LABELS = {
    marks_card: "Marks Card / Transcript",
    id_proof: "Government ID Proof",
    photo: "Passport-size Photograph",
    signature: "Signature",
    transfer_certificate: "Transfer / Migration Certificate",
    other: "Other Supporting Document"
  };

  /* ------------------------------ selectors --------------------------- */
  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

  /* ------------------------------ formatting -------------------------- */
  function escapeHtml(str) {
    if (str == null) return "";
    return String(str)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }

  function formatDate(value) {
    if (!value) return "—";
    const d = new Date(value);
    if (isNaN(d.getTime())) return String(value);
    return d.toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" });
  }

  function formatDateTime(value) {
    if (!value) return "—";
    const d = new Date(value);
    if (isNaN(d.getTime())) return String(value);
    return d.toLocaleString("en-IN", { day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });
  }

  function formatCurrency(amount) {
    if (amount == null) return "—";
    return "₹" + Number(amount).toLocaleString("en-IN");
  }

  function initials(name) {
    if (!name) return "?";
    return name.trim().split(/\s+/).slice(0, 2).map((w) => w[0].toUpperCase()).join("");
  }

  function statusPill(status) {
    const label = STATUS_LABELS[status] || status || "—";
    return `<span class="pill pill-${escapeHtml(status)}">${escapeHtml(label)}</span>`;
  }

  function statusLabel(status) { return STATUS_LABELS[status] || status || "—"; }

  /* ------------------------------ toasts ------------------------------ */
  function toastStack() {
    let stack = $("#toastStack");
    if (!stack) {
      stack = document.createElement("div");
      stack.id = "toastStack";
      stack.className = "toast-stack";
      document.body.appendChild(stack);
    }
    return stack;
  }

  function toast(message, type = "info", timeout = 4000) {
    const el = document.createElement("div");
    el.className = "toast toast-" + type;
    el.setAttribute("role", type === "error" ? "alert" : "status");
    el.textContent = message;
    toastStack().appendChild(el);
    setTimeout(() => {
      el.style.opacity = "0";
      el.style.transform = "translateY(6px)";
      setTimeout(() => el.remove(), 220);
    }, timeout);
  }

  /* ------------------------------ alerts ------------------------------ */
  function showAlert(container, message, type = "info") {
    if (!container) return;
    container.className = "alert alert-" + type;
    container.textContent = message;
    container.hidden = false;
  }
  function hideAlert(container) { if (container) container.hidden = true; }

  /* ------------------------------ loading ----------------------------- */
  function setLoading(btn, isLoading) {
    if (!btn) return;
    btn.classList.toggle("is-loading", isLoading);
    btn.disabled = isLoading;
  }

  function loadingBlock(message = "Loading…") {
    return `<div class="loading-block"><div class="spinner"></div><p>${escapeHtml(message)}</p></div>`;
  }

  function skeletonRows(n = 4) {
    let html = "";
    for (let i = 0; i < n; i++) {
      html += `<div style="padding:1rem 0"><div class="skeleton skeleton-line"></div>
        <div class="skeleton skeleton-line short"></div></div>`;
    }
    return html;
  }

  function emptyState({ icon = "📄", title = "Nothing here yet", text = "", action = "" }) {
    return `<div class="empty-state">
      <div class="empty-icon">${icon}</div>
      <h3>${escapeHtml(title)}</h3>
      <p>${escapeHtml(text)}</p>
      ${action}
    </div>`;
  }

  /* ------------------------------ modal ------------------------------- */
  function modalBackdrop() {
    let el = $("#modalBackdrop");
    if (!el) {
      el = document.createElement("div");
      el.id = "modalBackdrop";
      el.className = "modal-backdrop";
      el.innerHTML = '<div class="modal" role="dialog" aria-modal="true"></div>';
      el.addEventListener("click", (e) => { if (e.target === el) closeModal(); });
      document.body.appendChild(el);
    }
    return el;
  }

  function openModal({ title, body, confirmText = "Confirm", cancelText = "Cancel", danger = false, onConfirm }) {
    const backdrop = modalBackdrop();
    const box = $(".modal", backdrop);
    box.innerHTML = `
      <h3>${escapeHtml(title)}</h3>
      <div class="modal-body">${body || ""}</div>
      <div class="modal-actions">
        <button type="button" class="btn btn-ghost" data-modal-cancel>${escapeHtml(cancelText)}</button>
        <button type="button" class="btn ${danger ? "btn-danger" : ""}" data-modal-confirm>${escapeHtml(confirmText)}</button>
      </div>`;
    backdrop.classList.add("open");
    $("[data-modal-cancel]", box).onclick = closeModal;
    $("[data-modal-confirm]", box).onclick = async (ev) => {
      const btn = ev.currentTarget;
      setLoading(btn, true);
      try {
        if (onConfirm) await onConfirm();
        closeModal();
      } finally {
        setLoading(btn, false);
      }
    };
    const focusable = box.querySelector("input, textarea, select, [data-modal-confirm]");
    if (focusable) focusable.focus();
  }

  function closeModal() {
    const el = $("#modalBackdrop");
    if (el) el.classList.remove("open");
  }

  /** Promise-based confirmation dialog. */
  function confirmDialog({ title, message, confirmText = "Confirm", danger = false }) {
    return new Promise((resolve) => {
      openModal({
        title,
        body: `<p>${escapeHtml(message)}</p>`,
        confirmText,
        danger,
        onConfirm: () => resolve(true)
      });
      const backdrop = modalBackdrop();
      backdrop.addEventListener("click", function handler(e) {
        if (e.target === backdrop) { backdrop.removeEventListener("click", handler); resolve(false); }
      });
      $("[data-modal-cancel]", backdrop).addEventListener("click", () => resolve(false));
    });
  }

  /* ------------------------------ nav / footer ------------------------ */
  const NAV_LINKS = [
    { href: "index.html", label: "Home", page: "index" },
    { href: "courses.html", label: "Courses", page: "courses" },
    { href: "admission.html", label: "Apply", page: "admission" },
    { href: "status.html", label: "Track Status", page: "status" }
  ];
  const ADMIN_LINKS = [
    { href: "admin_dashboard.html", label: "Dashboard", page: "admin_dashboard" }
  ];

  function renderHeader() {
    const host = document.getElementById("site-header");
    if (!host) return;

    const user = window.Auth ? Auth.currentUser() : null;
    const page = document.body.getAttribute("data-page") || "";
    const cfg = window.APP_CONFIG;

    let links = NAV_LINKS.filter((l) => l.page !== "admission" || !user || user.role === "student");
    if (user && user.role === "admin") links = ADMIN_LINKS;
    if (user && user.role === "student") {
      links = links.concat([{ href: "student_dashboard.html", label: "Dashboard", page: "student_dashboard" }]);
    }

    const navHtml = links.map((l) =>
      `<li><a href="${l.href}" class="${l.page === page ? "active" : ""}">${l.label}</a></li>`
    ).join("");

    let ctaHtml;
    if (user) {
      ctaHtml = `
        <span class="user-chip hide-mobile">
          <span class="avatar">${escapeHtml(initials(user.name))}</span>${escapeHtml(user.name)}
        </span>
        <button type="button" class="btn btn-outline btn-sm" data-logout>Logout</button>`;
    } else {
      ctaHtml = `
        <a class="btn btn-ghost btn-sm hide-mobile" href="login.html">Login</a>
        <a class="btn btn-sm" href="register.html">Register</a>`;
    }

    host.className = "site-header";
    host.innerHTML = `
      <nav class="navbar container" aria-label="Main navigation">
        <a class="brand" href="index.html">
          <span class="brand-mark">EG</span>
          <span class="brand-text">
            <strong>${escapeHtml(cfg.COLLEGE_NAME)}</strong>
            <span>Admission Portal</span>
          </span>
        </a>
        <button class="nav-toggle" type="button" data-nav-toggle aria-label="Toggle menu" aria-expanded="false">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"><path d="M4 7h16M4 12h16M4 17h16"/></svg>
        </button>
        <ul class="nav-menu" id="navMenu">
          ${navHtml}
          <li class="nav-cta" style="gap:.5rem; margin-left:.5rem">${ctaHtml}</li>
        </ul>
      </nav>`;

    const toggle = $("[data-nav-toggle]", host);
    const menu = $("#navMenu", host);
    toggle.addEventListener("click", () => {
      const open = menu.classList.toggle("open");
      toggle.setAttribute("aria-expanded", String(open));
    });

    const logoutBtn = $("[data-logout]", host);
    if (logoutBtn) {
      logoutBtn.addEventListener("click", async () => {
        const ok = await confirmDialog({
          title: "Log out?",
          message: "You will need to sign in again to access your dashboard.",
          confirmText: "Log out"
        });
        if (ok) Auth.logout();
      });
    }
  }

  function renderFooter() {
    const host = document.getElementById("site-footer");
    if (!host) return;
    const c = SampleData.college;
    host.className = "site-footer";
    host.innerHTML = `
      <div class="container">
        <div class="footer-grid">
          <div>
            <h4>${escapeHtml(window.APP_CONFIG.COLLEGE_NAME)}</h4>
            <p>${escapeHtml(c.tagline)}</p>
            <p class="small">${escapeHtml(c.contact.address)}</p>
          </div>
          <div>
            <h4>Explore</h4>
            <a href="index.html">Home</a>
            <a href="courses.html">Courses</a>
            <a href="admission.html">Apply Online</a>
            <a href="status.html">Track Application</a>
          </div>
          <div>
            <h4>Account</h4>
            <a href="login.html">Login</a>
            <a href="register.html">Register</a>
            <a href="student_dashboard.html">Student Dashboard</a>
            <a href="admin_dashboard.html">Admin Dashboard</a>
          </div>
          <div>
            <h4>Contact</h4>
            <a href="tel:${escapeHtml(c.contact.phone)}">${escapeHtml(c.contact.phone)}</a>
            <a href="mailto:${escapeHtml(c.contact.email)}">${escapeHtml(c.contact.email)}</a>
            <a href="#">Help &amp; FAQ</a>
          </div>
        </div>
        <div class="footer-bottom flex-between flex-wrap">
          <span>&copy; ${new Date().getFullYear()} ${escapeHtml(window.APP_CONFIG.COLLEGE_NAME)}. All rights reserved.</span>
          <span>Frontend preview mode — no demo records are bundled.</span>
        </div>
      </div>`;
  }

  return {
    $, $$, escapeHtml,
    formatDate, formatDateTime, formatCurrency, initials,
    statusPill, statusLabel, STATUS_LABELS, DOC_LABELS,
    toast, showAlert, hideAlert, setLoading,
    loadingBlock, skeletonRows, emptyState,
    openModal, closeModal, confirmDialog,
    renderHeader, renderFooter
  };
})();
