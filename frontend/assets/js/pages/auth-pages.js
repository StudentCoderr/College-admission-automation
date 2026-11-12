/* auth-pages.js — login and registration behaviour */
(function () {
  "use strict";

  function loginInit() {
    const form = document.getElementById("loginForm");
    if (!form) return;
    const alertEl = document.getElementById("formAlert");
    const submit = form.querySelector('button[type="submit"]');

    Validation.bindLiveValidation(form);

    // Password visibility toggle
    document.querySelectorAll("[data-toggle-password]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const input = document.getElementById(btn.getAttribute("data-toggle-password"));
        const show = input.type === "password";
        input.type = show ? "text" : "password";
        btn.textContent = show ? "Hide" : "Show";
      });
    });

    form.addEventListener("submit", async (ev) => {
      ev.preventDefault();
      UI.hideAlert(alertEl);
      const { valid, data } = Validation.validateForm(form);
      if (!valid) { UI.showAlert(alertEl, "Please fix the highlighted fields.", "error"); return; }

      UI.setLoading(submit, true);
      try {
        const user = await Auth.login(data.email, data.password);
        UI.toast(`Welcome back, ${user.name.split(" ")[0]}!`, "success");
        const next = App.getQueryParam("next");
        setTimeout(() => {
          window.location.href = next && next.endsWith(".html") ? next : Auth.homeFor(user);
        }, 500);
      } catch (err) {
        UI.showAlert(alertEl, err.message, "error");
        UI.setLoading(submit, false);
      }
    });
  }

  function registerInit() {
    const form = document.getElementById("registerForm");
    if (!form) return;
    const alertEl = document.getElementById("formAlert");
    const submit = form.querySelector('button[type="submit"]');

    Validation.bindLiveValidation(form);

    document.querySelectorAll("[data-toggle-password]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const input = document.getElementById(btn.getAttribute("data-toggle-password"));
        const show = input.type === "password";
        input.type = show ? "text" : "password";
        btn.textContent = show ? "Hide" : "Show";
      });
    });

    form.addEventListener("submit", async (ev) => {
      ev.preventDefault();
      UI.hideAlert(alertEl);
      const { valid, data } = Validation.validateForm(form);
      if (!valid) { UI.showAlert(alertEl, "Please fix the highlighted fields.", "error"); return; }
      if (form.terms && !form.terms.checked) {
        UI.showAlert(alertEl, "Please accept the terms and privacy policy to continue.", "error");
        return;
      }

      UI.setLoading(submit, true);
      try {
        const user = await Auth.register({
          fullName: data.fullName,
          email: data.email,
          phone: data.phone,
          password: data.password
        });
        UI.toast("Account created successfully!", "success");
        setTimeout(() => { window.location.href = Auth.homeFor(user); }, 600);
      } catch (err) {
        UI.showAlert(alertEl, err.message, "error");
        UI.setLoading(submit, false);
      }
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    loginInit();
    registerInit();
  });
})();
