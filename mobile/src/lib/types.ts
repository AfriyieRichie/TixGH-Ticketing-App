export type Paginated<T> = { count: number; next: string | null; previous: string | null; results: T[] };

export type User = { id: number; full_name: string; email: string | null; phone: string | null };
export type AuthResponse = { access: string; refresh: string; is_new_user: boolean; user: User };

export type EventCard = {
  slug: string;
  title: string;
  summary: string;
  cover_image: string | null;
  category: { name: string; slug: string } | null;
  start_at: string;
  end_at: string;
  venue: { name: string; city: string; region: string } | null;
  organizer: { name: string; slug: string; is_verified: boolean };
  price_from: string | null;
  is_free: boolean;
  sold_out: boolean;
};

export type EventDetail = EventCard & {
  description: string;
  venue: { name: string; address: string; city: string; directions: string; digital_address: string } | null;
  ticket_types: { id: number; name: string; sale_status: string; pricing: { buyer_pays: string } }[];
  status: string;
  has_ended: boolean;
};

export type WalletTicket = {
  code: string;
  qr_payload: string | null;
  ticket_type_name: string;
  admits: number;
  attendee_name: string;
  status: "valid" | "checked_in" | "void";
  checked_in_at: string | null;
  event: { slug: string; title: string; start_at: string; when: string; where: string; status: string; online_url: string };
};

export type ScanEvent = {
  slug: string;
  title: string;
  start_at: string;
  end_at: string;
  when: string;
  where: string;
  status: string;
  organization: string;
  stats: Stats;
};

export type Stats = { tickets: number; checked_in: number; people: number; people_in: number };

export type ManifestTicket = {
  id: number;
  code: string;
  type: string;
  admits: number;
  name: string;
  status: "valid" | "checked_in" | "void";
  checked_in_at: string | null;
};

export type ScanResultKind = "ok" | "duplicate" | "invalid" | "transferred" | "void" | "wrong_event" | "event_cancelled";

export type ScanResponse = {
  result: ScanResultKind;
  message: string;
  scanned_at: string;
  ticket: ManifestTicket | null;
  previous?: { at: string; gate: string };
  stats?: Stats;
};
