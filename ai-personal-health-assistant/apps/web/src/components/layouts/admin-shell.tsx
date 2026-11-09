"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";
import { useSession } from "@/lib/session";
const links = [{ href: "/dashboard", label: "Tổng quan" }, { href: "/users", label: "Người dùng" }, { href: "/health-profiles", label: "Hỗ trợ hồ sơ" }, { href: "/reports", label: "Theo dõi API" }, { href: "/settings", label: "Trạng thái tính năng" }];
export function AdminShell({ children }: { children: ReactNode }) {
 const { user, ready, logout } = useSession(); const router = useRouter(); const path = usePathname(); const [error, setError] = useState("");
 useEffect(() => { if (ready && (!user || user.role !== "admin")) router.replace("/login"); }, [ready, user, router]);
 if (!ready || !user || user.role !== "admin") return <main><p role="status">Đang kiểm tra phiên quản trị…</p></main>;
 return <div className="shell"><aside><Link href="/dashboard" className="brand"><span className="brand-mark">+</span><strong>Health Admin</strong></Link><span className="eyebrow">PERSONAL HEALTH ASSISTANT</span><nav>{links.map(link => <Link href={link.href} key={link.href} aria-current={path === link.href ? "page" : undefined}>{link.label}</Link>)}</nav><div className="account"><p>{user.email}</p><button className="secondary" onClick={async () => { try { await logout(); } catch { setError("Chưa thể đăng xuất khỏi máy chủ. Vui lòng thử lại."); } }}>Đăng xuất</button>{error && <p className="error">{error}</p>}</div></aside><main>{children}</main></div>;
}
