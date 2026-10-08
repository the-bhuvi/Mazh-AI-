import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { InsightCard, RiskGauge } from "./Dashboard";
import type { Insight, Risk } from "../types/insight";

const risk: Risk = { type: "heavy_rain", score: 0.73, level: "moderate", window: { start: "", end: "" }, confidence: 0.8, reasons: ["Rain is likely"] };
const insight = { insight: { summary: "Carry an umbrella today.", recommendations: ["Allow extra travel time"], sms_text: "" } } as Insight;

describe("RiskGauge", () => {
  it("renders score and level", () => {
    render(<RiskGauge risk={risk} />);
    expect(screen.getByText("73%")).toBeInTheDocument();
    expect(screen.getByText("moderate")).toBeInTheDocument();
  });
});

describe("InsightCard", () => {
  it("renders summary and recommendations", () => {
    render(<InsightCard insight={insight} />);
    expect(screen.getByText("Carry an umbrella today.")).toBeInTheDocument();
    expect(screen.getByText("Allow extra travel time")).toBeInTheDocument();
  });
});
