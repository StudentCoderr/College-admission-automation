/* =========================================================================
   auth.js — session handling and route guards.
   -------------------------------------------------------------------------
   The session is a lightweight object kept in localStorage for the preview.
   In production the Flask backend sets an HttpOnly session cookie; this
   module then simply reflects /api/auth/me. The frontend never stores
   passwords or secrets.
   ========================================================================= */
window.Auth = (function () {
  "use strict";

  const KEY = window.APP_CONFIG.STORAGE.SESSION;

  function currentUser() {
    try {
      const raw = localStorage.getItem(KEY);
      return raw ? JSON.parse(raw) : null;
    } catch (e) {
      return null;
    }
  }

  function setUser(user) {
    if (user) localStorage.setItem(KEY, JSON.stringify(user));
    else localStorage.removeItem(KEY);
  }

  function homeFor(user) {
    if (!user) return "index.html";
    return user.role === "admin" ? "admin_dashboard.html" : "student_dashboard.html";
  }

  function currentFile() {
    const parts = window.location.pathname.split("/");
    return parts[parts.length - 1] || "index.html";
  }

  async function login(email, password) {
    const res = await Api.login({ email, password });
    setUser(res.user);
    return res.user;
  }

  async function register(payload) {
    const res = await Api.register(payload);
    setUser(res.user);
    return res.user;
  }

  async function logout() {
    try { await Api.logout(); } catch (e) { /* ignore network errors on logout */ }
    setUser(null);
    window.location.href = "index.html";
  }

  /** Redirect to login if there is no session. Returns the user otherwise. */
  function requireAuth() {
    const user = currentUser();
    if (!user) {
      const next = encodeURIComponent(currentFile());
      window.location.href = "login.html?next=" + next;
      return null;
    }
    return user;
  }

  /** Require a specific role; wrong role is sent to their own dashboard. */
  function requireRole(role) {
    const user = requireAuth();
    if (!user) return null;
    if (user.role !== role) {
      UI.toast("You do not have access to that page.", "error");
      window.location.href = homeFor(user);
      return null;
    }
    return user;
  }

  function isAdmin() { const u = currentUser(); return !!u && u.role === "admin"; }

  return { currentUser, setUser, homeFor, login, register, logout, requireAuth, requireRole, isAdmin };
})();
