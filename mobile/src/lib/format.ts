const TZ = "Africa/Accra";

export const cedis = (v: string | number | null | undefined) => {
  const n = Number(v ?? 0);
  return n === 0 ? "Free" : `GHS ${n.toLocaleString("en-GH", { maximumFractionDigits: 2 })}`;
};

export function eventDate(iso: string): string {
  const d = new Date(iso);
  const date = d.toLocaleDateString("en-GB", { weekday: "short", day: "numeric", month: "short", timeZone: TZ });
  const time = d.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit", timeZone: TZ });
  return `${date}, ${time}`;
}

export function timeOnly(iso: string): string {
  return new Date(iso).toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit", timeZone: TZ });
}
