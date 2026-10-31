/** Public holidays the crew does not work, as shown on the Orbyte leave calendar for this organization (October to December 2026).
 * The same list sits in config/holidays.json for the chat, which refuses these days. Add a year by adding rows there. */
export interface Holiday {
  date: string; // YYYY-MM-DD
  name: string;
  country: string;
}

export const HOLIDAYS: Holiday[] = [
  { date: "2026-10-29", name: "Sultan of Kelantan Birthday", country: "MY" },
  { date: "2026-10-30", name: "Sultan of Kelantan Birthday", country: "MY" },
  { date: "2026-11-06", name: "Sultan of Perak Birthday", country: "MY" },
  { date: "2026-12-11", name: "Sultan of Selangor Birthday", country: "MY" },
  { date: "2026-12-24", name: "Christmas Eve", country: "MY" },
  { date: "2026-12-25", name: "Christmas Day", country: "MY" },
];

export const holidaysOn = (isoDate: string): Holiday[] => HOLIDAYS.filter((h) => h.date === isoDate);
