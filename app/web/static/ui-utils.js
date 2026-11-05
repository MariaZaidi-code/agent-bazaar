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

export function average(values) {
  if (!values || !values.length) return 0;
  return values.reduce((sum, value) => sum + Number(value || 0), 0) / values.length;
}

export function groupBy(items, key) {
  return (items || []).reduce((groups, item) => {
    const groupKey = typeof key === "function" ? key(item) : item?.[key];
    groups[groupKey] = groups[groupKey] || [];
    groups[groupKey].push(item);
    return groups;
  }, {});
}

export function sortBy(items, key, direction = "asc") {
  const factor = direction === "desc" ? -1 : 1;
  return [...(items || [])].sort((a, b) => {
    const left = typeof key === "function" ? key(a) : a?.[key];
    const right = typeof key === "function" ? key(b) : b?.[key];
    return left > right ? factor : left < right ? -factor : 0;
  });
}

export function isEmptyObject(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value) && Object.keys(value).length === 0;
}

export function formatDuration(milliseconds) {
  if (!Number.isFinite(milliseconds)) return "0 ms";
  if (milliseconds < 1000) return `${Math.round(milliseconds)} ms`;
  return `${(milliseconds / 1000).toFixed(2)} s`;
}

export function capitalize(value) {
  const text = String(value ?? "");
  return text ? text.charAt(0).toUpperCase() + text.slice(1) : text;
}

export function omit(obj, keys) {
  const omitted = new Set(keys || []);
  return Object.keys(obj || {}).reduce((result, key) => {
    if (!omitted.has(key)) result[key] = obj[key];
    return result;
  }, {});
}

export function chunk(items, size) {
  const result = [];
  for (let index = 0; index < (items || []).length; index += size) {
    result.push((items || []).slice(index, index + size));
  }
  return result;
}
