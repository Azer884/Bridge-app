const p = { fill: "none", stroke: "currentColor", strokeWidth: 1.8, strokeLinecap: "round", strokeLinejoin: "round", viewBox: "0 0 24 24", "aria-hidden": true } as const;

export const IconQuotes = () => (
  <svg {...p}><path d="M5 3h10l4 4v14H5z" /><path d="M14 3v5h5M8 13h8M8 17h5" /></svg>
);
export const IconCalendar = () => (
  <svg {...p}><rect x="3.5" y="5" width="17" height="15" rx="2" /><path d="M3.5 10h17M8 3v4M16 3v4" /></svg>
);
export const IconPersona = () => (
  <svg {...p}><circle cx="12" cy="8" r="4" /><path d="M4 21c1-4 4-6 8-6s7 2 8 6" /></svg>
);
export const IconChat = () => (
  <svg {...p}><path d="M4 5h16v11H9l-5 4z" /><path d="M8 10h8M8 13h5" /></svg>
);
export const IconPipeline = () => (
  <svg {...p}><rect x="3" y="4" width="5" height="16" rx="1" /><rect x="10" y="4" width="5" height="10" rx="1" /><rect x="17" y="4" width="4" height="6" rx="1" /></svg>
);
export const IconStatus = () => (
  <svg {...p}><path d="M3 12h4l3-7 4 14 3-7h4" /></svg>
);


export const IconShield = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6l8-3z" /><path d="M9 12l2 2 4-4" /></svg>
);

/** Generic hexagon mark used beside the Orbyte name. */
export const OrbyteMark = ({ size = 18 }: { size?: number }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinejoin="round" aria-hidden="true"><path d="M12 2.5l8.2 4.75v9.5L12 21.5l-8.2-4.75v-9.5L12 2.5z" /><circle cx="12" cy="12" r="3" fill="currentColor" stroke="none" /></svg>
);
