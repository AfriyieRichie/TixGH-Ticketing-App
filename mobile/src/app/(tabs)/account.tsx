import { router } from "expo-router";
import * as WebBrowser from "expo-web-browser";
import { ScrollView, Text, View } from "react-native";

import { Button, Card } from "@/components/ui";
import { C } from "@/constants/theme";
import { useAuth } from "@/lib/auth";
import { SITE_NAME, WEB_URL } from "@/lib/config";

export default function AccountScreen() {
  const { user, signOut } = useAuth();
  return (
    <ScrollView contentContainerStyle={{ padding: 16, gap: 14 }}>
      {user ? (
        <Card>
          <Text style={{ fontSize: 20, fontWeight: "800", color: C.text }}>{user.full_name || "Your account"}</Text>
          {user.phone ? <Text style={{ color: C.muted, marginTop: 4 }}>{user.phone}</Text> : null}
          {user.email ? <Text style={{ color: C.muted }}>{user.email}</Text> : null}
        </Card>
      ) : (
        <Card>
          <Text style={{ fontSize: 18, fontWeight: "800", color: C.text, marginBottom: 12 }}>Welcome to {SITE_NAME}</Text>
          <Button title="Sign in" onPress={() => router.push("/login")} />
        </Card>
      )}
      <Card>
        <Text style={{ fontWeight: "800", color: C.text, marginBottom: 6 }}>Organizing an event?</Text>
        <Text style={{ color: C.muted, marginBottom: 12 }}>
          Create events and see sales on the organizer dashboard. Your gate staff can scan tickets in this app
          once you add them to your team with the &quot;Gate scanner&quot; role.
        </Text>
        <Button title="Open organizer dashboard" variant="secondary"
          onPress={() => WebBrowser.openBrowserAsync(`${WEB_URL}/dashboard`)} />
      </Card>
      {user ? <Button title="Sign out" variant="secondary" onPress={signOut} /> : null}
      <View style={{ alignItems: "center", marginTop: 8 }}>
        <Text style={{ color: C.muted, fontSize: 12 }}>{SITE_NAME} · Made in Ghana 🇬🇭</Text>
      </View>
    </ScrollView>
  );
}
