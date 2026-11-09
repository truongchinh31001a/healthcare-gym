import { Link } from "expo-router";
import { Text, View } from "react-native";
import { fieldLabel, type Progress } from "@health/contracts";
import { Screen } from "@/components/layouts/screen";
import { Button, Card, Copy, styles, theme, useResource } from "@/components/ui";

export default function DashboardScreen() {
  const { data, feedback, reload } = useResource<Progress>("/me/progress");
  return <Screen title="Từng bước hiểu cơ thể" description="Số đo theo từng nguồn và thiết bị. Ngày chưa đo được để trống.">
    {feedback}<Button title="Làm mới tiến trình" onPress={reload} />
    {data && !data.series.length && <Card title="Bắt đầu bằng một số đo"><Copy>Hoàn thiện hồ sơ, sau đó ghi lần đo đầu tiên. Cần ít nhất 4 ngày đo trong 28 ngày, trải dài 14 ngày để mô tả xu hướng.</Copy><Link href="/(tabs)/tracking"><Copy>Ghi số đo →</Copy></Link></Card>}
    {data?.series.map(series => <Card key={series.stream_id} title={fieldLabel(series.field)}><Text style={styles.metric}>{series.latest?.value?.toFixed(2) ?? "—"} <Text style={{ fontSize: 17 }}>{series.unit}</Text></Text><Copy>{series.device_model} · {series.provenance === "extracted" ? "Từ phiếu đã đối chiếu" : "Đo và nhập thủ công"} · {series.latest?.day ?? "Chưa rõ ngày đo"}</Copy>
      {series.trend.status === "descriptive_only" ? <Copy>Thay đổi mô tả: {series.trend.slope_per_week?.toFixed(2)} {series.unit}/tuần</Copy> : <Copy>Chưa đủ điều kiện kết luận xu hướng: {series.trend.withheld_reasons.map(reason => ({ insufficient_temporal_support: "chưa đủ ngày đo", stale_or_missing: "dữ liệu cũ hoặc thiếu", large_data_gap: "khoảng trống đo quá dài", source_not_reviewed_measurement: "nguồn chưa được xác nhận" }[reason] ?? reason)).join(", ")}</Copy>}
      <View style={{ gap: 10 }}>{series.days.filter(day => day.value !== null).slice(-7).map(day => <View key={day.day} style={styles.row}><Text style={{ color: theme.muted, width: 95 }}>{day.day}</Text><View style={{ flex: 1, backgroundColor: theme.light, borderRadius: 6, padding: 8 }}><Text style={{ color: theme.ink }}>{day.value?.toFixed(2)} {series.unit}{day.flags.length ? " · Có lưu ý" : ""}</Text></View></View>)}</View><Copy>So với 7 ngày trước: {series.recent_week_comparison.change === null ? "chưa đủ dữ liệu so sánh" : `${series.recent_week_comparison.change.toFixed(2)} ${series.recent_week_comparison.change_unit}`}</Copy></Card>)}
    <Card title="Nhìn lại theo tuần"><Copy>Tổng hợp dựa trên trung vị theo ngày. Các số đo từ thiết bị khác nhau được giữ riêng.</Copy><Link href="/weekly-review"><Copy>Mở tổng hợp tuần →</Copy></Link></Card>
  </Screen>;
}
