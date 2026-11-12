/* ==========================================================================
 * Administrator area: sidebar toggle and lightweight canvas charts.
 * No external chart library is used, so the dashboard works offline.
 * ========================================================================= */
(function () {
  "use strict";

  // ---------------------------------------------------------------- sidebar
  function initSidebar() {
    var toggle = document.getElementById("admin-menu-toggle");
    var sidebar = document.getElementById("admin-sidebar");
    if (!toggle || !sidebar) return;
    toggle.addEventListener("click", function (e) {
      e.stopPropagation();
      sidebar.classList.toggle("open");
    });
    document.addEventListener("click", function (e) {
      if (window.innerWidth > 900) return;
      if (!sidebar.classList.contains("open")) return;
      if (sidebar.contains(e.target) || toggle.contains(e.target)) return;
      sidebar.classList.remove("open");
    });
  }

  // ----------------------------------------------------------------- colours
  var PALETTE = {
    submitted: "#3b82f6",
    under_review: "#f59e0b",
    correction_requested: "#f97316",
    approved: "#22c55e",
    rejected: "#ef4444",
    Degree: "#6366f1",
    Diploma: "#14b8a6",
    default: "#64748b"
  };

  function colorFor(item, index) {
    if (item && item.key && PALETTE[item.key]) return PALETTE[item.key];
    if (item && PALETTE[item.label]) return PALETTE[item.label];
    var fallback = ["#6366f1", "#14b8a6", "#f59e0b", "#ef4444", "#3b82f6", "#8b5cf6"];
    return fallback[index % fallback.length];
  }

  function readValues(canvas) {
    try {
      var raw = canvas.getAttribute("data-values");
      var data = raw ? JSON.parse(raw) : [];
      return Array.isArray(data) ? data : [];
    } catch (err) {
      return [];
    }
  }

  function prepare(canvas) {
    var ratio = window.devicePixelRatio || 1;
    var rect = canvas.getBoundingClientRect();
    var width = rect.width || canvas.parentNode.clientWidth || 320;
    var height = parseInt(canvas.getAttribute("height") || "220", 10);
    canvas.width = width * ratio;
    canvas.height = height * ratio;
    canvas.style.height = height + "px";
    var ctx = canvas.getContext("2d");
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    ctx.clearRect(0, 0, width, height);
    ctx.font = "12px 'Segoe UI', system-ui, sans-serif";
    return { ctx: ctx, width: width, height: height };
  }

  function renderDonut(canvas, data) {
    var g = prepare(canvas);
    var ctx = g.ctx;
    var total = data.reduce(function (sum, item) { return sum + (item.value || 0); }, 0);
    var cx = g.width / 2;
    var cy = g.height / 2;
    var radius = Math.min(g.width, g.height) / 2 - 10;
    var inner = radius * 0.6;

    if (!total) {
      ctx.fillStyle = "#94a3b8";
      ctx.textAlign = "center";
      ctx.fillText("No data", cx, cy);
      return;
    }

    var start = -Math.PI / 2;
    data.forEach(function (item, index) {
      var value = item.value || 0;
      if (!value) return;
      var angle = (value / total) * Math.PI * 2;
      ctx.beginPath();
      ctx.moveTo(cx, cy);
      ctx.arc(cx, cy, radius, start, start + angle);
      ctx.closePath();
      ctx.fillStyle = colorFor(item, index);
      ctx.fill();
      start += angle;
    });

    // Punch the hole to make it a donut.
    ctx.beginPath();
    ctx.arc(cx, cy, inner, 0, Math.PI * 2);
    ctx.fillStyle = "#ffffff";
    ctx.fill();

    ctx.fillStyle = "#1f2937";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.font = "700 20px 'Segoe UI', system-ui, sans-serif";
    ctx.fillText(String(total), cx, cy - 6);
    ctx.font = "11px 'Segoe UI', system-ui, sans-serif";
    ctx.fillStyle = "#6b7280";
    ctx.fillText("total", cx, cy + 12);
  }

  function renderBar(canvas, data) {
    var g = prepare(canvas);
    var ctx = g.ctx;
    var pad = { top: 12, right: 12, bottom: 34, left: 30 };
    var plotW = g.width - pad.left - pad.right;
    var plotH = g.height - pad.top - pad.bottom;
    var max = Math.max.apply(null, data.map(function (d) { return d.value || 0; })).valueOf();
    if (!isFinite(max) || max <= 0) max = 1;

    // Axis
    ctx.strokeStyle = "#e5e7eb";
    ctx.beginPath();
    ctx.moveTo(pad.left, pad.top);
    ctx.lineTo(pad.left, pad.top + plotH);
    ctx.lineTo(pad.left + plotW, pad.top + plotH);
    ctx.stroke();

    var barGap = 8;
    var barW = data.length ? (plotW - barGap * (data.length - 1)) / data.length : plotW;

    data.forEach(function (item, index) {
      var value = item.value || 0;
      var h = (value / max) * plotH;
      var x = pad.left + index * (barW + barGap);
      var y = pad.top + plotH - h;
      ctx.fillStyle = colorFor(item, index);
      ctx.fillRect(x, y, Math.max(2, barW), h);

      ctx.fillStyle = "#1f2937";
      ctx.textAlign = "center";
      ctx.textBaseline = "bottom";
      ctx.font = "600 11px 'Segoe UI', system-ui, sans-serif";
      ctx.fillText(String(value), x + barW / 2, y - 2);

      ctx.fillStyle = "#6b7280";
      ctx.textBaseline = "top";
      ctx.font = "10px 'Segoe UI', system-ui, sans-serif";
      var label = String(item.label || "");
      if (label.length > 8) label = label.slice(0, 7) + "\u2026";
      ctx.fillText(label, x + barW / 2, pad.top + plotH + 6);
    });
  }

  function renderLine(canvas, data) {
    var g = prepare(canvas);
    var ctx = g.ctx;
    var pad = { top: 16, right: 14, bottom: 30, left: 30 };
    var plotW = g.width - pad.left - pad.right;
    var plotH = g.height - pad.top - pad.bottom;
    var max = Math.max.apply(null, data.map(function (d) { return d.value || 0; }).concat([1]));

    ctx.strokeStyle = "#e5e7eb";
    ctx.beginPath();
    ctx.moveTo(pad.left, pad.top);
    ctx.lineTo(pad.left, pad.top + plotH);
    ctx.lineTo(pad.left + plotW, pad.top + plotH);
    ctx.stroke();

    var step = data.length > 1 ? plotW / (data.length - 1) : 0;
    var points = data.map(function (item, index) {
      var x = pad.left + index * step;
      var y = pad.top + plotH - ((item.value || 0) / max) * plotH;
      return { x: x, y: y, item: item };
    });

    ctx.strokeStyle = "#1d4ed8";
    ctx.lineWidth = 2;
    ctx.beginPath();
    points.forEach(function (p, i) {
      if (i === 0) ctx.moveTo(p.x, p.y);
      else ctx.lineTo(p.x, p.y);
    });
    ctx.stroke();

    points.forEach(function (p) {
      ctx.beginPath();
      ctx.arc(p.x, p.y, 3.5, 0, Math.PI * 2);
      ctx.fillStyle = "#1d4ed8";
      ctx.fill();

      ctx.fillStyle = "#6b7280";
      ctx.textAlign = "center";
      ctx.textBaseline = "top";
      ctx.font = "10px 'Segoe UI', system-ui, sans-serif";
      ctx.fillText(String(p.item.label || p.item.month || ""), p.x, pad.top + plotH + 6);
    });
  }

  function drawAll() {
    var canvases = document.querySelectorAll("canvas[data-chart]");
    Array.prototype.forEach.call(canvases, function (canvas) {
      var kind = canvas.getAttribute("data-chart");
      var data = readValues(canvas);
      if (kind === "donut") renderDonut(canvas, data);
      else if (kind === "bar") renderBar(canvas, data);
      else if (kind === "line") renderLine(canvas, data);
    });
  }

  var resizeTimer = null;
  function initCharts() {
    if (!document.querySelector("canvas[data-chart]")) return;
    drawAll();
    window.addEventListener("resize", function () {
      clearTimeout(resizeTimer);
      resizeTimer = setTimeout(drawAll, 150);
    });
  }

  function boot() {
    initSidebar();
    initCharts();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
