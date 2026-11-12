/* =========================================================================
   api.js — the ONLY place the frontend talks to data.
   -------------------------------------------------------------------------
   • When APP_CONFIG.USE_SAMPLE_DATA is true it answers from SampleData with a
     small simulated latency (so loading states are visible). This is the
     preview mode.
   • When false it issues real fetch() calls to the Flask API defined in
     config.js. The browser never touches a database directly.
   ========================================================================= */
window.ApiError = class ApiError extends Error {
  constructor(message, status = 0, details = null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.details = details;
  }
};

window.Api = (function () {
  "use strict";

  const cfg = window.APP_CONFIG;
  const S = cfg.STORAGE;

  /* -------------------------- small storage helpers ------------------- */
  function readJSON(key, fallback) {
    try {
      const raw = localStorage.getItem(key);
      return raw ? JSON.parse(raw) : fallback;
    } catch (e) {
      return fallback;
    }
  }
  function writeJSON(key, value) {
    try { localStorage.setItem(key, JSON.stringify(value)); } catch (e) { /* ignore */ }
  }

  /* Patches let an administrator's decisions (or a student's edits) persist
     across page navigation in preview mode. They are NOT used in real mode. */
  function readPatches() { return readJSON("cas.patches", {}); }
  function writePatches(p) { writeJSON("cas.patches", p); }
  function applyPatch(app) {
    const patch = readPatches()[app.id];
    return patch ? Object.assign({}, app, patch) : app;
  }

  const STORE = {
    readMine: () => readJSON(S.MY_APPLICATIONS, []),
    writeMine: (list) => writeJSON(S.MY_APPLICATIONS, list)
  };

  /* ---------------------------- sample engine ------------------------- */
  function delay(ms) { return new Promise((r) => setTimeout(r, ms)); }

  function allApplications() {
    const mine = STORE.readMine();
    const base = SampleData.applications.concat(mine);
    const seen = new Set();
    const merged = [];
    base.forEach((a) => {
      const patched = applyPatch(a);
      if (!seen.has(patched.id)) { seen.add(patched.id); merged.push(patched); }
    });
    return merged;
  }

  function createSampleApplication(payload) {
    const course = SampleData.findCourse(payload.courseId);
    const seq = String(allApplications().length + 1).padStart(5, "0");
    const app = {
      id: "APP-LOCAL-" + Date.now(),
      number: "ADM-2026-" + seq,
      userId: (window.Auth && Auth.currentUser() && Auth.currentUser().id) || "guest",
      applicantName: [payload.firstName, payload.middleName, payload.lastName].filter(Boolean).join(" "),
      email: payload.email,
      phone: payload.phone,
      courseId: payload.courseId,
      courseName: course ? course.name : "—",
      courseCode: course ? course.code : "—",
      status: "draft",
      percentage: payload.percentage || null,
      submittedAt: null,
      updatedAt: new Date().toISOString(),
      dateOfBirth: payload.dateOfBirth,
      gender: payload.gender,
      category: payload.category,
      nationality: payload.nationality || "Indian",
      address: payload.address,
      city: payload.city,
      state: payload.state,
      postalCode: payload.postalCode,
      qualifyingExam: payload.qualifyingExam,
      board: payload.board,
      school: payload.school,
      passingYear: payload.passingYear,
      marksObtained: payload.marksObtained,
      marksTotal: payload.marksTotal,
      adminNote: null,
      documents: [],
      history: [{ status: "draft", note: "Draft created from the online form.", at: new Date().toISOString() }]
    };
    const mine = STORE.readMine();
    mine.unshift(app);
    STORE.writeMine(mine);
    return app;
  }

  const sample = {
    async login({ email, password }) {
      await delay(500);
      const acc = SampleData.accounts.find(
        (a) => a.email.toLowerCase() === String(email).toLowerCase()
      );
      if (!acc || acc.password !== password) {
        throw new ApiError("Invalid email or password.", 401);
      }
      return { user: { id: acc.id, name: acc.name, email: acc.email, role: acc.role, phone: acc.phone } };
    },

    async register(payload) {
      await delay(600);
      const exists = SampleData.accounts.some(
        (a) => a.email.toLowerCase() === payload.email.toLowerCase()
      );
      if (exists) throw new ApiError("An account with this email already exists.", 409);
      return {
        user: { id: "u-" + Date.now(), name: payload.fullName, email: payload.email, role: "student", phone: payload.phone }
      };
    },

    async logout() { await delay(150); return { ok: true }; },
    async me() { await delay(150); return { user: null }; },

    async getCourses() { await delay(400); return { courses: SampleData.courses.slice() }; },

    async getAnnouncements() { await delay(300); return { announcements: SampleData.announcements.slice() }; },

    async getApplications({ scope = "mine", status = "", courseId = "", search = "" } = {}) {
      await delay(450);
      const user = window.Auth && Auth.currentUser();
      let list = allApplications();
      if (scope !== "all") {
        const uid = user ? user.id : null;
        list = list.filter((a) => a.userId === uid);
      }
      if (status) list = list.filter((a) => a.status === status);
      if (courseId) list = list.filter((a) => a.courseId === courseId);
      if (search) {
        const t = search.toLowerCase();
        list = list.filter((a) =>
          (a.number || "").toLowerCase().includes(t) ||
          (a.applicantName || "").toLowerCase().includes(t) ||
          (a.email || "").toLowerCase().includes(t)
        );
      }
      return { applications: list };
    },

    async getApplication(id) {
      await delay(350);
      const app = allApplications().find((a) => a.id === id || a.number === id);
      if (!app) throw new ApiError("Application not found.", 404);
      return { application: app };
    },

    async createApplication(payload) {
      await delay(700);
      return { application: createSampleApplication(payload) };
    },

    async updateApplication(id, payload) {
      await delay(400);
      const patch = readPatches();
      patch[id] = Object.assign({}, patch[id], payload, { updatedAt: new Date().toISOString() });
      writePatches(patch);
      return { application: applyPatch(SampleData.findApplication(id) || { id }) };
    },

    async submitApplication(id) {
      await delay(600);
      const patches = readPatches();
      const app = allApplications().find((a) => a.id === id);
      const history = (app.history || []).concat([{ status: "submitted", note: "Application submitted.", at: new Date().toISOString() }]);
      Object.assign(patches, { [id]: Object.assign({}, patches[id], { status: "submitted", submittedAt: new Date().toISOString(), history }) });
      writePatches(patches);
      return { application: allApplications().find((a) => a.id === id) };
    },

    async uploadDocuments(id) {
      await delay(500);
      return { ok: true };
    },

    async trackApplication({ number, email }) {
      await delay(600);
      const app = allApplications().find(
        (a) => (a.number || "").toLowerCase() === String(number).trim().toLowerCase()
      );
      if (!app) throw new ApiError("No application found with that application number.", 404);
      if (email && String(email).trim().toLowerCase() !== String(app.email).toLowerCase()) {
        throw new ApiError("The email does not match this application number.", 403);
      }
      return { application: app };
    },

    async getAdminStats() {
      await delay(450);
      const list = allApplications();
      const counts = { total: list.length, submitted: 0, under_review: 0, correction_requested: 0, approved: 0, rejected: 0, draft: 0 };
      list.forEach((a) => { if (counts[a.status] != null) counts[a.status] += 1; });
      counts.pending = counts.submitted + counts.under_review + counts.correction_requested;
      return { stats: counts };
    },

    async updateApplicationStatus(id, status, note) {
      await delay(600);
      const patches = readPatches();
      const app = allApplications().find((a) => a.id === id);
      const history = (app.history || []).concat([{ status, note: note || "", at: new Date().toISOString() }]);
      patches[id] = Object.assign({}, patches[id], { status, adminNote: note || null, updatedAt: new Date().toISOString(), history });
      writePatches(patches);
      return { application: allApplications().find((a) => a.id === id) };
    }
  };

  /* ------------------------------ real engine ------------------------- */
  const MUTATING = ["POST", "PUT", "PATCH", "DELETE"];

  function storedCsrf() {
    try { return localStorage.getItem(S.CSRF) || ""; } catch (e) { return ""; }
  }
  function storeCsrf(token) {
    if (!token) return;
    try { localStorage.setItem(S.CSRF, token); } catch (e) { /* ignore */ }
  }
  function clearCsrf() {
    try { localStorage.removeItem(S.CSRF); } catch (e) { /* ignore */ }
  }

  /* Fetch a CSRF token once (the Flask API expects X-CSRF-Token on writes). */
  async function ensureCsrf() {
    if (storedCsrf()) return;
    try {
      const res = await fetch(cfg.API_BASE_URL + cfg.ENDPOINTS.csrf.path, {
        method: "GET",
        credentials: "include",
        headers: { "Accept": "application/json" }
      });
      const data = await res.json().catch(() => ({}));
      storeCsrf(data && data.csrf_token);
    } catch (e) { /* the actual request will surface any error */ }
  }

  async function request(method, path, body) {
    if (MUTATING.indexOf(method) !== -1) await ensureCsrf();
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), cfg.REQUEST_TIMEOUT_MS);
    try {
      const res = await fetch(cfg.API_BASE_URL + path, {
        method,
        credentials: "include",
        headers: {
          "Content-Type": "application/json",
          "Accept": "application/json",
          "X-CSRF-Token": storedCsrf()
        },
        body: body != null ? JSON.stringify(body) : undefined,
        signal: controller.signal
      });
      const text = await res.text();
      const data = text ? JSON.parse(text) : {};
      if (data && data.csrf_token) storeCsrf(data.csrf_token);
      if (!res.ok) {
        throw new ApiError(data.error || data.message || "Request failed.", res.status, data);
      }
      return data;
    } catch (err) {
      if (err.name === "AbortError") throw new ApiError("The request timed out. Please try again.", 0);
      if (err instanceof ApiError) {
        // A stale token (e.g. after the session changed) is fetched freshly
        // on the next mutating request.
        if (err.status === 403) clearCsrf();
        throw err;
      }
      throw new ApiError("Could not reach the server. Is the Flask API running?", 0);
    } finally {
      clearTimeout(timer);
    }
  }

  const real = {
    login: (p) => request("POST", cfg.ENDPOINTS.login.path, p),
    register: (p) => request("POST", cfg.ENDPOINTS.register.path, p),
    logout: async () => {
      try { return await request("POST", cfg.ENDPOINTS.logout.path, {}); }
      finally { clearCsrf(); }
    },
    me: () => request("GET", cfg.ENDPOINTS.me.path),
    getCourses: () => request("GET", cfg.ENDPOINTS.courses.path),
    getAnnouncements: () => request("GET", cfg.ENDPOINTS.announcements.path),
    getApplications: (opts = {}) => {
      const q = new URLSearchParams(Object.entries(opts).filter(([, v]) => v != null && v !== ""));
      return request("GET", cfg.ENDPOINTS.applications.path + (q.toString() ? "?" + q : ""));
    },
    getApplication: (id) => request("GET", cfg.ENDPOINTS.application.path.replace(":id", id)),
    createApplication: (p) => request("POST", cfg.ENDPOINTS.applicationCreate.path, p),
    updateApplication: (id, p) => request("PUT", cfg.ENDPOINTS.applicationUpdate.path.replace(":id", id), p),
    submitApplication: (id) => request("POST", cfg.ENDPOINTS.applicationSubmit.path.replace(":id", id), {}),
    uploadDocuments: (id) => request("POST", cfg.ENDPOINTS.documentUpload.path.replace(":id", id), {}),
    trackApplication: (p) => request("POST", cfg.ENDPOINTS.track.path, p),
    getAdminStats: () => request("GET", cfg.ENDPOINTS.adminStats.path),
    updateApplicationStatus: (id, status, note) =>
      request("POST", cfg.ENDPOINTS.applicationStatus.path.replace(":id", id), { status, note })
  };

  return cfg.USE_SAMPLE_DATA ? sample : real;
})();
