import { CameraView, useCameraPermissions } from "expo-camera";
import * as Haptics from "expo-haptics";
import { useKeepAwake } from "expo-keep-awake";
import { router, useLocalSearchParams } from "expo-router";
import { useEffect, useRef, useState } from "react";
import { Alert, Modal, Pressable, StyleSheet, Text, TextInput, View } from "react-native";

import { Button, Loading } from "@/components/ui";
import { C } from "@/constants/theme";
import { timeOnly } from "@/lib/format";
import { getGate, setGate as saveGate, useScanner, type ScanOutcome } from "@/lib/scanner";

const COLORS: Record<string, string> = {
  ok: "#16A34A", duplicate: "#D97706", invalid: "#DC2626", transferred: "#DC2626",
  void: "#DC2626", wrong_event: "#DC2626", event_cancelled: "#DC2626",
};
const HEADLINE: Record<string, string> = {
  ok: "ADMIT", duplicate: "ALREADY USED", invalid: "INVALID", transferred: "OLD TICKET",
  void: "VOID", wrong_event: "WRONG EVENT", event_cancelled: "CANCELLED",
};

export default function ScannerScreen() {
  useKeepAwake(); // screen stays on at the gate
  const { slug } = useLocalSearchParams<{ slug: string }>();
  const sc = useScanner(slug);
  const [permission, requestPermission] = useCameraPermissions();
  const [gate, setGate] = useState("Main gate");
  const [torch, setTorch] = useState(false);
  const [result, setResult] = useState<ScanOutcome | null>(null);
  const [busy, setBusy] = useState(false);
  const [typing, setTyping] = useState(false);
  const [typed, setTyped] = useState("");
  const [editingGate, setEditingGate] = useState(false);
  const last = useRef<{ data: string; at: number }>({ data: "", at: 0 });
  const dismissTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => { getGate().then(setGate); }, []);

  async function handle(raw: string) {
    const now = Date.now();
    // Ignore the same QR held in front of the camera, and scans while a result is showing.
    if (busy || result || (raw === last.current.data && now - last.current.at < 3000)) return;
    last.current = { data: raw, at: now };
    setBusy(true);
    try {
      const r = await sc.scan(raw, gate);
      setResult(r);
      Haptics.notificationAsync(
        r.result === "ok" ? Haptics.NotificationFeedbackType.Success
          : r.result === "duplicate" ? Haptics.NotificationFeedbackType.Warning
          : Haptics.NotificationFeedbackType.Error,
      );
      if (dismissTimer.current) clearTimeout(dismissTimer.current);
      // Admits clear quickly so the queue keeps moving; problems stay until tapped.
      if (r.result === "ok") dismissTimer.current = setTimeout(() => setResult(null), 2200);
    } catch (e) {
      Alert.alert("Scan failed", e instanceof Error ? e.message : "Please try again.");
    } finally {
      setBusy(false);
    }
  }

  async function undo(code: string) {
    try {
      await sc.undo(code);
      setResult(null);
    } catch (e) {
      Alert.alert("Couldn't undo", e instanceof Error ? e.message : "Try again when online.");
    }
  }

  if (!permission) return <Loading />;
  if (!permission.granted) {
    return (
      <View style={s.center}>
        <Text style={s.bigDark}>Camera access needed</Text>
        <Text style={s.mutedCenter}>The scanner uses your camera to read ticket QR codes.</Text>
        <Button title="Allow camera" onPress={requestPermission} style={{ marginTop: 16, alignSelf: "stretch" }} />
        <Button title="Back" variant="secondary" onPress={() => router.back()} style={{ marginTop: 10, alignSelf: "stretch" }} />
      </View>
    );
  }
  if (!sc.ready) {
    return (
      <View style={s.center}>
        <Loading />
        <Text style={s.mutedCenter}>
          {sc.online ? "Downloading tickets for offline scanning…" : "No connection. Connect once to download this event's tickets."}
        </Text>
        {sc.error ? <Text style={{ color: C.danger, marginTop: 8 }}>{sc.error}</Text> : null}
        <Button title="Back" variant="secondary" onPress={() => router.back()} style={{ marginTop: 16, alignSelf: "stretch" }} />
      </View>
    );
  }

  const pctIn = sc.stats.tickets ? Math.round((sc.stats.checked_in / sc.stats.tickets) * 100) : 0;

  return (
    <View style={{ flex: 1, backgroundColor: "#000" }}>
      <CameraView
        style={StyleSheet.absoluteFill}
        facing="back"
        enableTorch={torch}
        barcodeScannerSettings={{ barcodeTypes: ["qr"] }}
        onBarcodeScanned={result || busy ? undefined : ({ data }) => handle(data)}
      />

      {/* Top bar: event, counts, connection */}
      <View style={s.top}>
        <View style={{ flexDirection: "row", alignItems: "center", gap: 10 }}>
          <Pressable onPress={() => router.back()} hitSlop={12}><Text style={s.topText}>✕</Text></Pressable>
          <Text style={[s.topText, { flex: 1 }]} numberOfLines={1}>{sc.eventInfo?.title}</Text>
          <View style={[s.dot, { backgroundColor: sc.online ? "#22C55E" : "#F59E0B" }]} />
          <Text style={s.topSmall}>{sc.online ? "Online" : "Offline"}</Text>
        </View>
        <Text style={s.count}>{sc.stats.checked_in} / {sc.stats.tickets} in <Text style={s.topSmall}>({pctIn}%, {sc.stats.people_in} people)</Text></Text>
        <Text style={s.topSmall}>
          {sc.queued ? `${sc.queued} scan(s) waiting to sync · ` : ""}
          {sc.lastSync ? `Synced ${timeOnly(sc.lastSync.toISOString())}` : "Not synced yet"}
        </Text>
      </View>

      {sc.alerts.length > 0 && !result ? (
        <Pressable style={s.alert} onPress={() => sc.dismissAlert(sc.alerts[0].id)}>
          <Text style={{ color: "#fff", fontWeight: "700" }}>⚠ {sc.alerts[0].text}</Text>
          <Text style={{ color: "#fff", opacity: 0.8, fontSize: 12 }}>Tap to dismiss{sc.alerts.length > 1 ? ` (${sc.alerts.length - 1} more)` : ""}</Text>
        </Pressable>
      ) : null}

      {!result ? <View style={s.frame} pointerEvents="none" /> : null}

      {/* Bottom controls */}
      <View style={s.bottom}>
        <Pressable style={s.ctrl} onPress={() => setTorch(!torch)}><Text style={s.ctrlText}>{torch ? "🔦 On" : "🔦 Off"}</Text></Pressable>
        <Pressable style={s.ctrl} onPress={() => setTyping(true)}><Text style={s.ctrlText}>⌨ Type code</Text></Pressable>
        <Pressable style={s.ctrl} onPress={() => setEditingGate(true)}><Text style={s.ctrlText} numberOfLines={1}>🚪 {gate}</Text></Pressable>
      </View>

      {/* Result */}
      {result ? (
        <Pressable style={[s.result, { backgroundColor: COLORS[result.result] }]} onPress={() => setResult(null)}>
          <Text style={s.headline}>{HEADLINE[result.result]}</Text>
          {result.ticket ? (
            <>
              <Text style={s.name}>{result.ticket.name}</Text>
              <Text style={s.detail}>{result.ticket.type}{result.ticket.admits > 1 ? ` · ADMITS ${result.ticket.admits}` : ""}</Text>
              <Text style={s.code}>{result.ticket.code}</Text>
            </>
          ) : <Text style={s.detail}>{result.message}</Text>}
          {result.result === "duplicate" && result.previous ? (
            <Text style={s.detail}>First used {timeOnly(result.previous.at)}{result.previous.gate ? ` at ${result.previous.gate}` : ""}</Text>
          ) : null}
          {result.offline ? <Text style={s.small}>Checked offline · will sync</Text> : null}
          <Text style={s.small}>Tap anywhere to scan next</Text>
          {result.result === "ok" && result.ticket && !result.offline ? (
            <Pressable style={s.undo} onPress={() => undo(result.ticket!.code)}><Text style={{ color: "#fff", fontWeight: "700" }}>Undo</Text></Pressable>
          ) : null}
        </Pressable>
      ) : null}

      {/* Type a code */}
      <Modal visible={typing} transparent animationType="fade" onRequestClose={() => setTyping(false)}>
        <View style={s.modalBg}>
          <View style={s.sheet}>
            <Text style={s.bigDark}>Enter ticket code</Text>
            <TextInput value={typed} onChangeText={(t) => setTyped(t.toUpperCase())} autoFocus autoCapitalize="characters"
              placeholder="e.g. 9G588T485X" style={s.input} maxLength={12} />
            <Button title="Check" disabled={typed.length < 8} onPress={() => { setTyping(false); handle(typed.trim()); setTyped(""); }} />
            <Button title="Cancel" variant="secondary" style={{ marginTop: 8 }} onPress={() => setTyping(false)} />
          </View>
        </View>
      </Modal>

      {/* Gate name */}
      <Modal visible={editingGate} transparent animationType="fade" onRequestClose={() => setEditingGate(false)}>
        <View style={s.modalBg}>
          <View style={s.sheet}>
            <Text style={s.bigDark}>Which gate is this phone at?</Text>
            <TextInput value={gate} onChangeText={setGate} style={s.input} maxLength={40} />
            <Button title="Save" onPress={() => { saveGate(gate); setEditingGate(false); }} />
          </View>
        </View>
      </Modal>
    </View>
  );
}

