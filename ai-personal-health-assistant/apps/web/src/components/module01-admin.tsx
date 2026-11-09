"use client";
import { useEffect, useState } from "react";
import type { Overview, Page, AdminUser, Profile } from "@health/contracts";
import { useSession } from "@/lib/session";

function useData<T>(path: string) {
  const { api } = useSession(); const [data, setData] = useState<T | null>(null); const [error, setError] = useState(""); const [loading, setLoading] = useState(true); const [revision, setRevision] = useState(0);
  useEffect(() => { let live = true; setLoading(true); setError(""); api<T>(path).then(value => { if (live) setData(value); }).catch(error => { if (live) { setError(error.message); setData(null); } }).finally(() => { if (live) setLoading(false); }); return () => { live = false; }; }, [api, path, revision]);
  return { data, reload: () => setRevision(x => x+1), feedback: loading ? <p role="status">Đang tải…</p> : error ? <p className="error" role="alert">{error}</p> : null };
}

export function OverviewPanel({ settings = false }: { settings?: boolean }) {
  const result = useData<Overview>("/admin/overview");
  return <><header className="page-heading"><div><span className="eyebrow">MODULE 01 / VẬN HÀNH</span><h1>{settings ? "Trạng thái tính năng" : "Tổng quan hệ thống"}</h1><p>Quản lý tài khoản và tình trạng tích hợp hồ sơ cơ thể.</p></div><button className="secondary" onClick={result.reload}>Làm mới</button></header>{result.feedback}{result.data && <>
    {!settings && <div className="metrics">{[["Tài khoản", result.data.users], ["Số đo có lịch sử", result.data.observations], ["Nguồn phiếu", result.data.documents]].map(([label, value]) => <article className="card" key={label}><span className="muted">{label}</span><strong className="metric">{value}</strong></article>)}</div>}
    <section className="card"><h2>Khả năng đang hoạt động</h2><p>Hồ sơ, consent, nhập số đo, đối chiếu phiếu và tiến trình đã có API. Quy tắc mục tiêu chạy độc lập với AI.</p><div className="gate-list">{[["Đọc phiếu tự động", result.data.capabilities.ocr], ["Ước lượng từ ảnh cơ thể", result.data.capabilities.body_cv], ["Lập kế hoạch bằng AI", result.data.capabilities.generative_planner]].map(([label, gate]) => <div className="gate" key={String(label)}><div><strong>{String(label)}</strong><p>Đang chờ hoàn thành kiểm chứng trước khi cung cấp cho người dùng.</p></div><span className="badge">{typeof gate === "object" && gate.enabled ? "Đang mở" : "Đang khóa"}</span></div>)}</div></section><section className="card"><h2>Truy cập phục vụ hỗ trợ</h2><p>Quản trị viên chỉ xem được hồ sơ khi người dùng cấp quyền hỗ trợ. Quyền này có thể được rút lại; mọi lần xem đều được ghi vào nhật ký của người dùng.</p></section>
  </>}</>;
}

export function UsersPanel() {
  const { api } = useSession(); const [offset, setOffset] = useState(0); const result = useData<Page<AdminUser>>(`/admin/users?offset=${offset}&limit=25`); const [support, setSupport] = useState<{ profile: Profile | null; read_only: boolean } | null>(null); const [error, setError] = useState(""); const [busy, setBusy] = useState(false);
  return <><header className="page-heading"><div><span className="eyebrow">TÀI KHOẢN / HỖ TRỢ</span><h1>Người dùng</h1><p>{result.data?.total ?? "—"} tài khoản. Hồ sơ sức khỏe cần quyền hỗ trợ riêng.</p></div><button className="secondary" onClick={() => { setSupport(null); result.reload(); }}>Làm mới</button></header>{result.feedback}{error && <p role="alert" className="error">{error}</p>}<div className="card table-wrap"><table><thead><tr><th>Email</th><th>Vai trò</th><th>Quyền hỗ trợ</th><th>Thao tác</th></tr></thead><tbody>{result.data?.items.map(user => <tr key={user.id}><td>{user.email}</td><td>{user.role === "admin" ? "Quản trị" : "Người dùng"}</td><td><span className="badge">{user.support_access ? "Đã cấp quyền" : "Chưa cấp quyền"}</span></td><td><button disabled={!user.support_access || busy} onClick={async () => { setError(""); setSupport(null); setBusy(true); try { setSupport(await api(`/admin/users/${user.id}/support-profile`)); } catch (error) { setError(error instanceof Error ? error.message : "Không thể mở hồ sơ"); } finally { setBusy(false); } }}>Xem hồ sơ hỗ trợ</button></td></tr>)}</tbody></table><div className="actions"><button className="secondary" disabled={!offset} onClick={() => { setSupport(null); setOffset(Math.max(0, offset-25)); }}>Trang trước</button><button className="secondary" disabled={offset+25 >= (result.data?.total ?? 0)} onClick={() => { setSupport(null); setOffset(offset+25); }}>Trang sau</button></div></div>
    {support && <section className="card"><div className="page-heading"><h2>Hồ sơ hỗ trợ · chỉ đọc</h2><button className="secondary" onClick={() => setSupport(null)}>Đóng</button></div>{support.profile ? <dl><dt>Tên hiển thị</dt><dd>{support.profile.display_name}</dd><dt>Ngày sinh khai báo</dt><dd>{support.profile.birth_date}</dd><dt>Chiều cao khai báo</dt><dd>{support.profile.height_cm} cm</dd><dt>Múi giờ</dt><dd>{support.profile.timezone}</dd></dl> : <p>Người dùng chưa tạo hồ sơ.</p>}<p className="muted">Lần truy cập đã được ghi vào nhật ký riêng tư.</p></section>}
  </>;
}

export function MonitoringPanel() {
  const result = useData<{ scope: string; requests: { method: string; route: string; status: number; count: number }[] }>("/admin/metrics");
  return <><header className="page-heading"><div><span className="eyebrow">VẬN HÀNH</span><h1>Theo dõi API</h1><p>Số lượt gọi kể từ khi tiến trình API hiện tại khởi động. Không chứa nội dung hồ sơ.</p></div><button className="secondary" onClick={result.reload}>Làm mới</button></header>{result.feedback}<section className="card table-wrap"><table><thead><tr><th>Method</th><th>Route</th><th>Status</th><th>Lượt gọi</th></tr></thead><tbody>{result.data?.requests.map((row, i) => <tr key={i}><td>{row.method}</td><td><code>{row.route}</code></td><td>{row.status}</td><td>{row.count}</td></tr>)}</tbody></table></section></>;
}
