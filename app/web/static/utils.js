(function (root, factory) {
  if (typeof module === "object" && module.exports) {
    module.exports = factory();
  } else {
    root.ABUtils = factory();
  }
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>"']/g, function (character) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[character];
    });
  }

  function clamp(value, min, max) {
    var number = Number(value);
    if (!Number.isFinite(number)) return min;
    return Math.min(max, Math.max(min, number));
  }

  function formatPercent(value, digits) {
    var number = Number(value);
    if (!Number.isFinite(number)) number = 0;
    return (number * 100).toFixed(digits === undefined ? 0 : digits) + "%";
  }

  function formatDuration(milliseconds) {
    var value = Number(milliseconds);
    if (!Number.isFinite(value) || value <= 0) return "0 ms";
    if (value < 1000) return Math.round(value) + " ms";
    if (value < 60000) return (value / 1000).toFixed(value < 10000 ? 1 : 0) + " s";
    return (value / 60000).toFixed(1) + " min";
  }

  function relativeTime(value, now) {
    var then = value instanceof Date ? value.getTime() : new Date(value).getTime();
    if (!Number.isFinite(then)) return "";
    var reference = now === undefined ? Date.now() : now instanceof Date ? now.getTime() : Number(now);
    var seconds = Math.max(0, Math.round((reference - then) / 1000));
    if (seconds < 45) return "just now";
    if (seconds < 90) return "1 min ago";
    if (seconds < 3600) return Math.round(seconds / 60) + " min ago";
    if (seconds < 7200) return "1 hour ago";
    if (seconds < 86400) return Math.round(seconds / 3600) + " hours ago";
    if (seconds < 172800) return "yesterday";
    return Math.round(seconds / 86400) + " days ago";
  }

  function percentile(values, fraction) {
    if (!values || !values.length) return 0;
    var ordered = values.slice().sort(function (a, b) {
      return a - b;
    });
    var index = Math.min(ordered.length - 1, Math.max(0, Math.round((ordered.length - 1) * fraction)));
    return ordered[index];
  }

  function debounce(fn, wait) {
    var timer = null;
    return function () {
      var args = arguments;
      var self = this;
      if (timer) clearTimeout(timer);
      timer = setTimeout(function () {
        timer = null;
        fn.apply(self, args);
      }, wait);
    };
  }

  return {
    escapeHtml: escapeHtml,
    clamp: clamp,
    formatPercent: formatPercent,
    formatDuration: formatDuration,
    relativeTime: relativeTime,
    percentile: percentile,
    debounce: debounce,
  };
});
