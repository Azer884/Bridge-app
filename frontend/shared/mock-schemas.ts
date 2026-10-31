import type { ExtractedParams, ParamField } from "./types";

/** Form layouts. In live mode the backend sends the schema with each quote. */
export const SCHEMAS: Record<ExtractedParams["kind"], ParamField[]> = {
  painting: [
    { key: "length_m", label: "Room length", type: "number", unit: "m", min: 0.5, max: 30, step: 0.1 },
    { key: "width_m", label: "Room width", type: "number", unit: "m", min: 0.5, max: 30, step: 0.1 },
    { key: "height_m", label: "Ceiling height", type: "number", unit: "m", min: 1.8, max: 8, step: 0.1 },
    {
      key: "surface_condition", label: "Surface condition", type: "select",
      options: [{ value: "good", label: "Good" }, { value: "fair", label: "Fair, small repairs" }, { value: "poor", label: "Poor, heavy prep" }],
    },
    { key: "coats", label: "Coats", type: "number", min: 1, max: 4, step: 1, integer: true },
    {
      key: "tier", label: "Paint tier", type: "select",
      options: [{ value: "economy", label: "Economy" }, { value: "standard", label: "Standard" }, { value: "premium", label: "Premium" }],
    },
  ],
  aircon: [
    { key: "unit_count", label: "Aircon units", type: "number", min: 1, max: 20, step: 1, integer: true },
    {
      key: "service_type", label: "Service", type: "select",
      options: [{ value: "general_service", label: "General service" }, { value: "chemical_wash", label: "Chemical wash" }, { value: "chemical_overhaul", label: "Chemical overhaul" }],
    },
    {
      key: "horsepower", label: "Horsepower", type: "select",
      options: [{ value: "1.0hp", label: "1.0 HP" }, { value: "1.5hp", label: "1.5 HP" }, { value: "2.0hp", label: "2.0 HP" }, { value: "2.5hp", label: "2.5 HP" }, { value: "3.0hp", label: "3.0 HP" }],
    },
  ],
  plumbing: [
    { key: "labour_hours", label: "Labour", type: "number", unit: "h", min: 0.5, max: 40, step: 0.5, help: "Time on site for one plumber." },
    { key: "parts_cost", label: "Parts and fittings", type: "number", unit: "MYR", min: 0, max: 20000, step: 1 },
    {
      key: "urgency", label: "Urgency", type: "select",
      options: [{ value: "standard", label: "Standard" }, { value: "same_day", label: "Same day, +25% labour" }],
    },
  ],
  general: [
    { key: "crew_days", label: "Crew days", type: "number", unit: "days", min: 0.5, max: 60, step: 0.5 },
    { key: "materials_cost", label: "Materials", type: "number", unit: "MYR", min: 0, max: 200000, step: 10 },
    { key: "specialist_cost", label: "Specialist work", type: "number", unit: "MYR", min: 0, max: 100000, step: 10, help: "Licensed electrician, tiler and similar." },
  ],
};
