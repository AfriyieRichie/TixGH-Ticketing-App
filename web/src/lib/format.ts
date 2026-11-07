const TZ = "Africa/Accra";

export function cedis(amount: string | number | null | undefined): string {
  const n = Number(amount ?? 0);
  return `GHS ${n.toLocaleString("en-GH", { minimumFractionDigits: n % 1 ? 2 : 0, maximumFractionDigits: 2 })}`;
}

export function priceLabel(priceFrom: string | null, isFree: boolean): string {
  if (isFree) return "Free";
  if (priceFrom === null) return "";
  return Number(priceFrom) === 0 ? "From Free" : `From ${cedis(priceFrom)}`;
}

/** "Sat 15 Nov, 7:00 PM" */
export function eventDate(iso: string, opts: { year?: boolean } = {}): string {
  const d = new Date(iso);
  const date = d.toLocaleDateString("en-GB", {
    weekday: "short", day: "numeric", month: "short", timeZone: TZ, ...(opts.year ? { year: "numeric" } : {}),
  });
  return `${date}, ${timeOnly(iso)}`;
}

export function timeOnly(iso: string): string {
  return new Date(iso).toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit", timeZone: TZ });
}

export function dayBadge(iso: string): { month: string; day: string } {
  const d = new Date(iso);
  return {
    month: d.toLocaleDateString("en-GB", { month: "short", timeZone: TZ }).toUpperCase(),
    day: d.toLocaleDateString("en-GB", { day: "numeric", timeZone: TZ }),
  };
}

/** For <input type="datetime-local">: ISO -> "YYYY-MM-DDTHH:mm" in Accra time (UTC+0, no DST). */
export function toLocalInput(iso: string | null | undefined): string {
  if (!iso) return "";
  return new Date(iso).toISOString().slice(0, 16);
}

/** "YYYY-MM-DDTHH:mm" (Accra) -> ISO string. Ghana is UTC+0 all year. */
export function fromLocalInput(value: string): string | null {
  return value ? `${value}:00Z` : null;
}

export const REGIONS: Record<string, string> = {
  ahafo: "Ahafo", ashanti: "Ashanti", bono: "Bono", bono_east: "Bono East", central: "Central",
  eastern: "Eastern", greater_accra: "Greater Accra", north_east: "North East", northern: "Northern",
  oti: "Oti", savannah: "Savannah", upper_east: "Upper East", upper_west: "Upper West", volta: "Volta",
  western: "Western", western_north: "Western North",
};
