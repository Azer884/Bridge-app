export interface Country {
  name: string;
  iso: string;
  dial: string; // digits only, no "+"
}

export const DEFAULT_COUNTRY = "MY";

export const COUNTRIES: Country[] = [
  { name: "Malaysia", iso: "MY", dial: "60" },
  { name: "Singapore", iso: "SG", dial: "65" },
  { name: "Indonesia", iso: "ID", dial: "62" },
  { name: "Brunei", iso: "BN", dial: "673" },
  { name: "Thailand", iso: "TH", dial: "66" },
  { name: "Vietnam", iso: "VN", dial: "84" },
  { name: "Philippines", iso: "PH", dial: "63" },
  { name: "India", iso: "IN", dial: "91" },
  { name: "Pakistan", iso: "PK", dial: "92" },
  { name: "Bangladesh", iso: "BD", dial: "880" },
  { name: "Sri Lanka", iso: "LK", dial: "94" },
  { name: "Nepal", iso: "NP", dial: "977" },
  { name: "China", iso: "CN", dial: "86" },
  { name: "Hong Kong", iso: "HK", dial: "852" },
  { name: "Taiwan", iso: "TW", dial: "886" },
  { name: "Japan", iso: "JP", dial: "81" },
  { name: "South Korea", iso: "KR", dial: "82" },
  { name: "Australia", iso: "AU", dial: "61" },
  { name: "New Zealand", iso: "NZ", dial: "64" },
  { name: "United Kingdom", iso: "GB", dial: "44" },
  { name: "Ireland", iso: "IE", dial: "353" },
  { name: "United States", iso: "US", dial: "1" },
  { name: "Canada", iso: "CA", dial: "1" },
  { name: "Mexico", iso: "MX", dial: "52" },
  { name: "Brazil", iso: "BR", dial: "55" },
  { name: "Argentina", iso: "AR", dial: "54" },
  { name: "Chile", iso: "CL", dial: "56" },
  { name: "Colombia", iso: "CO", dial: "57" },
  { name: "Peru", iso: "PE", dial: "51" },
  { name: "Germany", iso: "DE", dial: "49" },
  { name: "France", iso: "FR", dial: "33" },
  { name: "Spain", iso: "ES", dial: "34" },
  { name: "Portugal", iso: "PT", dial: "351" },
  { name: "Italy", iso: "IT", dial: "39" },
  { name: "Netherlands", iso: "NL", dial: "31" },
  { name: "Belgium", iso: "BE", dial: "32" },
  { name: "Switzerland", iso: "CH", dial: "41" },
  { name: "Austria", iso: "AT", dial: "43" },
  { name: "Sweden", iso: "SE", dial: "46" },
  { name: "Norway", iso: "NO", dial: "47" },
  { name: "Denmark", iso: "DK", dial: "45" },
  { name: "Finland", iso: "FI", dial: "358" },
  { name: "Poland", iso: "PL", dial: "48" },
  { name: "Greece", iso: "GR", dial: "30" },
  { name: "Turkey", iso: "TR", dial: "90" },
  { name: "Russia", iso: "RU", dial: "7" },
  { name: "Ukraine", iso: "UA", dial: "380" },
  { name: "United Arab Emirates", iso: "AE", dial: "971" },
  { name: "Saudi Arabia", iso: "SA", dial: "966" },
  { name: "Qatar", iso: "QA", dial: "974" },
  { name: "Kuwait", iso: "KW", dial: "965" },
  { name: "Bahrain", iso: "BH", dial: "973" },
  { name: "Oman", iso: "OM", dial: "968" },
  { name: "Jordan", iso: "JO", dial: "962" },
  { name: "Lebanon", iso: "LB", dial: "961" },
  { name: "Israel", iso: "IL", dial: "972" },
  { name: "Egypt", iso: "EG", dial: "20" },
  { name: "Morocco", iso: "MA", dial: "212" },
  { name: "Nigeria", iso: "NG", dial: "234" },
  { name: "Ghana", iso: "GH", dial: "233" },
  { name: "Kenya", iso: "KE", dial: "254" },
  { name: "Tanzania", iso: "TZ", dial: "255" },
  { name: "Uganda", iso: "UG", dial: "256" },
  { name: "South Africa", iso: "ZA", dial: "27" },
];

export const countryByIso = (iso: string) => COUNTRIES.find((c) => c.iso === iso) ?? COUNTRIES[0];

/** Build the digits-only international number. Drops a trunk "0" and any pasted country code. */
export function toE164(country: Country, national: string): string {
  let d = national.replace(/\D/g, "").replace(/^0+/, "");
  if (d.startsWith(country.dial) && d.length > country.dial.length + 6) d = d.slice(country.dial.length);
  return country.dial + d;
}

/** Longest matching dial code, so "6012345678" reads as +60 12345678. */
export function splitE164(digits: string): { country: Country | null; national: string } {
  const hit = [...COUNTRIES].sort((a, b) => b.dial.length - a.dial.length).find((c) => digits.startsWith(c.dial));
  return hit ? { country: hit, national: digits.slice(hit.dial.length) } : { country: null, national: digits };
}

export function validNational(national: string): boolean {
  const n = national.replace(/\D/g, "").replace(/^0+/, "");
  return n.length >= 6 && n.length <= 12;
}
