export function formatStatus(label, ok) {
  return `${ok ? "OK" : "ERROR"}: ${label}`;
}

export function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max);
}

export function titleCase(value) {
  return String(value)
    .split(/[\s_-]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1).toLowerCase())
    .join(" ");
}

export function isNonEmpty(value) {
  return String(value ?? "").trim().length > 0;
}

export function safeNumber(value, fallback = 0) {
  const number = Number(value);
  return Number.isFinite(number) ? number : fallback;
}

export function percent(value, total) {
  if (!total) return 0;
  return Math.round((value / total) * 100);
}

export function unique(items) {
  return [...new Set(items)];
}

export function truncate(value, length) {
  const text = String(value ?? "");
  return text.length <= length ? text : `${text.slice(0, Math.max(0, length - 1))}…`;
}

export function slugify(value) {
  return String(value ?? "")
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");
}

export function pick(obj, keys) {
  return keys.reduce((result, key) => {
    if (Object.prototype.hasOwnProperty.call(obj || {}, key)) result[key] = obj[key];
    return result;
  }, {});
}
