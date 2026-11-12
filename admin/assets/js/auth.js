/* ==========================================================================
 * Authentication helpers for the admin console.
 *  - login form handling (login.html)
 *  - session guard: /api/auth/me, admin-role check, logout
 * ========================================================================= */
(function () {
  "use strict";

  var ui = window.ADMIN.UI;

  function currentUser() {
    return window.ADMIN.Api.get(ADMIN.ENDPOINTS.me).then(function (body) {
      return body.user || null;
    });
  }

  // ---------- Login page ------------------------------------------------
  function initLogin() {
    var form = document.getElementById("login-form");
    if (!form) return;

    form.addEventListener("submit", function (e) {
      e.preventDefault();
      var email = document.getElementById("email").value.trim();
      var password = document.getElementById("password").value;
      var apiField = document.getElementById("api-base");
      if (apiField && apiField.value.trim()) {
        try { localStorage.setItem("admin_api_base", apiField.value.trim().replace(/\/+$/, "")); }
        catch (err) { /* ignore */ }
      }
      var errorBox = document.getElementById("login-error");
      errorBox.style.display = "none";

      var btn = document.getElementById("login-button");
      btn.disabled = true;
      btn.textContent = "Signing in\u2026";

      ADMIN.Api.post(ADMIN.ENDPOINTS.login, { email: email, password: password })
        .then(function (body) {
          var user = body.user;
          if (!user || user.role !== "admin") {
            // Logged in but not an administrator.
            return ADMIN.Api.post(ADMIN.ENDPOINTS.logout, {}).catch(function () {
              /* ignore */
            }).then(function () {
              throw new window.ADMIN.Api.ApiError(
                "Only administrator accounts can open this dashboard.", 403);
            });
          }
          window.location.replace("index.html");
        })
        .catch(function (err) {
          if (err instanceof window.ADMIN.Api.ApiError && err.status === 0) {
            errorBox.textContent = err.message;
          } else {
            errorBox.textContent = err.message || "Login failed.";
          }
          errorBox.style.display = "block";
        })
        .finally(function () {
          btn.disabled = false;
          btn.textContent = "Sign in";
        });
    });
  }

  // ---------- Session guard for the dashboard (index.html) --------------
  function guardDashboard() {
    return currentUser().then(function (user) {
      if (!user) {
        var q = ADMIN.API_BASE ? "?api=" + encodeURIComponent(ADMIN.API_BASE) : "";
        window.location.replace("login.html" + q);
        return null;
      }
      if (user.role !== "admin") {
        document.getElementById("app").classList.add("hidden");
        document.getElementById("forbidden-screen").classList.remove("hidden");
        return null;
      }
      document.getElementById("screen-loading").classList.add("hidden");
      document.getElementById("app").classList.remove("hidden");
      ui.success("Welcome, " + user.name + ".");
      return user;
    });
  }

  function initLogout() {
    function wire(btn) {
      if (!btn) return;
      btn.addEventListener("click", function () {
        var q = ADMIN.API_BASE ? "?api=" + encodeURIComponent(ADMIN.API_BASE) : "";
        ADMIN.Api.post(ADMIN.ENDPOINTS.logout, {}).catch(function () { /* ignore */ })
          .finally(function () {
            window.location.replace("login.html" + q);
          });
      });
    }
    wire(document.getElementById("logout-button"));
    wire(document.getElementById("forbidden-logout"));
  }

  window.ADMIN.Auth = {
    initLogin: initLogin,
    initLogout: initLogout,
    guardDashboard: guardDashboard,
    currentUser: currentUser
  };
})();