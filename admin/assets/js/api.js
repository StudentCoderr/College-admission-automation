/* ==========================================================================
 * Thin API client for the admin console.
 *  - attaches the X-CSRF-Token header to state-changing requests
 *  - includes session cookies on every request
 *  - returns parsed JSON, throws ApiError with message + field errors
 *  - retries once after refreshing the CSRF token when the server says 403
 * ========================================================================= */
(function () {
  "use strict";

  function ApiError(message, status, errors) {
    this.message = message || "Something went wrong.";
    this.status = status;
    this.errors = errors || null;
  }
  ApiError.prototype = Object.create(Error.prototype);
  ApiError.prototype.constructor = ApiError;

  var csrfToken = null;

  function getCsrf(force) {
    if (csrfToken && !force) return Promise.resolve(csrfToken);
    return window.fetch(ADMIN.url(ADMIN.ENDPOINTS.csrf), { credentials: "include" })
      .then(function (r) { return r.json(); })
      .then(function (body) {
        csrfToken = body && body.csrf_token ? body.csrf_token : null;
        if (!csrfToken) throw new ApiError("Could not obtain a CSRF token.", 403);
        return csrfToken;
      })
      .catch(function (err) {
        if (err instanceof ApiError) throw err;
        throw new ApiError("Could not reach the server. Is the API running?", 0);
      });
  }

  function isWrite(method) {
    return ["POST", "PUT", "PATCH", "DELETE"].indexOf((method || "GET").toUpperCase()) !== -1;
  }

  function request(path, options) {
    options = options || {};
    var method = (options.method || "GET").toUpperCase();
    var init = {
      method: method,
      credentials: "include",
      headers: options.headers || {}
    };
    if (options.body !== undefined && options.body !== null) {
      if (options.formData) {
        init.body = options.formData; // multipart; no Content-Type header
      } else {
        init.headers["Content-Type"] = "application/json";
        init.body = JSON.stringify(options.body);
      }
    }

    var doFetch = function () {
      if (isWrite(method)) {
        return getCsrf().then(function (token) {
          init.headers["X-CSRF-Token"] = token;
          return window.fetch(ADMIN.url(path), init);
        });
      }
      return window.fetch(ADMIN.url(path), init);
    };

    return doFetch().then(function (response) {
      var contentType = response.headers.get("Content-Type") || "";
      var parse = contentType.indexOf("application/json") !== -1
        ? response.json().catch(function () { return null; })
        : response.text().then(function (t) { return { ok: response.ok, raw: t }; });

      return parse.then(function (body) {
        if (response.status === 401) {
          // Session expired: bounce to the login screen.
          redirectToLogin();
          throw new ApiError("Your session has expired. Please log in again.", 401);
        }
        if (response.status === 403 && csrfToken && body && body.error &&
            /csrf/i.test(body.error)) {
          // Stale token: refresh once and retry.
          return getCsrf(true).then(function (token) {
            init.headers["X-CSRF-Token"] = token;
            return window.fetch(ADMIN.url(path), init).then(function (again) {
              return again.json().then(function (againBody) {
                if (again.ok) return againBody;
                throw new ApiError(againBody.error, again.status, againBody.errors);
              });
            });
          });
        }
        if (!response.ok) {
          throw new ApiError(body && body.error, response.status, body && body.errors);
        }
        return body;
      });
    });
  }

  function redirectToLogin() {
    var api = ADMIN.API_BASE;
    var q = api ? "?api=" + encodeURIComponent(api) : "";
    if (window.location.pathname.indexOf("login.html") === -1) {
      window.location.replace("login.html" + q);
    }
  }

  window.ADMIN.Api = {
    get: function (path) { return request(path); },
    post: function (path, body) { return request(path, { method: "POST", body: body }); },
    patch: function (path, body) { return request(path, { method: "PATCH", body: body }); },
    postForm: function (path, formData) {
      return request(path, { method: "POST", body: formData, formData: true });
    },
    request: request,
    ApiError: ApiError,
    loginRedirect: redirectToLogin,
    csrf: getCsrf
  };
})();