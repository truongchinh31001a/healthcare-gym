export type UserRole = "admin" | "user";
export interface User { id: string; email: string; role: UserRole }
export interface HealthResponse { status: "ok"; service: "api" | "ai-service" }
export interface AuthResponse { user: User; access_token: string | null; csrf_token: string | null; expires_at: string }
export type Purpose = "health_data_processing" | "document_processing" | "body_image_processing" | "admin_support" | "research_training";
export interface Consent { purpose: Purpose; granted: boolean; policy_version: string }
export interface Profile { id: string; version: number; display_name: string; birth_date: string; height_cm: number; gender: "male" | "female" | "unspecified"; timezone: string }
export type TriState = "unknown" | "no" | "yes";
export interface HealthContext { version: number; pregnancy: TriState; eating_disorder_risk: TriState; clinician_restrictions: TriState; acute_red_flags: TriState; notes: string }
export interface Page<T> { items: T[]; total: number; offset: number; limit: number }
export interface Observation { id: string; version: number; observation_id: string; field: string; value: number; unit: string; measured_at: string | null; recorded_at: string; source: string; provenance: "observed" | "extracted" | "inferred" | "declared"; verification_status: string; device_model: string; supersedes_observation_id?: string; quality_flags: string[] }
export interface Point { day: string; value: number | null; flags: string[]; observation_ids: string[] }
export interface Series { stream_id: string; field: string; unit: string; source: string; provenance: string; verification_band: string; device_model: string; device_id: string; reviewed_measurement: boolean; latest: Point | null; days: Point[]; weekly: { week_start: string; median: number; days_with_values: number; flags: string[] }[]; trend: { status: "withheld" | "descriptive_only"; slope_per_week: number | null; withheld_reasons: string[] }; recent_week_comparison: { change: number | null; change_unit: string } }
export interface Progress { subject_id: string; report_timezone: string; as_of: string; synthetic_only: boolean; series: Series[]; quality_summary: Record<string, unknown>; clinical_interpretation: false }
export interface Document { id: string; version: number; mime: string; bytes: number; created_at: string; expires_at: string }
export interface Draft { id: string; version: number; status: string; extraction: { measured_at: string | null; field_evidence: Record<string, unknown>; [key: string]: unknown }; required_acknowledgements: string[] }
export interface Goal { id: string; version: number; status: string; reasons: string[]; target_weight_kg: number; current_weight_kg: number | null; weight_stream_id: string | null; weeks: number; screened_at: string; automatic_plan_authorized: false }
export interface CapabilityGate { enabled: boolean; reason: string }
export interface Capabilities { manual_measurements: boolean; report_transcription_and_review: boolean; ocr: CapabilityGate; body_cv: CapabilityGate; generative_planner: CapabilityGate; rule_version: string }
export interface Overview { users: number; documents: number; observations: number; capabilities: Capabilities }
export interface AdminUser extends User { support_access: boolean }
export interface PlannerContext { facts: { field: string; stream_id: string; [key: string]: unknown }[]; needs_source_selection: unknown[]; missing_or_withheld_stream_ids: string[]; plan_generation_authorized: false; requires_safety_screening: true }
export const fields = {
 weight_kg: { label: "Cân nặng", unit: "kg", method: "scale" },
 waist_cm: { label: "Vòng eo", unit: "cm", method: "tape" },
 chest_cm: { label: "Vòng ngực", unit: "cm", method: "tape" },
 hip_cm: { label: "Vòng hông", unit: "cm", method: "tape" },
 height_cm: { label: "Chiều cao", unit: "cm", method: "tape" },
 skeletal_muscle_mass_kg: { label: "Khối cơ xương", unit: "kg", method: "device_report" },
 body_fat_mass_kg: { label: "Khối mỡ", unit: "kg", method: "device_report" },
 percent_body_fat: { label: "Tỷ lệ mỡ", unit: "%", method: "device_report" },
 total_body_water_l: { label: "Tổng nước", unit: "L", method: "device_report" },
 ecw_tbw_ratio: { label: "ECW/TBW", unit: "ratio", method: "device_report" },
 basal_metabolic_rate_kcal: { label: "BMR", unit: "kcal/day", method: "device_report" },
 bmi: { label: "BMI", unit: "kg/m2", method: "device_report" },
} as const;
export type FieldName = keyof typeof fields;
export function fieldLabel(key: string) { return fields[key as FieldName]?.label ?? key }
