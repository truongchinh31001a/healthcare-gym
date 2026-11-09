import { useState } from "react";
import { Link } from "expo-router";
import { Screen } from "@/components/layouts/screen";
import { Button, Card, Input, Copy, useTask } from "@/components/ui";
import { useSession } from "@/lib/session";
export default function Login() {
 const [email, setEmail] = useState(""); const [password, setPassword] = useState(""); const { login } = useSession(); const task = useTask();
 return <Screen title="Chào bạn trở lại" description="Lưu hồ sơ và hiểu rõ các số đo của bạn theo thời gian."><Card title="Đăng nhập"><Input label="Email" value={email} onChangeText={setEmail} autoCapitalize="none" autoComplete="email" keyboardType="email-address" /><Input label="Mật khẩu" value={password} onChangeText={setPassword} secureTextEntry autoComplete="current-password" />{task.feedback}<Button title="Đăng nhập" disabled={task.busy} onPress={() => void task.run(() => login(email.trim(), password), "")} /><Link href="/(auth)/register"><Copy>Chưa có tài khoản? Đăng ký</Copy></Link></Card></Screen>;
}
