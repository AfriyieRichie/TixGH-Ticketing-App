import { ActivityIndicator, Pressable, StyleSheet, Text, TextInput, View, type TextInputProps, type ViewStyle } from "react-native";

import { C } from "@/constants/theme";

export function Button({ title, onPress, variant = "primary", loading, disabled, style }: {
  title: string; onPress: () => void; variant?: "primary" | "secondary" | "danger"; loading?: boolean;
  disabled?: boolean; style?: ViewStyle;
}) {
  const bg = { primary: C.brand, secondary: C.card, danger: C.danger }[variant];
  const fg = variant === "secondary" ? C.text : "#fff";
  return (
    <Pressable
      onPress={onPress}
      disabled={disabled || loading}
      style={({ pressed }) => [s.btn, { backgroundColor: bg, opacity: disabled ? 0.5 : pressed ? 0.85 : 1 },
        variant === "secondary" && { borderWidth: 1, borderColor: C.line }, style]}
    >
      {loading ? <ActivityIndicator color={fg} /> : <Text style={[s.btnText, { color: fg }]}>{title}</Text>}
    </Pressable>
  );
}

export function Field({ label, ...props }: TextInputProps & { label: string }) {
  return (
    <View style={{ marginBottom: 14 }}>
      <Text style={s.label}>{label}</Text>
      <TextInput placeholderTextColor={C.muted} {...props} style={[s.input, props.style]} />
    </View>
  );
}

export function Card({ children, style }: { children: React.ReactNode; style?: ViewStyle }) {
  return <View style={[s.card, style]}>{children}</View>;
}

export function Loading() {
  return <View style={s.center}><ActivityIndicator size="large" color={C.brand} /></View>;
}

export function Empty({ title, children }: { title: string; children?: React.ReactNode }) {
  return (
    <View style={[s.card, { alignItems: "center", paddingVertical: 32 }]}>
      <Text style={{ fontWeight: "700", fontSize: 16, color: C.text }}>{title}</Text>
      {children ? <View style={{ marginTop: 8 }}>{children}</View> : null}
    </View>
  );
}

export function ErrorText({ children }: { children: React.ReactNode }) {
  return <Text style={s.error}>{children}</Text>;
}

const s = StyleSheet.create({
  btn: { paddingVertical: 14, paddingHorizontal: 18, borderRadius: 10, alignItems: "center", justifyContent: "center" },
  btnText: { fontWeight: "700", fontSize: 16 },
  label: { fontSize: 14, fontWeight: "600", color: C.text, marginBottom: 6 },
  input: { borderWidth: 1, borderColor: C.line, backgroundColor: "#fff", borderRadius: 10, paddingHorizontal: 14,
    paddingVertical: 12, fontSize: 16, color: C.text },
  card: { backgroundColor: C.card, borderRadius: 14, borderWidth: 1, borderColor: C.line, padding: 16 },
  center: { flex: 1, alignItems: "center", justifyContent: "center", padding: 24 },
  error: { color: C.danger, marginBottom: 12 },
});
