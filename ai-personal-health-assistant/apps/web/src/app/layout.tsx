import type { Metadata } from "next";
import type { ReactNode } from "react";
import { SessionProvider } from "@/lib/session";
import "./globals.css";
export const metadata: Metadata = { title: "Health Admin", description: "Personal Health Assistant administration" };
export default function RootLayout({ children }: { children: ReactNode }) { return <html lang="vi"><body><SessionProvider>{children}</SessionProvider></body></html>; }
