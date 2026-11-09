import { router } from "expo-router";
import { useState } from "react";
import { KeyboardAvoidingView, Platform, Pressable, ScrollView, Text } from "react-native";

import { Button, ErrorText, Field } from "@/components/ui";
import { C } from "@/constants/theme";
import { apiFetch } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import type { AuthResponse } from "@/lib/types";

export default function Login() {
  const { signIn } = useAuth();
  const [mode, setMode] = useState<"code" | "password">("code");
  const [identifier, setIdentifier] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const [sentTo, setSentTo] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function run(fn: () => Promise<void>) {
    setBusy(true);
    setError("");
    try {
      await fn();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong.");
    } finally {
      setBusy(false);
    }
  }

  async function finish(res: AuthResponse) {
    await signIn(res);
    router.back();
  }

  const requestCode = () => run(async () => {
    const r = await apiFetch<{ sent_to: string }>("/auth/otp/request/", {
      body: { identifier, purpose: "login" }, timeoutMs: 60_000,
    });
    setSentTo(r.sent_to);
  });
  const verifyCode = () => run(async () => {
    await finish(await apiFetch<AuthResponse>("/auth/otp/verify/", { body: { identifier, code, full_name: name } }));
  });
  const passwordLogin = () => run(async () => {
    await finish(await apiFetch<AuthResponse>("/auth/login/", { body: { identifier, password }, timeoutMs: 60_000 }));
  });

  return (
    <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === "ios" ? "padding" : undefined}>
      <ScrollView contentContainerStyle={{ padding: 20 }} keyboardShouldPersistTaps="handled">
        <Text style={{ fontSize: 24, fontWeight: "800", color: C.text, marginBottom: 6 }}>Sign in or create an account</Text>
        <Text style={{ color: C.muted, marginBottom: 20 }}>
          {mode === "code" ? "We'll send a 6-digit code. No password needed." : "Use your email or phone and password."}
        </Text>

        {mode === "password" ? (
          <>
            <Field label="Phone or email" value={identifier} onChangeText={setIdentifier} autoCapitalize="none" autoComplete="username" />
            <Field label="Password" value={password} onChangeText={setPassword} secureTextEntry autoComplete="password" />
            {error ? <ErrorText>{error}</ErrorText> : null}
            <Button title="Sign in" loading={busy} disabled={!identifier || !password} onPress={passwordLogin} />
          </>
        ) : !sentTo ? (
          <>
            <Field label="Phone number or email" value={identifier} onChangeText={setIdentifier} placeholder="024 123 4567"
              autoCapitalize="none" keyboardType="email-address" autoComplete="username" />
            {error ? <ErrorText>{error}</ErrorText> : null}
            <Button title="Send code" loading={busy} disabled={!identifier} onPress={requestCode} />
          </>
        ) : (
          <>
            <Text style={{ color: C.text, marginBottom: 14 }}>
              Code sent to <Text style={{ fontWeight: "700" }}>{sentTo}</Text>
            </Text>
            <Field label="6-digit code" value={code} onChangeText={(t) => setCode(t.replace(/\D/g, ""))}
              keyboardType="number-pad" maxLength={6} autoComplete="one-time-code"
              style={{ fontSize: 24, letterSpacing: 8, textAlign: "center" }} />
            <Field label="Your name (first time only)" value={name} onChangeText={setName} autoComplete="name" />
            {error ? <ErrorText>{error}</ErrorText> : null}
            <Button title="Continue" loading={busy} disabled={code.length !== 6} onPress={verifyCode} />
            <Pressable onPress={() => { setSentTo(""); setCode(""); }} style={{ marginTop: 16 }}>
              <Text style={{ color: C.brand, fontWeight: "700" }}>Change number</Text>
            </Pressable>
          </>
        )}

        <Pressable onPress={() => { setMode(mode === "code" ? "password" : "code"); setError(""); }} style={{ marginTop: 20 }}>
          <Text style={{ color: C.brand, fontWeight: "700" }}>
            {mode === "code" ? "Use password instead" : "Use a one-time code instead"}
          </Text>
        </Pressable>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}
