import { Stack } from "expo-router";
import { StatusBar } from "expo-status-bar";

import { C } from "@/constants/theme";
import { AuthProvider } from "@/lib/auth";

export default function RootLayout() {
  return (
    <AuthProvider>
      <StatusBar style="dark" />
      <Stack screenOptions={{ headerTintColor: C.brand, headerTitleStyle: { color: C.text }, contentStyle: { backgroundColor: C.bg } }}>
        <Stack.Screen name="(tabs)" options={{ headerShown: false }} />
        <Stack.Screen name="login" options={{ title: "Sign in", presentation: "modal" }} />
        <Stack.Screen name="event/[slug]" options={{ title: "Event" }} />
        <Stack.Screen name="scan/[slug]" options={{ title: "Scan tickets", headerShown: false }} />
      </Stack>
    </AuthProvider>
  );
}
