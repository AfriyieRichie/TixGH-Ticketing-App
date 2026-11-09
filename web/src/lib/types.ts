export type Paginated<T> = { count: number; next: string | null; previous: string | null; results: T[] };

export type Category = { name: string; slug: string; icon: string };

export type Pricing = {
  price: string;
  fee: string;
  buyer_pays: string;
  organizer_receives: string;
  fee_bearer: "buyer" | "organizer";
};

export type SaleStatus = "on_sale" | "scheduled" | "ended" | "sold_out" | "unavailable";

export type PublicTicketType = {
  id: number;
  name: string;
  description: string;
  admits: number;
  min_per_order: number;
  max_per_order: number;
  sales_start_at: string | null;
  sales_end_at: string | null;
  sale_status: SaleStatus;
  pricing: Pricing;
  remaining: number | null;
};

export type EventCardData = {
  slug: string;
  title: string;
  summary: string;
  cover_image: string | null;
  category: Category | null;
  format: "in_person" | "online" | "hybrid";
  start_at: string;
  end_at: string;
  venue: { name: string; city: string; region: string } | null;
  organizer: { name: string; slug: string; logo: string | null; is_verified: boolean };
  price_from: string | null;
  is_free: boolean;
  sold_out: boolean;
  is_featured: boolean;
  status: string;
};

export type EventDetail = Omit<EventCardData, "venue"> & {
  venue: {
    name: string;
    address: string;
    city: string;
    region: string;
    digital_address: string;
    latitude: string | null;
    longitude: string | null;
    directions: string;
  } | null;
  description: string;
  ticket_types: PublicTicketType[];
  age_restriction: number;
  max_tickets_per_order: number;
  allow_transfers: boolean;
  reentry_allowed: boolean;
  max_reentries: number | null;
  reentry_cutoff_at: string | null;
  refund_policy: string;
  refund_policy_details: string;
  has_ended: boolean;
  cancellation_reason: string;
  organizer_description: string;
};

export type User = {
  id: number;
  full_name: string;
  email: string | null;
  phone: string | null;
  email_verified: boolean;
  phone_verified: boolean;
  marketing_opt_in: boolean;
  has_password: boolean;
};

export type AuthResponse = { access: string; refresh: string; is_new_user: boolean; user: User };

export type OrderTicket = {
  code: string;
  qr_payload: string | null;
  ticket_type_name: string;
  admits: number;
  attendee_name: string;
  status: "valid" | "checked_in" | "void";
  checked_in_at: string | null;
  transferred: boolean;
};

export type Order = {
  reference: string;
  access_token: string;
  status: "pending" | "paid" | "expired" | "failed" | "cancelled" | "refunded" | "needs_review";
  event: { slug: string; title: string; start_at: string; end_at: string; cover_image: string | null;
    venue_name: string | null; venue_city: string | null };
  buyer_name: string;
  buyer_email: string;
  buyer_phone: string;
  items: { ticket_type: number; ticket_type_name: string; quantity: number; unit_list_price: string;
    unit_price: string; unit_fee: string; unit_buyer_pays: string; line_total: string }[];
  promo_code: string | null;
  subtotal: string;
  discount_total: string;
  fee_total: string;
  total: string;
  expires_at: string;
  seconds_left: number;
  paid_at: string | null;
  payment: { reference: string; status: string; gateway: string; authorization_url: string;
    access_code: string; channel: string } | null;
  tickets: OrderTicket[];
  links: { tickets_page: string; pdf: string; whatsapp_share: string } | null;
};

export type WalletTicket = {
  code: string;
  qr_payload: string | null;
  ticket_type_name: string;
  admits: number;
  attendee_name: string;
  status: "valid" | "checked_in" | "void";
  checked_in_at: string | null;
  event: { slug: string; title: string; start_at: string; end_at: string; status: string; when: string;
    where: string; cover_image: string | null; online_url: string };
  page_url: string;
  can_transfer: boolean;
};

export type Organization = {
  id: number;
  name: string;
  slug: string;
  description: string;
  logo: string | null;
  email: string;
  phone: string;
  website: string;
  instagram: string;
  x_handle: string;
  facebook: string;
  tiktok: string;
  region: string;
  city: string;
  verification_status: "unverified" | "pending" | "verified" | "rejected";
  verification_note: string;
  fee_bearer: string;
  my_role: string | null;
  my_permissions: string[];
};

export type Venue = {
  id: number; name: string; address: string; city: string; region: string; digital_address: string;
  directions: string; capacity: number | null;
};

export type TicketType = {
  id: number;
  name: string;
  description: string;
  price: string;
  quantity: number;
  quantity_sold: number;
  quantity_available: number;
  admits: number;
  min_per_order: number;
  max_per_order: number;
  sales_start_at: string | null;
  sales_end_at: string | null;
  visibility: "visible" | "hidden";
  sort_order: number;
  is_active: boolean;
  sale_status: SaleStatus;
  pricing: Pricing;
};

export type OrgEvent = {
  id: number;
  slug: string;
  title: string;
  summary: string;
  description: string;
  category: string | null;
  cover_image: string | null;
  format: "in_person" | "online" | "hybrid";
  venue: number | null;
  venue_detail: Venue | null;
  online_url: string;
  start_at: string;
  end_at: string;
  status: "draft" | "published" | "cancelled";
  visibility: "public" | "unlisted";
  age_restriction: number;
  max_tickets_per_order: number;
  fee_bearer: string;
  effective_fee_bearer: string;
  allow_transfers: boolean;
  reentry_allowed: boolean;
  max_reentries: number | null;
  reentry_cutoff_at: string | null;
  refund_policy: string;
  refund_policy_details: string;
  is_featured: boolean;
  published_at: string | null;
  cancellation_reason: string;
  ticket_types: TicketType[];
  tickets_sold: number;
  has_ended: boolean;
  publish_problems: string[];
};

export type PromoCode = {
  id: number; code: string; discount_type: "percent" | "fixed" | "none"; amount: string;
  ticket_types: number[]; max_uses: number | null; times_used: number; valid_from: string | null;
  valid_until: string | null; is_active: boolean;
};

export type PublicConfig = {
  platform_name: string;
  currency: string;
  fees: { percent: string; flat: string; cap: string | null; default_bearer: string };
  regions: { value: string; label: string }[];
  mobile_money_providers: { value: string; label: string }[];
};
