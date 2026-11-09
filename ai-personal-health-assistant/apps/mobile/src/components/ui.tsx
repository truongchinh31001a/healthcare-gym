import { useCallback, useState, type ReactNode } from "react";
import { ActivityIndicator, Pressable, StyleSheet, Text, TextInput, View, type TextInputProps } from "react-native";
import { useFocusEffect } from "expo-router";
import { useSession } from "@/lib/session";

export const theme = { ink: "#183e43", muted: "#5b7477", teal: "#167b70", light: "#edf5f2", line: "#d9e8e3", danger: "#a33a35" };
export const styles = StyleSheet.create({ card: { backgroundColor: "white", borderRadius: 20, padding: 20, gap: 14, borderWidth: 1, borderColor: theme.line },
  title: { color: theme.ink, fontSize: 21, fontWeight: "700" }, text: { color: theme.muted, fontSize: 15, lineHeight: 23 },
  row: { flexDirection: "row", flexWrap: "wrap", gap: 9, alignItems: "center" },
  input: { borderWidth: 1, borderColor: theme.line, borderRadius: 12, padding: 14, fontSize: 16, color: theme.ink, backgroundColor: "#fafdfb" },
  button: { paddingVertical: 14, paddingHorizontal: 18, borderRadius: 12, backgroundColor: theme.teal, alignItems: "center" },
  buttonText: { color: "white", fontSize: 15, fontWeight: "700" }, chip: { padding: 10, borderRadius: 10, borderWidth: 1, borderColor: theme.line },
  error: { color: theme.danger, lineHeight: 22 }, metric: { fontSize: 32, fontWeight: "700", color: theme.ink },
});
export function Card({ title, children }: { title?: string; children: ReactNode }) { return <View style={styles.card}>{title && <Text style={styles.title}>{title}</Text>}{children}</View>; }
export function Copy({ children }: { children: ReactNode }) { return <Text style={styles.text}>{children}</Text>; }
export function Button({ title, onPress, disabled, danger }: { title: string; onPress: () => void; disabled?: boolean; danger?: boolean }) {
  return <Pressable accessibilityRole="button" accessibilityState={{ disabled }} onPress={onPress} disabled={disabled} style={[styles.button, danger && { backgroundColor: theme.danger }, disabled && { opacity: .5 }]}><Text style={styles.buttonText}>{title}</Text></Pressable>;
}
export function Input({ label, ...props }: TextInputProps & { label: string }) { return <View style={{ gap: 7 }}><Text style={{ color: theme.ink, fontWeight: "600" }}>{label}</Text><TextInput accessibilityLabel={label} placeholderTextColor="#7c9291" style={styles.input} {...props} /></View>; }
export function Choice<T extends string>({ label, value, options, onChange }: { label: string; value: T; options: { value: T; label: string }[]; onChange: (value: T) => void }) {
  return <View style={{ gap: 9 }}><Text style={{ color: theme.ink, fontWeight: "600" }}>{label}</Text><View style={styles.row}>{options.map(option => <Pressable key={option.value} accessibilityRole="radio" accessibilityState={{ selected: value === option.value }} onPress={() => onChange(option.value)} style={[styles.chip, value === option.value && { borderColor: theme.teal, backgroundColor: theme.light }]}><Text style={{ color: theme.ink }}>{option.label}</Text></Pressable>)}</View></View>;
}
export function Check({ checked, onChange, label }: { checked: boolean; onChange: (value: boolean) => void; label: string }) {
  return <Pressable accessibilityRole="checkbox" accessibilityState={{ checked }} onPress={() => onChange(!checked)} style={styles.row}><Text style={{ fontSize: 24, color: theme.teal }}>{checked ? "☑" : "☐"}</Text><Text style={[styles.text, { flex: 1 }]}>{label}</Text></Pressable>;
}
export function useTask() {
  const [busy, setBusy] = useState(false); const [message, setMessage] = useState(""); const [failed, setFailed] = useState(false);
  const run = async (task: () => Promise<unknown>, success = "Đã lưu") => {
    if (busy) return;
    setBusy(true); setMessage(""); setFailed(false);
    try { await task(); setMessage(success); } catch (error) { setFailed(true); setMessage(error instanceof Error ? error.message : "Có lỗi xảy ra"); }
    finally { setBusy(false); }
  };
  return { busy, run, feedback: busy ? <ActivityIndicator color={theme.teal} /> : message ? <Text accessibilityRole="alert" style={failed ? styles.error : styles.text}>{message}</Text> : null };
}
export function useResource<T>(path: string) {
  const { api } = useSession(); const [data, setData] = useState<T | null>(null); const [error, setError] = useState(""); const [loading, setLoading] = useState(true); const [revision, setRevision] = useState(0);
  useFocusEffect(useCallback(() => { let live = true; setLoading(true); setError("");
    api<T>(path).then(value => { if (live) setData(value); }).catch(error => { if (live) { setError(error.message); setData(null); } }).finally(() => { if (live) setLoading(false); });
    return () => { live = false; };
  }, [api, path, revision]));
  return { data, loading, error, reload: () => setRevision(x => x + 1), feedback: loading ? <ActivityIndicator color={theme.teal} /> : error ? <Text style={styles.error}>{error}</Text> : null };
}
