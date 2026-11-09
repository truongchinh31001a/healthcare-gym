import { Link } from "expo-router";
import { fieldLabel, type Progress } from "@health/contracts";
import { Screen } from "@/components/layouts/screen";
import { Card, Copy, useResource } from "@/components/ui";
export default function ReviewScreen() {
  const result = useResource<Progress>("/me/progress");
  return <Screen title="Nhìn lại theo tuần" description="Trung vị số đo theo ngày, tổng hợp riêng cho từng thiết bị và nguồn."><Link href="/(tabs)/dashboard"><Copy>← Về tổng quan</Copy></Link>{result.feedback}{result.data?.series.map(series => <Card key={series.stream_id} title={`${fieldLabel(series.field)} · ${series.device_model}`}>
    {series.weekly.length ? series.weekly.map(week => <Copy key={week.week_start}>Tuần {week.week_start}: {week.median.toFixed(2)} {series.unit} · {week.days_with_values} ngày có số đo{week.flags.length ? " · có lưu ý dữ liệu" : ""}</Copy>) : <Copy>Chưa có tuần đủ dữ liệu.</Copy>}
  </Card>)}<Card title="Dữ liệu mô tả"><Copy>Tổng hợp này không chẩn đoán, dự đoán sức khỏe hoặc tự thay đổi mục tiêu. Tuần thiếu dữ liệu được giữ đúng số ngày đã đo.</Copy></Card></Screen>;
}
