import { useState } from "react";
import { Link } from "expo-router";
import { Screen } from "@/components/layouts/screen";
import { Button, Card, Check, Input, Copy, useTask } from "@/components/ui";
import { useSession } from "@/lib/session";
export default function Register() {
 const [email, setEmail] = useState(""); const [password, setPassword] = useState(""); const [adult, setAdult] = useState(false); const { api, login } = useSession(); const task = useTask();
 return <Screen title="Bắt đầu từ bạn" description="Ứng dụng hiện hỗ trợ người trưởng thành từ 18 tuổi."><Card title="Tạo tài khoản"><Input label="Email" value={email} onChangeText={setEmail} autoCapitalize="none" keyboardType="email-address" autoComplete="email" /><Input label="Mật khẩu (ít nhất 12 ký tự)" value={password} onChangeText={setPassword} secureTextEntry autoComplete="new-password" /><Check label="Tôi xác nhận đã đủ 18 tuổi" checked={adult} onChange={setAdult} /><Copy>Quyền xử lý hồ sơ sức khỏe và sử dụng cho nghiên cứu được lựa chọn riêng trong Hồ sơ.</Copy>{task.feedback}<Button title="Tạo tài khoản" disabled={task.busy || !adult} onPress={() => void task.run(async () => { await api("/auth/register", { method: "POST", body: { email: email.trim(), password, adult_attestation: adult } }); await login(email.trim(), password); }, "")} /><Link href="/(auth)/login"><Copy>Đã có tài khoản? Đăng nhập</Copy></Link></Card></Screen>;
}
