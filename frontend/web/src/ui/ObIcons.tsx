// Line icons in the style of Orbyte's menu (drawn here, not copied from Orbyte).
const p = { width: 20, height: 20, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: 1.7, strokeLinecap: "round" as const, strokeLinejoin: "round" as const, "aria-hidden": true };

export const IHome = () => <svg {...p}><path d="M4 11l8-7 8 7v9a1 1 0 01-1 1h-4v-6H9v6H5a1 1 0 01-1-1z" /></svg>;
export const IBuilding = () => <svg {...p}><rect x="4" y="3" width="16" height="18" rx="1.5" /><path d="M8 7h2M14 7h2M8 11h2M14 11h2M8 15h2M14 15h2M10 21v-3h4v3" /></svg>;
export const IUsers = () => <svg {...p}><circle cx="9" cy="8" r="3.2" /><path d="M3.5 19c.7-3.2 3-5 5.5-5s4.8 1.8 5.5 5" /><path d="M15.5 5.2a3 3 0 010 5.6M17.5 14.4c1.6.7 2.6 2.4 3 4.6" /></svg>;
export const IFolder = () => <svg {...p}><path d="M3.5 6.5a1.5 1.5 0 011.5-1.5h4l2 2h8a1.5 1.5 0 011.5 1.5v9A1.5 1.5 0 0119 19H5a1.5 1.5 0 01-1.5-1.5z" /></svg>;
export const IUserEdit = () => <svg {...p}><circle cx="10" cy="8" r="3.5" /><path d="M4 20c.6-3.5 3-5.5 6-5.5 1 0 2 .2 2.8.6M15 20l1-3 4-4 2 2-4 4z" /></svg>;
export const IWallet = () => <svg {...p}><path d="M4 7a2 2 0 012-2h11v3" /><rect x="4" y="7" width="16" height="12" rx="2" /><path d="M16 13h2" /></svg>;
export const IMail = () => <svg {...p}><rect x="3.5" y="5.5" width="17" height="13" rx="1.5" /><path d="M4 7l8 6 8-6" /></svg>;
export const ICalendar = () => <svg {...p}><rect x="4" y="5" width="16" height="15" rx="2" /><path d="M4 10h16M8 3v4M16 3v4M8 14h2M14 14h2" /></svg>;
export const IBriefcase = () => <svg {...p}><rect x="3.5" y="7" width="17" height="12" rx="2" /><path d="M9 7V5.5A1.5 1.5 0 0110.5 4h3A1.5 1.5 0 0115 5.5V7M3.5 12h17" /></svg>;
export const IGear = () => <svg {...p}><circle cx="12" cy="12" r="3" /><path d="M12 3v2.5M12 18.5V21M3 12h2.5M18.5 12H21M5.6 5.6l1.8 1.8M16.6 16.6l1.8 1.8M5.6 18.4l1.8-1.8M16.6 7.4l1.8-1.8" /></svg>;
export const IPen = () => <svg {...p}><path d="M4 20c3-1 4-4 6-4s1 3 4 3 4-3 6-3" /><path d="M14 4l4 4-7 7H7v-4z" /></svg>;
export const ISearch = () => <svg {...p}><circle cx="11" cy="11" r="6.5" /><path d="M20 20l-4.2-4.2" /></svg>;
export const IClock = () => <svg {...p} width={14} height={14}><circle cx="12" cy="12" r="8.5" /><path d="M12 7.5V12l3 2" /></svg>;
export const IChevron = ({ open }: { open?: boolean }) => (
  <svg {...p} width={18} height={18} style={{ transform: open ? "rotate(90deg)" : undefined, transition: "transform .15s" }}><path d="M9 6l6 6-6 6" /></svg>
);
export const IChevronDown = () => <svg {...p} width={18} height={18}><path d="M6 9l6 6 6-6" /></svg>;
export const IArrowOut = () => <svg {...p} width={14} height={14}><path d="M8 16L16 8M9 8h7v7" /></svg>;
