// Override with EXPO_PUBLIC_API_URL / EXPO_PUBLIC_WEB_URL (e.g. in mobile/.env) for local testing.
export const API_URL = (process.env.EXPO_PUBLIC_API_URL ?? "https://tixgh-api.onrender.com").replace(/\/$/, "");
export const WEB_URL = (process.env.EXPO_PUBLIC_WEB_URL ?? "https://tixgh-six.vercel.app").replace(/\/$/, "");
export const SITE_NAME = process.env.EXPO_PUBLIC_SITE_NAME ?? "TixGH";