const s = StyleSheet.create({
  center: { flex: 1, alignItems: "center", justifyContent: "center", padding: 24, backgroundColor: C.bg },
  bigDark: { fontSize: 20, fontWeight: "800", color: C.text, marginBottom: 8, textAlign: "center" },
  mutedCenter: { color: C.muted, textAlign: "center", marginTop: 8 },
  top: { paddingTop: 54, paddingHorizontal: 16, paddingBottom: 12, backgroundColor: "rgba(0,0,0,0.65)" },
  topText: { color: "#fff", fontWeight: "700", fontSize: 16 },
  topSmall: { color: "#D4D4D8", fontSize: 12 },
  count: { color: "#fff", fontSize: 26, fontWeight: "800", marginTop: 6 },
  dot: { width: 10, height: 10, borderRadius: 5 },
  alert: { backgroundColor: "#B45309", margin: 12, padding: 12, borderRadius: 12 },
  frame: { position: "absolute", top: "32%", left: "15%", right: "15%", aspectRatio: 1, borderWidth: 3, borderColor: "rgba(255,255,255,0.85)", borderRadius: 24 },
  bottom: { position: "absolute", bottom: 0, left: 0, right: 0, flexDirection: "row", gap: 8, padding: 16, paddingBottom: 34, backgroundColor: "rgba(0,0,0,0.65)" },
  ctrl: { flex: 1, backgroundColor: "rgba(255,255,255,0.15)", paddingVertical: 14, borderRadius: 12, alignItems: "center" },
  ctrlText: { color: "#fff", fontWeight: "700" },
  result: { position: "absolute", top: 0, left: 0, right: 0, bottom: 0, alignItems: "center", justifyContent: "center", padding: 24 },
  headline: { color: "#fff", fontSize: 46, fontWeight: "900", textAlign: "center" },
  name: { color: "#fff", fontSize: 26, fontWeight: "800", marginTop: 16, textAlign: "center" },
  detail: { color: "#fff", fontSize: 18, marginTop: 8, textAlign: "center", fontWeight: "600" },
  code: { color: "#fff", fontSize: 20, marginTop: 8, letterSpacing: 3, fontWeight: "700" },
  small: { color: "rgba(255,255,255,0.85)", marginTop: 18 },
  undo: { marginTop: 24, borderWidth: 2, borderColor: "#fff", borderRadius: 10, paddingVertical: 10, paddingHorizontal: 24 },
  modalBg: { flex: 1, backgroundColor: "rgba(0,0,0,0.6)", justifyContent: "center", padding: 24 },
  sheet: { backgroundColor: "#fff", borderRadius: 16, padding: 20 },
  input: { borderWidth: 1, borderColor: C.line, borderRadius: 10, padding: 14, fontSize: 20, letterSpacing: 2, marginVertical: 14, color: C.text },
});
