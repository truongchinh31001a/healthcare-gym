import { Tabs } from "expo-router";
export default function Layout() { return <Tabs screenOptions={{ headerShown: false, tabBarActiveTintColor: "#167b70", tabBarStyle: { backgroundColor: "#fff", borderTopColor: "#d9e8e3" } }}>
<Tabs.Screen name="dashboard" options={{ title: "Tổng quan" }} />
<Tabs.Screen name="tracking" options={{ title: "Số đo" }} />
<Tabs.Screen name="profile" options={{ title: "Hồ sơ" }} />
<Tabs.Screen name="planner" options={{ title: "Mục tiêu" }} />
<Tabs.Screen name="assistant" options={{ title: "Trợ lý" }} />
</Tabs>; }
