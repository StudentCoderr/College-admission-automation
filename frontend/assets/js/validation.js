/* =========================================================================
   validation.js — reusable client-side validation.
   -------------------------------------------------------------------------
   This mirrors the SERVER-SIDE rules in the Flask app. Client-side validation
   improves UX only; the server always validates again and is the authority.
   ========================================================================= */
window.Validation = (function () {
  "use strict";

  const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;
  const PHONE_RE = /^[0-9+\-\s()]{7,20}$/;

  const rules = {
    required: (v) => (v != null && String(v).trim() !== "") || "This field is required.",
    email: (v) => !v || EMAIL_RE.test(v) || "Enter a valid email address.",
    phone: (v) => !v || PHONE_RE.test(v) || "Enter a valid phone number.",
    min: (n) => (v) => !v || String(v).length >= n || `Must be at least ${n} characters.`,
    max: (n) => (v) => !v || String(v).length <= n || `Must be at most ${n} characters.`,
    number: (v) => !v || !isNaN(parseFloat(v)) || "Enter a valid number.",
    minValue: (n) => (v) => v === "" || parseFloat(v) >= n || `Must be at least ${n}.`,
    maxValue: (n) => (v) => v === "" || parseFloat(v) <= n || `Must be at most ${n}.`,
    date: (v) => {
      if (!v) return true;
      const d = new Date(v);
      return !isNaN(d.getTime()) || "Enter a valid date.";
    },
    datePast: (v) => {
      if (!v) return true;
      return new Date(v) <= new Date() || "The date cannot be in the future.";
    },
    password: (v) => {
      if (!v) return "Password is required.";
      if (v.length < 8) return "Password must be at least 8 characters.";
      if (!/[A-Za-z]/.test(v)) return "Password must contain at least one letter.";
      if (!/\d/.test(v)) return "Password must contain at least one number.";
      return true;
    },
    match: (otherId, label) => (v) => {
      const other = document.getElementById(otherId);
      return !other || v === other.value || `${label || "Values"} do not match.`;
    },
    checked: (v, el) => (el && el.checked) || "Please tick this box to continue."
  };

  /**
   * Validate one field.
   * @param {HTMLElement} field  the input/select/textarea
   * @param {string[]} list      rule names, e.g. ["required","email"]
   * @returns {string|null}      error message or null
   */
  function validateField(field, list) {
    for (const name of list) {
      let fn;
      if (name.startsWith("match:")) {
        fn = rules.match(name.slice(6), "Passwords");
      } else {
        fn = rules[name];
      }
      if (!fn) continue;
      const result = fn(field.value, field);
      if (result !== true) return result;
    }
    return null;
  }

  function setFieldError(field, message) {
    const group = field.closest(".form-group") || field.parentElement;
    const errorEl = group ? group.querySelector(".form-error") : null;
    if (message) {
      if (group) group.classList.add("is-invalid");
      field.setAttribute("aria-invalid", "true");
      if (errorEl) errorEl.textContent = message;
    } else {
      if (group) group.classList.remove("is-invalid");
      field.removeAttribute("aria-invalid");
      if (errorEl) errorEl.textContent = "";
    }
  }

  /**
   * Validate a whole form using data-validate attributes on each control.
   * Markup: <input data-validate="required email">
   * @returns {{valid:boolean, data:object, errors:object}}
   */
  function validateForm(form) {
    const fields = form.querySelectorAll("[data-validate]");
    const data = {};
    const errors = {};
    let valid = true;
    let firstInvalid = null;

    fields.forEach((field) => {
      const list = field.getAttribute("data-validate").split(/\s+/).filter(Boolean);
      const message = validateField(field, list);
      if (message) {
        valid = false;
        errors[field.name] = message;
        setFieldError(field, message);
        if (!firstInvalid) firstInvalid = field;
      } else {
        setFieldError(field, null);
      }
      if (field.name) data[field.name] = field.type === "checkbox" ? field.checked : field.value.trim();
    });

    if (firstInvalid) {
      firstInvalid.focus({ preventScroll: false });
    }
    return { valid, data, errors };
  }

  /** Attach live validation: validate a field once it has been touched. */
  function bindLiveValidation(form) {
    form.querySelectorAll("[data-validate]").forEach((field) => {
      const revalidate = () => {
        const list = field.getAttribute("data-validate").split(/\s+/).filter(Boolean);
        setFieldError(field, validateField(field, list));
      };
      field.addEventListener("blur", revalidate);
      field.addEventListener("change", revalidate);
    });
  }

  return { rules, validateField, validateForm, setFieldError, bindLiveValidation };
})();
