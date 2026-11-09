import { router, useFocusEffect } from "expo-router";
import { useCallback, useState } from "react";
import { FlatList, Pressable, RefreshControl, StyleSheet, Text, View } from "react-native";

import { Empty, ErrorText } from "@/components/ui";
import { C } from "@/constants/theme";
import { useAuth } from "@/lib/auth";
import type { ScanEvent } from "@/lib/types";

export default function ScanEventsScreen() {
  const { request } = useAuth();
  const [events, setEvents] = useState<ScanEvent[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setEvents(await request<ScanEvent[]>("/scanner/events/", { timeoutMs: 60_000 }));
      setError("");
    } catch {
      setError("Couldn't load events. You can still open an event you've synced before.");
    } finally {
      setLoading(false);
    }
  }, [request]);

  useFocusEffect(useCallback(() => { load(); }, [load]));

  return (
    <FlatList
      style={{ backgroundColor: C.bg }}
      contentContainerStyle={{ padding: 16, gap: 12 }}
      data={events ?? []}
      keyExtractor={(e) => e.slug}
      refreshControl={<RefreshControl refreshing={loading} onRefresh={load} tintColor={C.brand} />}
      ListHeaderComponent={
        <View>
          <Text style={{ color: C.muted, marginBottom: 8 }}>Choose the event you&apos;re scanning at.</Text>
          {error ? <ErrorText>{error}</ErrorText> : null}
        </View>
      }
      ListEmptyComponent={events && !loading ? <Empty title="No events to scan right now" /> : undefined}
      renderItem={({ item: e }) => {
        const pct = e.stats.tickets ? Math.round((e.stats.checked_in / e.stats.tickets) * 100) : 0;
        return (
          <Pressable style={s.card} onPress={() => router.push(`/scan/${e.slug}`)}>
            <Text style={s.org}>{e.organization}</Text>
            <Text style={s.title}>{e.title}</Text>
            <Text style={s.muted}>{e.when} · {e.where}</Text>
            {e.status === "cancelled" ? <Text style={{ color: C.danger, fontWeight: "700" }}>Cancelled</Text> : null}
            <View style={s.bar}><View style={[s.fill, { width: `${pct}%` }]} /></View>
            <Text style={s.muted}>{e.stats.checked_in} of {e.stats.tickets} tickets checked in ({e.stats.people_in}/{e.stats.people} people)</Text>
          </Pressable>
        );
      }}
    />
  );
}

const s = StyleSheet.create({
  card: { backgroundColor: "#fff", borderRadius: 14, borderWidth: 1, borderColor: C.line, padding: 16, gap: 4 },
  org: { color: C.brand, fontWeight: "700", fontSize: 12 },
  title: { fontWeight: "800", fontSize: 18, color: C.text },
  muted: { color: C.muted },
  bar: { height: 8, borderRadius: 4, backgroundColor: C.line, marginVertical: 8, overflow: "hidden" },
  fill: { height: 8, backgroundColor: C.brand },
});
