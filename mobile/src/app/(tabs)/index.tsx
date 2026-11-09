import { Image } from "expo-image";
import { router } from "expo-router";
import { useCallback, useEffect, useState } from "react";
import { FlatList, Pressable, RefreshControl, StyleSheet, Text, TextInput, View } from "react-native";

import { Empty, ErrorText } from "@/components/ui";
import { C } from "@/constants/theme";
import { apiFetch } from "@/lib/api";
import { cedis, eventDate } from "@/lib/format";
import type { EventCard, Paginated } from "@/lib/types";

// Generous timeout: the free server may need ~50 s to wake up.
function fetchEvents(q: string, when: string) {
  const params = new URLSearchParams();
  if (q.trim()) params.set("q", q.trim());
  if (when) params.set("when", when);
  return apiFetch<Paginated<EventCard>>(`/events/?${params}`, { timeoutMs: 60_000 });
}

const WHEN = [["", "All"], ["today", "Today"], ["this_weekend", "Weekend"], ["this_week", "This week"], ["this_month", "Month"]];

export default function EventsScreen() {
  const [events, setEvents] = useState<EventCard[]>([]);
  const [q, setQ] = useState("");
  const [when, setWhen] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const apply = useCallback((p: Promise<Paginated<EventCard>>) => {
    p.then((res) => { setEvents(res.results); setError(""); })
      .catch(() => setError("Couldn't load events. Check your connection and pull down to refresh."))
      .finally(() => setLoading(false));
  }, []);
  const load = () => {
    setLoading(true);
    apply(fetchEvents(q, when));
  };

  // Reload when the date filter changes; the search box reloads on submit.
  useEffect(() => {
    apply(fetchEvents(q, when));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [when]);

  return (
    <FlatList
      style={{ backgroundColor: C.bg }}
      contentContainerStyle={{ padding: 16, gap: 14 }}
      data={events}
      keyExtractor={(e) => e.slug}
      refreshControl={<RefreshControl refreshing={loading} onRefresh={load} tintColor={C.brand} />}
      ListHeaderComponent={
        <View style={{ gap: 12 }}>
          <TextInput value={q} onChangeText={setQ} onSubmitEditing={load} returnKeyType="search"
            placeholder="Search events, venues, cities" placeholderTextColor={C.muted} style={s.search} />
          <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 8 }}>
            {WHEN.map(([v, l]) => (
              <Pressable key={v} onPress={() => setWhen(v)} style={[s.chip, when === v && s.chipOn]}>
                <Text style={[s.chipText, when === v && { color: "#fff" }]}>{l}</Text>
              </Pressable>
            ))}
          </View>
          {error ? <ErrorText>{error}</ErrorText> : null}
        </View>
      }
      ListEmptyComponent={loading ? undefined : <Empty title="No events found" />}
      renderItem={({ item: e }) => (
        <Pressable onPress={() => router.push(`/event/${e.slug}`)} style={s.card}>
          {e.cover_image ? <Image source={e.cover_image} style={s.cover} contentFit="cover" /> : (
            <View style={[s.cover, s.coverFallback]}>
              <Text style={s.coverText} numberOfLines={2}>{e.title}</Text>
            </View>
          )}
          <View style={{ padding: 14, gap: 3 }}>
            {e.category ? <Text style={s.cat}>{e.category.name.toUpperCase()}</Text> : null}
            <Text style={s.title} numberOfLines={2}>{e.title}</Text>
            <Text style={s.muted}>{eventDate(e.start_at)}</Text>
            <Text style={s.muted}>{e.venue ? `${e.venue.name}, ${e.venue.city}` : "Online"}</Text>
            <Text style={s.price}>{e.sold_out ? "Sold out" : e.is_free ? "Free" : `From ${cedis(e.price_from)}`}</Text>
          </View>
        </Pressable>
      )}
    />
  );
}

const s = StyleSheet.create({
  search: { backgroundColor: "#fff", borderWidth: 1, borderColor: C.line, borderRadius: 12, padding: 14, fontSize: 16, color: C.text },
  chip: { borderWidth: 1, borderColor: C.line, backgroundColor: "#fff", borderRadius: 99, paddingHorizontal: 14, paddingVertical: 7 },
  chipOn: { backgroundColor: C.brand, borderColor: C.brand },
  chipText: { fontWeight: "600", color: C.text },
  card: { backgroundColor: "#fff", borderRadius: 14, borderWidth: 1, borderColor: C.line, overflow: "hidden" },
  cover: { width: "100%", aspectRatio: 16 / 9 },
  coverFallback: { backgroundColor: C.brand, justifyContent: "flex-end", padding: 12 },
  coverText: { color: "#fff", fontWeight: "800", fontSize: 18 },
  cat: { color: C.brand, fontWeight: "700", fontSize: 12 },
  title: { fontWeight: "800", fontSize: 17, color: C.text },
  muted: { color: C.muted },
  price: { marginTop: 6, fontWeight: "800", color: C.text },
});
