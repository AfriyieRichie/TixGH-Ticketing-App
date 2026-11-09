# TixGH mobile app (Expo)

One app for attendees and gate staff:

- **Events**: browse and search; "Get tickets" opens the secure web checkout (Paystack MoMo/card).
- **My tickets**: QR wallet, saved on the phone so it works at venues with no signal.
- **Scan** (organizer staff with Owner/Admin/Gate scanner role): camera QR scanning with
  full-screen ADMIT / ALREADY USED / INVALID results, torch, typed codes, per-phone gate names.
  Works offline: the event's ticket list and signing key are cached, forged QRs are rejected
  on-device, scans queue and sync every 15 s, and cross-gate duplicates are flagged.

## Run

```powershell
npm install
npx expo start      # open Expo Go on your phone and scan the QR (same Wi-Fi)
```

Uses the live API by default. Copy `.env.example` to `.env` to point at another backend.

Checks: `npx tsc --noEmit`, `npx expo lint`, `npx expo-doctor`.
