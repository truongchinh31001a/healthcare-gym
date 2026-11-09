import type { ReactNode } from "react";
import { KeyboardAvoidingView, Platform, ScrollView, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
export function Screen({ title, description, children }: { title: string; description: string; children?: ReactNode }) {
 return <SafeAreaView style={{ flex: 1, backgroundColor: "#edf5f2" }} edges={["top", "left", "right"]}><KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === "ios" ? "padding" : undefined}><ScrollView keyboardShouldPersistTaps="handled" contentContainerStyle={{ padding: 22, gap: 18, paddingBottom: 48, width: "100%", maxWidth: 760, alignSelf: "center" }}><View style={{ gap: 9, paddingVertical: 10 }}><Text style={{ fontSize: 12, letterSpacing: 3, color: "#167b70", fontWeight: "700" }}>HEALTH COMPANION</Text><Text style={{ fontSize: 30, fontWeight: "700", color: "#183e43" }}>{title}</Text><Text style={{ color: "#5b7477", lineHeight: 24, fontSize: 15 }}>{description}</Text></View>{children}</ScrollView></KeyboardAvoidingView></SafeAreaView>;
}
