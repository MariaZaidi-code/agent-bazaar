import { describe, it, expect } from "vitest";
import {
  formatStatus,
  clamp,
  titleCase,
  isNonEmpty,
  safeNumber,
  percent,
  unique,
  truncate,
  slugify,
  pick,
  average,
  groupBy,
  sortBy,
  isEmptyObject,
  formatDuration,
  capitalize,
  omit,
  chunk,
} from "../../app/web/static/ui-utils.js";

describe("ui utils", () => {
  it("formats status", () => expect(formatStatus("provider", true)).toBe("OK: provider"));
  it("clamps values", () => expect(clamp(150, 0, 100)).toBe(100));
  it("title-cases labels", () => expect(titleCase("provider_health")).toBe("Provider Health"));
  it("checks non-empty values", () => {
    expect(isNonEmpty("  text  ")).toBe(true);
    expect(isNonEmpty("   ")).toBe(false);
  });
  it("falls back for invalid numbers", () => expect(safeNumber("abc", 7)).toBe(7));
  it("calculates percentages", () => expect(percent(3, 4)).toBe(75));
  it("removes duplicates", () => expect(unique([1, 1, 2])).toEqual([1, 2]));
  it("truncates long text", () => expect(truncate("abcdefghijklmnopqrstuvwxyz", 8)).toBe("abcdefg…"));
  it("slugifies values", () => expect(slugify("Provider Health Score!")).toBe("provider-health-score"));
  it("picks requested keys", () => expect(pick({ a: 1, b: 2, c: 3 }, ["a", "c", "missing"])).toEqual({ a: 1, c: 3 }));
  it("averages values", () => expect(average([1, 2, 3])).toBe(2));
  it("groups items", () => expect(Object.keys(groupBy([{ type: "a" }, { type: "b" }, { type: "a" }], "type"))).toEqual(["a", "b"]));
  it("sorts items", () => expect(sortBy([{ n: 2 }, { n: 1 }], "n").map((item) => item.n)).toEqual([1, 2]));
  it("detects empty objects", () => expect(isEmptyObject({})).toBe(true));
  it("formats durations", () => expect(formatDuration(1500)).toBe("1.50 s"));
  it("capitalizes text", () => expect(capitalize("agent")).toBe("Agent"));
  it("omits keys", () => expect(omit({ a: 1, b: 2 }, ["b"])).toEqual({ a: 1 }));
  it("chunks arrays", () => expect(chunk([1, 2, 3, 4], 2)).toEqual([[1, 2], [3, 4]]));
});
