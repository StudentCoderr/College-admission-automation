/* =========================================================================
   config.js — central configuration for the frontend
   -------------------------------------------------------------------------
   USE_SAMPLE_DATA = true  -> the UI uses the empty preview data in sample-data.js.
   USE_SAMPLE_DATA = false -> every call goes to the Flask backend at
                              API_BASE_URL using the endpoint map below.

   Nothing in this file touches a database. All network access is centralised
   in api.js.
   ========================================================================= */
window.APP_CONFIG = {
  COLLEGE_NAME: "Evergreen Institute of Technology",
  COLLEGE_SHORT: "Evergreen",

  // This project starts blank and talks to the Flask API by default.
  // Set to true only if you deliberately add sample data back.
  USE_SAMPLE_DATA: false,

  // Flask API base URL (used only when USE_SAMPLE_DATA is false).
  API_BASE_URL: "http://localhost:5000/api",

  // localStorage keys
  STORAGE: {
    SESSION: "cas.session",
    MY_APPLICATIONS: "cas.myApplications",
    CSRF: "cas.csrfToken"
  },

  REQUEST_TIMEOUT_MS: 15000,

  // Endpoint map — the contract the Flask backend should implement.
  ENDPOINTS: {
    csrf:             { method: "GET",  path: "/auth/csrf" },
    login:            { method: "POST", path: "/auth/login" },
    register:         { method: "POST", path: "/auth/register" },
    logout:           { method: "POST", path: "/auth/logout" },
    me:               { method: "GET",  path: "/auth/me" },
    courses:          { method: "GET",  path: "/courses" },
    announcements:    { method: "GET",  path: "/announcements" },
    applications:     { method: "GET",  path: "/applications" },
    applicationCreate:{ method: "POST", path: "/applications" },
    application:      { method: "GET",  path: "/applications/:id" },
    applicationUpdate:{ method: "PUT",  path: "/applications/:id" },
    applicationSubmit:{ method: "POST", path: "/applications/:id/submit" },
    applicationStatus:{ method: "POST", path: "/admin/applications/:id/status" },
    documents:        { method: "GET",  path: "/applications/:id/documents" },
    documentUpload:   { method: "POST", path: "/applications/:id/documents" },
    track:            { method: "POST", path: "/applications/track" },
    adminStats:       { method: "GET",  path: "/admin/stats" }
  }
};
