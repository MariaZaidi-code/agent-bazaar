export function formatStatus(label, ok) {
  return `${ok ? "OK" : "ERROR"}: ${label}`;
}

export function clamp(value, min, max) {
  return Math.min(Math.max(value, min), max);
}
