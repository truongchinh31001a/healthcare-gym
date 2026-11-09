"use client";
import { useEffect, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { useSession } from "@/lib/session";
export default function Login() {
 const { user, login } = useSession(); const router = useRouter(); const [email, setEmail] = useState(""); const [password, setPassword] = useState(""); const [error, setError] = useState(""); const [busy, setBusy] = useState(false);
 useEffect(() => { if (user?.role === "admin") router.replace("/dashboard"); }, [user, router]);
 async function submit(event: FormEvent) { event.preventDefault(); setBusy(true); setError(""); try { await login(email.trim(), password); } catch (error) { setError(error instanceof Error ? error.message : "Không kết nối được máy chủ"); } finally { setBusy(false); } }
 return <main className="login-page"><div className="login-intro"><span className="eyebrow">PERSONAL HEALTH ASSISTANT</span><h1>Hỗ trợ đúng người.<br />Tôn trọng từng dữ liệu.</h1><p>Cổng quản trị hồ sơ và vận hành. Dữ liệu sức khỏe được giới hạn theo quyền người dùng đã cấp.</p><div className="login-orbit" aria-hidden="true"><span>+</span></div></div><form className="card login-card" onSubmit={submit}><span className="eyebrow">CỔNG QUẢN TRỊ</span><h2>Đăng nhập</h2><p>Dùng tài khoản quản trị do người vận hành tạo.</p><label>Email<input type="email" autoComplete="username" required value={email} onChange={e => setEmail(e.target.value)} /></label><label>Mật khẩu<input type="password" autoComplete="current-password" required maxLength={128} value={password} onChange={e => setPassword(e.target.value)} /></label>{error && <p className="error" role="alert">{error}</p>}<button disabled={busy}>{busy ? "Đang đăng nhập…" : "Vào trang quản trị"}</button><p className="muted">Tài khoản cá nhân sử dụng ứng dụng di động.</p></form></main>;
}
