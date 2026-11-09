import { Tabs } from "expo-router";
import { useEffect, useState } from "react";
import { AppState, Text, type ColorValue } from "react-native";

import { C } from "@/constants/theme";
import { useAuth } from "@/lib/auth";
import type { ScanEvent } from "@/lib/types";

function TabIcon({ glyph, color }: { glyph: string; color: ColorValue }) {
  return <Text style={{ fontSize: 20, color }}>{glyph}</Text>;
}
const icon = (glyph: string) => function Icon({ color }: { color: ColorValue }) {
  return <TabIcon glyph={glyph} color={color} />;
};

export default function TabsLayout() {
  const { user, request } = useAuth();
  const [hasScanEvents, setHasScanEvents] = useState(false);

  // Show the Scan tab only to organizer staff who have something to scan.
  // Re-checked whenever the app comes back to the foreground, so newly added
  // team members see the tab without signing out and in again.
  useEffect(() => {
    if (!user) return;
    const check = () =>
      request<ScanEvent[]>("/scanner/events/").then((e) => setHasScanEvents(e.length > 0)).catch(() => {});
    check();
    const sub = AppState.addEventListener("change", (state) => {
      if (state === "active") check();
    });
    return () => sub.remove();
  }, [user, request]);
  const canScan = !!user && hasScanEvents;

  return (
    <Tabs screenOptions={{ tabBarActiveTintColor: C.brand, headerTitleStyle: { fontWeight: "800" } }}>
      <Tabs.Screen name="index" options={{ title: "Events", tabBarIcon: icon("🔎") }} />
      <Tabs.Screen name="tickets" options={{ title: "My tickets", tabBarIcon: icon("🎟") }} />
      <Tabs.Screen name="scan" options={{ title: "Scan", tabBarIcon: icon("📷"), href: canScan ? "/scan" : null }} />
      <Tabs.Screen name="account" options={{ title: "Account", tabBarIcon: icon("👤") }} />
    </Tabs>
  );
}
