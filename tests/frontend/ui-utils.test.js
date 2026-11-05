import { describe, it, expect } from "vitest";
import { formatStatus, clamp } from "../../app/web/static/ui-utils.js";

describe("ui utils", () => {
  it("formats status", () => {
    expect(formatStatus("provider", true)).toBe("OK: provider");
  });

  it("clamps values", () => {
    expect(clamp(150, 0, 100)).toBe(100);
  });
});
