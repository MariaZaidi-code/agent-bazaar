import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import utils from "../../app/web/static/utils.js";

describe("escapeHtml", () => {
  it("escapes the five HTML characters", () => {
    expect(utils.escapeHtml(`<a href="x">'&'</a>`)).toBe(
      "&lt;a href=&quot;x&quot;&gt;&#39;&amp;&#39;&lt;/a&gt;"
    );
  });

  it("handles null and undefined", () => {
    expect(utils.escapeHtml(null)).toBe("");
    expect(utils.escapeHtml(undefined)).toBe("");
  });
});

describe("clamp", () => {
  it("bounds values inside the range", () => {
    expect(utils.clamp(5, 0, 10)).toBe(5);
    expect(utils.clamp(-2, 0, 10)).toBe(0);
    expect(utils.clamp(12, 0, 10)).toBe(10);
  });

  it("falls back to the minimum for invalid input", () => {
    expect(utils.clamp("nope", 3, 9)).toBe(3);
  });
});

describe("formatPercent", () => {
  it("renders a rounded percentage by default", () => {
    expect(utils.formatPercent(0.94)).toBe("94%");
  });

  it("supports decimals", () => {
    expect(utils.formatPercent(0.9412, 1)).toBe("94.1%");
  });

  it("treats invalid values as zero", () => {
    expect(utils.formatPercent("bad")).toBe("0%");
  });
});

describe("formatDuration", () => {
  it("formats milliseconds, seconds and minutes", () => {
    expect(utils.formatDuration(750)).toBe("750 ms");
    expect(utils.formatDuration(1200)).toBe("1.2 s");
    expect(utils.formatDuration(65000)).toBe("1.1 min");
  });

  it("returns zero for empty values", () => {
    expect(utils.formatDuration(0)).toBe("0 ms");
    expect(utils.formatDuration(-4)).toBe("0 ms");
  });
});

describe("relativeTime", () => {
  const now = new Date("2026-11-07T12:00:00Z").getTime();

  it("describes recent timestamps", () => {
    expect(utils.relativeTime("2026-11-07T11:59:30Z", now)).toBe("just now");
    expect(utils.relativeTime("2026-11-07T11:58:00Z", now)).toBe("2 min ago");
    expect(utils.relativeTime("2026-11-07T10:00:00Z", now)).toBe("2 hours ago");
    expect(utils.relativeTime("2026-11-06T10:00:00Z", now)).toBe("yesterday");
  });

  it("returns an empty string for invalid dates", () => {
    expect(utils.relativeTime("not-a-date", now)).toBe("");
  });
});

describe("percentile", () => {
  it("returns median and p95 values", () => {
    const values = [10, 20, 30, 40, 50, 60, 70, 80, 90];
    expect(utils.percentile(values, 0.5)).toBe(50);
    expect(utils.percentile(values, 0.95)).toBe(90);
  });

  it("returns zero for empty input", () => {
    expect(utils.percentile([], 0.9)).toBe(0);
  });
});

describe("debounce", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("runs once after the wait period", () => {
    const spy = vi.fn();
    const debounced = utils.debounce(spy, 100);
    debounced("a");
    debounced("b");
    debounced("c");
    expect(spy).not.toHaveBeenCalled();
    vi.advanceTimersByTime(100);
    expect(spy).toHaveBeenCalledTimes(1);
    expect(spy).toHaveBeenCalledWith("c");
  });
});
