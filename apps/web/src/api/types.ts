import type { components } from "./schema";

type S = components["schemas"];

export type UserOut = S["UserOut"];
export type ProjectOut = S["ProjectOut"];
export type ProjectSummary = S["ProjectSummary"];
export type ProjectStage = ProjectOut["stage"];
export type Measurements = S["Measurements"];
export type JobOut = S["JobOut"];
export type PhotoIssue = S["PhotoIssue"];
export type PhotoVerdict = S["PhotoVerdict"];
export type PhotoUploadResult = S["PhotoUploadResult"];
export type RegionOut = S["RegionOut"];
export type RegionIn = S["RegionIn"];
export type RegionsOut = S["RegionsOut"];
export type Label = RegionOut["label"] | "canopy" | "louvers" | "compound_wall";
export type Point = [number, number];
export type ScaleOut = S["ScaleOut"];
export type ScaleConfirm = S["ScaleConfirm"];
export type ReferenceLine = S["ReferenceLine"];
export type BoxPx = S["BoxPx"];
export type MaterialOut = S["MaterialOut"];
export type MaterialAdvice = S["MaterialAdvice"];
export type MaterialAdviceOut = S["MaterialAdviceOut"];
export type DesignOut = S["DesignOut"];
export type Assignment = S["Assignment"];
export type RenderOut = S["RenderOut"];
export type RenderStarted = S["RenderStarted"];
export type QAResult = S["QAResult"];
export type EstimateOut = S["EstimateOut"];
export type Estimate = S["Estimate"];
export type LineItem = S["LineItem"];
export type CompanionLine = S["CompanionLine"];
export type SurfaceMeasure = S["SurfaceMeasure"];
export type RatesOut = S["RatesOut"];
export type RatesPut = S["RatesPut"];
export type RateOverride = S["RateOverride"];
export type Extras = S["Extras"];
export type ReportOut = S["ReportOut"];
export type AICallOut = S["AICallOut"];
export type ScaleResult = S["ScaleResult"];
export type MaterialCategory = MaterialOut["category"];

/** Body of a plain-language error (`ApiError` in renocore/schemas/contracts.py). */
export interface ApiErrorBody {
  code: string;
  message: string;
}
