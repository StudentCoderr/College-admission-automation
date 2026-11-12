/* =========================================================================
   sample-data.js — intentionally empty
   -------------------------------------------------------------------------
   This project no longer ships demo members, demo applications or sample
   courses. The static frontend talks to the Flask API by default
   (APP_CONFIG.USE_SAMPLE_DATA = false).

   The arrays below stay empty so the preview UI renders its normal empty
   states instead of pretending a database exists.
   ========================================================================= */
window.SampleData = (function () {
  "use strict";

  const college = {
    name: "College Admission Portal",
    tagline: "Apply online, track your application and manage admissions",
    about:
      "This admission portal is ready for your institution's real data. " +
      "Sign in as an administrator to add courses and announcements.",
    stats: [],
    contact: {
      address: "",
      phone: "",
      email: ""
    }
  };

  const announcements = [];
  const courses = [];
  const accounts = [];
  const applications = [];
  const statusSequence = ["draft", "submitted", "under_review", "approved"];

  return {
    college,
    announcements,
    courses,
    accounts,
    applications,
    statusSequence,
    findCourse: (id) => courses.find((c) => c.id === id) || null,
    findApplication: (id) =>
      applications.find((a) => a.id === id || a.number === id) || null
  };
})();
