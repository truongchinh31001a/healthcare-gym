import { Stack, useRouter, useSegments } from "expo-router";
import { useEffect, type ReactNode } from "react";
import { ActivityIndicator, View } from "react-native";
import { SafeAreaProvider } from "react-native-safe-area-context";
import { SessionProvider, useSession } from "@/lib/session";
function Gate({ children }: { children: ReactNode }) {
 const { ready, user } = useSession(); const segments = useSegments(); const router = useRouter(); const auth = segments[0] === "(auth)";
 useEffect(() => { if (!ready) return; if (!user && !auth) router.replace("/(auth)/login"); if (user && auth) router.replace("/(tabs)/dashboard"); }, [ready, user, auth, router]);
 if (!ready || (!user && !auth) || (user && auth)) return <View style={{ flex: 1, justifyContent: "center" }}><ActivityIndicator /></View>;
 return children;
}
export default function Layout() { return <SafeAreaProvider><SessionProvider><Gate><Stack screenOptions={{ headerShown: false }} /></Gate></SessionProvider></SafeAreaProvider>; }
