import { useEffect, useState } from "react";
import { Alert, Share, Text, View } from "react-native";
import type { Consent, Profile, HealthContext, Purpose, TriState } from "@health/contracts";
import { Screen } from "@/components/layouts/screen";
import { Button, Card, Check, Choice, Copy, Input, useResource, useTask, styles } from "@/components/ui";
import { useSession } from "@/lib/session";

const purposeLabels: Record<Purpose, string> = {
  health_data_processing: "Xử lý hồ sơ và số đo để hiển thị tiến trình",
  document_processing: "Lưu và xử lý phiếu InBody (lưu nguồn tối đa 30 ngày)",
  body_image_processing: "Cho phép xử lý ảnh cơ thể khi tính năng được mở",
  admin_support: "Cho quản trị viên xem hồ sơ để hỗ trợ (chỉ đọc, có nhật ký)",
  research_training: "Cho phép sử dụng cho nghiên cứu riêng biệt (hiện chưa thu thập huấn luyện)",
};
const riskLabels = { pregnancy: "Đang mang thai hoặc cho con bú", eating_disorder_risk: "Có lo ngại về rối loạn ăn uống", clinician_restrictions: "Có giới hạn vận động/dinh dưỡng từ bác sĩ", acute_red_flags: "Đang có triệu chứng cần được khám ngay" } as const;

export default function ProfileScreen() {
  const { api, user, logout, forget } = useSession(); const task = useTask();
  const profile = useResource<Profile | null>("/me/profile"); const consents = useResource<Consent[]>("/me/consents"); const context = useResource<HealthContext>("/me/health-context");
  const [name, setName] = useState(""); const [birthday, setBirthday] = useState(""); const [height, setHeight] = useState("");
  const [gender, setGender] = useState<Profile["gender"]>("unspecified"); const [zone, setZone] = useState("Asia/Bangkok");
  const [risks, setRisks] = useState<HealthContext>({ version: 0, pregnancy: "unknown", eating_disorder_risk: "unknown", clinician_restrictions: "unknown", acute_red_flags: "unknown", notes: "" });
  const [password, setPassword] = useState("");
  useEffect(() => { if (profile.data) { const p = profile.data; setName(p.display_name); setBirthday(p.birth_date); setHeight(String(p.height_cm)); setGender(p.gender); setZone(p.timezone); } }, [profile.data]);
  useEffect(() => { if (context.data) { const { version, pregnancy, eating_disorder_risk, clinician_restrictions, acute_red_flags, notes } = context.data; setRisks({ version, pregnancy, eating_disorder_risk, clinician_restrictions, acute_red_flags, notes }); } }, [context.data]);
  const processing = consents.data?.find(c => c.purpose === "health_data_processing")?.granted;
  return <Screen title="Hồ sơ của bạn" description={user?.email ?? "Thông tin cá nhân và quyền riêng tư"}>
    {task.feedback}
    <Card title="Bạn chọn cách dùng dữ liệu">{consents.feedback}{consents.data?.map(consent => <Check key={consent.purpose} label={purposeLabels[consent.purpose]} checked={consent.granted} onChange={granted => { if (task.busy) return; void task.run(async () => { await api("/me/consents", { method: "POST", body: { purpose: consent.purpose, granted } }); consents.reload(); }, "Đã cập nhật lựa chọn"); }} />)}<Copy>Rút quyền xử lý sẽ dừng thao tác và phân tích mới. Bạn vẫn có thể đọc, xuất hoặc xóa dữ liệu đã lưu. Xóa nguồn phiếu cũng xóa các số đo lấy từ phiếu đó.</Copy></Card>
    <Card title="Thông tin cơ bản">{profile.feedback}<Input label="Tên hiển thị" value={name} onChangeText={setName} /><Input label="Ngày sinh (YYYY-MM-DD)" value={birthday} onChangeText={setBirthday} placeholder="1995-04-20" /><Input label="Chiều cao (cm)" value={height} onChangeText={setHeight} keyboardType="decimal-pad" /><Choice label="Giới tính khai báo" value={gender} onChange={setGender} options={[{ value: "unspecified", label: "Chưa cung cấp" }, { value: "male", label: "Nam" }, { value: "female", label: "Nữ" }]} /><Input label="Múi giờ IANA" value={zone} onChangeText={setZone} autoCapitalize="none" /><Button title="Lưu hồ sơ" disabled={task.busy || profile.loading || !processing} onPress={() => void task.run(async () => { await api("/me/profile", { method: "PUT", body: { display_name: name, birth_date: birthday, height_cm: Number(height), gender, timezone: zone, version: profile.data?.version ?? 0 } }); profile.reload(); })} />{!processing && <Copy>Hãy cấp quyền xử lý hồ sơ trước khi lưu.</Copy>}</Card>
    <Card title="Bối cảnh để xét mục tiêu">{context.feedback}<Copy>Chưa biết sẽ được giữ nguyên để yêu cầu bổ sung thông tin. Các câu trả lời này không thay thế đánh giá của bác sĩ.</Copy>{Object.entries(riskLabels).map(([key, label]) => <Choice key={key} label={label} value={risks[key as keyof typeof riskLabels]} options={[{ value: "unknown", label: "Chưa biết" }, { value: "no", label: "Không" }, { value: "yes", label: "Có" }]} onChange={(value: TriState) => setRisks(old => ({ ...old, [key]: value }))} />)}<Input label="Lưu ý của bạn" value={risks.notes} onChangeText={notes => setRisks(old => ({ ...old, notes }))} multiline /><Button title="Lưu bối cảnh" disabled={task.busy || context.loading || !processing} onPress={() => void task.run(async () => { await api("/me/health-context", { method: "PUT", body: risks }); context.reload(); })} /></Card>
    <Card title="Dữ liệu và tài khoản"><Button title="Xuất dữ liệu JSON" disabled={task.busy} onPress={() => void task.run(async () => { const data = await api("/me/export"); await Share.share({ title: "Bản xuất hồ sơ sức khỏe riêng tư", message: JSON.stringify(data, null, 2) }); }, "Đã mở tùy chọn lưu/chia sẻ")} /><Copy>Bản xuất có hồ sơ và nhật ký riêng tư. File phiếu gốc được xuất riêng qua API tải nguồn.</Copy><Button title="Đăng xuất" disabled={task.busy} onPress={() => void task.run(logout, "")} /><View style={{ borderTopWidth: 1, borderColor: "#d9e8e3", paddingTop: 15, gap: 12 }}><Text style={styles.title}>Xóa tài khoản</Text><Copy>Xóa toàn bộ hồ sơ, số đo, phiếu và phiên đăng nhập trên máy chủ. Không thể khôi phục từ ứng dụng.</Copy><Input label="Nhập mật khẩu để xóa" value={password} onChangeText={setPassword} secureTextEntry /><Button title="Xóa toàn bộ tài khoản" danger disabled={task.busy || !password} onPress={() => Alert.alert("Xóa tài khoản?", "Dữ liệu đang dùng sẽ bị xóa vĩnh viễn. Bản sao bạn đã xuất cần tự xóa riêng.", [{ text: "Hủy", style: "cancel" }, { text: "Xóa tài khoản", style: "destructive", onPress: () => void task.run(async () => { await api("/me/account", { method: "DELETE", body: { password } }); forget(); }, "") }])} /></View></Card>
  </Screen>;
}
