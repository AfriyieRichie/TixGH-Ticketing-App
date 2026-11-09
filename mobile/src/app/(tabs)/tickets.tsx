import AsyncStorage from "@react-native-async-storage/async-storage";
import { router, useFocusEffect } from "expo-router";
import { useCallback, useState } from "react";
import { FlatList, Modal, Pressable, RefreshControl, StyleSheet, Text, View } from "react-native";
import QRCode from "react-native-qrcode-svg";

import { Button, Empty } from "@/components/ui";
import { C } from "@/constants/theme";
import { isNetworkError } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { Paginated, WalletTicket } from "@/lib/types";

const CACHE = "wallet:upcoming";

export default function TicketsScreen() {
  const { user, ready, request } = useAuth();
  const [tickets, setTickets] = useState<WalletTicket[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [offline, setOffline] = useState(false);
  const [open, setOpen] = useState<WalletTicket | null>(null);

  const load = useCallback(async () => {
    if (!user) return;
    setLoading(true);
    try {
      const res = await request<Paginated<WalletTicket>>("/tickets/?when=upcoming", { timeoutMs: 60_000 });
      setTickets(res.results);
      setOffline(false);
      await AsyncStorage.setItem(`${CACHE}:${user.id}`, JSON.stringify(res.results)); // for offline use at the venue
    } catch (e) {
      if (isNetworkError(e)) {
        setOffline(true);
        const cached = await AsyncStorage.getItem(`${CACHE}:${user.id}`);
        setTickets(cached ? JSON.parse(cached) : []);
      }
    } finally {
      setLoading(false);
    }
  }, [user, request]);

  useFocusEffect(useCallback(() => { load(); }, [load]));

  if (ready && !user) {
    return (
      <View style={{ padding: 16 }}>
        <Empty title="Sign in to see your tickets">
          <Text style={{ color: C.muted, textAlign: "center", marginBottom: 12 }}>
            Use the same phone number or email you bought with. Guest purchases appear automatically.
          </Text>
          <Button title="Sign in" onPress={() => router.push("/login")} />
        </Empty>
      </View>
    );
  }

  return (
    <>
      <FlatList
        style={{ backgroundColor: C.bg }}
        contentContainerStyle={{ padding: 16, gap: 12 }}
        data={tickets ?? []}
        keyExtractor={(t) => t.code}
        refreshControl={<RefreshControl refreshing={loading} onRefresh={load} tintColor={C.brand} />}
        ListHeaderComponent={offline ? (
          <Text style={s.offline}>Offline: showing saved tickets. QR codes still work at the gate.</Text>
        ) : undefined}
        ListEmptyComponent={tickets && !loading ? (
          <Empty title="No upcoming tickets">
            <Button title="Find events" variant="secondary" onPress={() => router.push("/")} />
          </Empty>
        ) : undefined}
        renderItem={({ item: t }) => (
          <Pressable style={s.card} onPress={() => setOpen(t)}>
            <View style={{ flex: 1 }}>
              <Text style={s.title} numberOfLines={2}>{t.event.title}</Text>
              <Text style={s.muted}>{t.event.when}</Text>
              <Text style={s.muted}>{t.ticket_type_name}{t.attendee_name ? ` · ${t.attendee_name}` : ""}</Text>
            </View>
            <Text style={[s.badge, !t.qr_payload && { color: C.warning }]}>
              {t.event.status === "cancelled" ? "Cancelled" : t.qr_payload ? "Show QR" : "Used"}
            </Text>
          </Pressable>
        )}
      />
      <Modal visible={!!open} animationType="slide" onRequestClose={() => setOpen(null)}>
        {open ? (
          <View style={s.modal}>
            <Text style={[s.title, { textAlign: "center" }]}>{open.event.title}</Text>
            <Text style={[s.muted, { textAlign: "center" }]}>{open.event.when}</Text>
            <Text style={[s.muted, { textAlign: "center", marginBottom: 20 }]}>{open.event.where}</Text>
            {open.qr_payload ? (
              <View style={s.qr}><QRCode value={open.qr_payload} size={250} /></View>
            ) : <Text style={s.muted}>This ticket can no longer be used.</Text>}
            <Text style={s.code}>{open.code}</Text>
            <Text style={s.muted}>
              {open.ticket_type_name}{open.admits > 1 ? ` · admits ${open.admits}` : ""}
            </Text>
            <Text style={[s.muted, { textAlign: "center", marginTop: 12, fontSize: 13 }]}>
              Turn your screen brightness up at the gate. Each QR works once.
            </Text>
            <Button title="Close" variant="secondary" style={{ marginTop: 24, alignSelf: "stretch" }} onPress={() => setOpen(null)} />
          </View>
        ) : null}
      </Modal>
    </>
  );
}

const s = StyleSheet.create({
  card: { flexDirection: "row", alignItems: "center", gap: 12, backgroundColor: "#fff", borderRadius: 14,
    borderWidth: 1, borderColor: C.line, padding: 16 },
  title: { fontWeight: "800", fontSize: 17, color: C.text },
  muted: { color: C.muted },
  badge: { color: C.brand, fontWeight: "700" },
  offline: { backgroundColor: "#FEF3C7", color: "#92400E", padding: 12, borderRadius: 10, fontWeight: "600" },
  modal: { flex: 1, alignItems: "center", justifyContent: "center", padding: 24, backgroundColor: "#fff" },
  qr: { padding: 16, backgroundColor: "#fff", borderRadius: 16, borderWidth: 1, borderColor: C.line },
  code: { fontSize: 24, fontWeight: "800", letterSpacing: 4, marginTop: 16, color: C.text, fontVariant: ["tabular-nums"] },
});
