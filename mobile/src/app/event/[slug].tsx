import { Image } from "expo-image";
import { Stack, useLocalSearchParams } from "expo-router";
import * as WebBrowser from "expo-web-browser";
import { useEffect, useState } from "react";
import { ScrollView, StyleSheet, Text, View } from "react-native";

import { Button, Card, ErrorText, Loading } from "@/components/ui";
import { C } from "@/constants/theme";
import { apiFetch } from "@/lib/api";
import { WEB_URL } from "@/lib/config";
import { cedis, eventDate } from "@/lib/format";
import type { EventDetail } from "@/lib/types";

export default function EventScreen() {
  const { slug } = useLocalSearchParams<{ slug: string }>();
  const [ev, setEv] = useState<EventDetail | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    apiFetch<EventDetail>(`/events/${slug}/`, { timeoutMs: 60_000 })
      .then(setEv)
      .catch(() => setError("Couldn't load this event."));
  }, [slug]);

  if (error) return <View style={{ padding: 16 }}><ErrorText>{error}</ErrorText></View>;
  if (!ev) return <Loading />;
  const onSale = ev.status === "published" && !ev.has_ended;
  const buttonTitle = onSale ? "Get tickets" : ev.status === "cancelled" ? "Event cancelled" : "Event ended";

  return (
    <>
      <Stack.Screen options={{ title: ev.title }} />
      <ScrollView contentContainerStyle={{ paddingBottom: 130 }}>
        {ev.cover_image
          ? <Image source={ev.cover_image} style={{ width: "100%", aspectRatio: 16 / 9 }} contentFit="cover" />
          : <View style={{ height: 120, backgroundColor: C.brand }} />}
        <View style={{ padding: 16, gap: 12 }}>
          <Text style={s.title}>{ev.title}</Text>
          {ev.summary ? <Text style={s.muted}>{ev.summary}</Text> : null}
          <Card>
            <Text style={s.label}>When</Text>
            <Text style={s.value}>{eventDate(ev.start_at)}</Text>
            <Text style={[s.label, { marginTop: 10 }]}>Where</Text>
            <Text style={s.value}>{ev.venue ? `${ev.venue.name}, ${ev.venue.city}` : "Online"}</Text>
            {ev.venue?.digital_address ? <Text style={s.muted}>GPS: {ev.venue.digital_address}</Text> : null}
          </Card>
          <Card>
            <Text style={s.label}>Tickets</Text>
            {ev.ticket_types.map((t) => (
              <View key={t.id} style={s.row}>
                <Text style={s.value}>{t.name}</Text>
                <Text style={s.value}>{t.sale_status === "sold_out" ? "Sold out" : cedis(t.pricing.buyer_pays)}</Text>
              </View>
            ))}
          </Card>
          {ev.description ? <Text style={{ color: C.text, lineHeight: 22 }}>{ev.description}</Text> : null}
          {ev.venue?.directions ? (
            <Card><Text style={s.label}>Getting there</Text><Text style={s.value}>{ev.venue.directions}</Text></Card>
          ) : null}
        </View>
      </ScrollView>
      <View style={s.footer}>
        <Button
          title={buttonTitle}
          disabled={!onSale}
          // Checkout runs on the secure website (Paystack MoMo/card), opened inside the app.
          onPress={() => WebBrowser.openBrowserAsync(`${WEB_URL}/e/${ev.slug}`)}
        />
        <Text style={s.hint}>Pay with Mobile Money or card. Your tickets then appear under My tickets.</Text>
      </View>
    </>
  );
}

const s = StyleSheet.create({
  title: { fontSize: 26, fontWeight: "800", color: C.text },
  muted: { color: C.muted },
  label: { color: C.muted, fontWeight: "600", marginBottom: 4 },
  value: { color: C.text, fontWeight: "600", fontSize: 15 },
  row: { flexDirection: "row", justifyContent: "space-between", paddingVertical: 6 },
  footer: { position: "absolute", bottom: 0, left: 0, right: 0, padding: 16, paddingBottom: 28, backgroundColor: "#fff",
    borderTopWidth: 1, borderColor: C.line },
  hint: { color: C.muted, textAlign: "center", marginTop: 6, fontSize: 12 },
});
