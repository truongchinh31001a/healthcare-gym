"""Create the initial admin web / React Native / FastAPI workspace safely."""

import json
from pathlib import Path
from textwrap import dedent

ROOT = Path(__file__).resolve().parents[1]
FILES = {}


def add(path, content):
    FILES[path] = dedent(content).lstrip("\n")


def manifest(path, value):
    FILES[path] = json.dumps(value, indent=2, ensure_ascii=False) + "\n"


manifest("package.json", {
    "name": "ai-personal-health-assistant", "version": "0.1.0", "private": True,
    "workspaces": ["apps/web", "apps/mobile", "packages/contracts"],
    "engines": {"node": "^24.3.0 || >=26.0.0"},
    "scripts": {"dev:web": "npm run dev --workspace=@health/web", "dev:mobile": "npm run start --workspace=@health/mobile",
                "build:web": "npm run build --workspace=@health/web", "typecheck": "npm run typecheck --workspaces --if-present"},
})
manifest("apps/web/package.json", {
    "name": "@health/web", "version": "0.1.0", "private": True,
    "scripts": {"dev": "next dev", "build": "next build", "start": "next start", "typecheck": "tsc --noEmit"},
    "dependencies": {"@health/contracts": "*", "next": "16.4.2", "react": "19.3.0", "react-dom": "19.3.0"},
    "devDependencies": {"typescript": "~6.0.3", "@types/react": "~19.3.0", "@types/react-dom": "^19.0.0", "@types/node": "^24.0.0"},
})
manifest("apps/web/tsconfig.json", {"compilerOptions": {
    "target": "ES2022", "lib": ["dom", "dom.iterable", "esnext"], "allowJs": True,
    "skipLibCheck": True, "strict": True, "noEmit": True, "esModuleInterop": True,
    "module": "esnext", "moduleResolution": "bundler", "resolveJsonModule": True,
    "isolatedModules": True, "jsx": "react-jsx", "incremental": True,
    "plugins": [{"name": "next"}], "paths": {"@/*": ["./src/*"]}},
    "include": ["next-env.d.ts", "src/**/*.ts", "src/**/*.tsx", ".next/types/**/*.ts", ".next/dev/types/**/*.ts"], "exclude": ["node_modules"]})
add("apps/web/next-env.d.ts", '/// <reference types="next" />\n/// <reference types="next/image-types/global" />\n')
add("apps/web/next.config.ts", '''
    import type { NextConfig } from "next";
    import path from "node:path";
    const config: NextConfig = {
      output: "standalone",
      outputFileTracingRoot: path.join(__dirname, "../.."),
      transpilePackages: ["@health/contracts"],
    };
    export default config;
''')
add("apps/web/src/app/layout.tsx", '''
    import type { Metadata } from "next";
    import type { ReactNode } from "react";
    import "./globals.css";
    export const metadata: Metadata = { title: "Health Admin", description: "Personal Health Assistant administration" };
    export default function RootLayout({ children }: { children: ReactNode }) {
      return <html lang="vi"><body>{children}</body></html>;
    }
''')
add("apps/web/src/app/page.tsx", 'import { redirect } from "next/navigation";\nexport default function Home() { redirect("/dashboard"); }\n')
add("apps/web/src/app/globals.css", '''
    * { box-sizing: border-box; }
    body { margin: 0; color: #172c39; background: #f5f8fa; font-family: Arial, sans-serif; }
    a { color: #156b65; text-decoration: none; }
    .shell { display: grid; grid-template-columns: 240px 1fr; min-height: 100vh; }
    aside { padding: 30px 20px; border-right: 1px solid #dae5e9; background: white; }
    aside nav { display: grid; gap: 18px; margin-top: 28px; }
    main { padding: 42px; max-width: 1100px; }
    h1 { font-size: 30px; } p { line-height: 1.7; }
    .placeholder { margin-top: 30px; border: 1px dashed #a8c5ca; padding: 24px; border-radius: 12px; background: white; }
    @media (max-width: 760px) { .shell { grid-template-columns: 1fr; } aside { border-right: 0; } main { padding: 24px; } }
''')
admin_routes = {
    "dashboard": ("Tổng quan quản trị", "Theo dõi hoạt động hệ thống và các báo cáo quản trị."),
    "users": ("Quản lý người dùng", "Tra cứu tài khoản, trạng thái và vai trò người dùng."),
    "health-profiles": ("Quản lý hồ sơ sức khỏe", "Các luồng quản trị hồ sơ cần phân quyền và ghi nhật ký truy cập."),
    "tracking": ("Quản lý dữ liệu theo dõi", "Theo dõi tình trạng đồng bộ và chất lượng dữ liệu."),
    "plans": ("Quản lý kế hoạch", "Quản lý mẫu kế hoạch và xem các luồng hỗ trợ người dùng."),
    "ai-sessions": ("Quản lý phiên AI", "Theo dõi vận hành, phản hồi và đánh giá chất lượng AI."),
    "weekly-reviews": ("Quản lý đánh giá tuần", "Theo dõi quá trình tổng hợp báo cáo tuần."),
    "reports": ("Báo cáo hệ thống", "Báo cáo tổng hợp cho quản trị viên."),
    "settings": ("Cấu hình hệ thống", "Cấu hình chức năng và chính sách truy cập."),
}
links = ",\n".join(f'  {{ href: "/{route}", label: {json.dumps(title, ensure_ascii=False)} }}' for route, (title, _) in admin_routes.items())
add("apps/web/src/components/layouts/admin-shell.tsx", '''
    import Link from "next/link";
    import type { ReactNode } from "react";
    const links = [
    LINKS
    ];
    export function AdminShell({ children }: { children: ReactNode }) {
      return <div className="shell"><aside><strong>Health Admin</strong><nav>
        {links.map(item => <Link key={item.href} href={item.href}>{item.label}</Link>)}
      </nav></aside><main>{children}</main></div>;
    }
'''.replace("LINKS", links))
add("apps/web/src/components/layouts/admin-section.tsx", '''
    export function AdminSection({ title, description }: { title: string; description: string }) {
      return <section><h1>{title}</h1><p>{description}</p>
        <div className="placeholder">Khung chức năng. Chưa kết nối dữ liệu và xử lý nghiệp vụ.</div>
      </section>;
    }
''')
add("apps/web/src/app/(admin)/layout.tsx", '''
    import type { ReactNode } from "react";
    import { AdminShell } from "@/components/layouts/admin-shell";
    export default function Layout({ children }: { children: ReactNode }) { return <AdminShell>{children}</AdminShell>; }
''')
for route, (title, description) in admin_routes.items():
    add(f"apps/web/src/app/(admin)/{route}/page.tsx", 'import { AdminSection } from "@/components/layouts/admin-section";\n'
        + f'export default function Page() {{ return <AdminSection title={json.dumps(title, ensure_ascii=False)} description={json.dumps(description, ensure_ascii=False)} />; }}\n')
add("apps/web/src/app/(auth)/login/page.tsx", '''
    import { AdminSection } from "@/components/layouts/admin-section";
    export default function Login() { return <main><AdminSection title="Đăng nhập quản trị"
      description="Khung đăng nhập dành cho tài khoản quản trị. Cần kết nối xác thực và phân quyền API." /></main>; }
''')

# Versions match the official expo-template-default 58.0.25 dependency set.
mobile_dependencies = {
    "@health/contracts": "*", "@expo/ui": "~58.0.21", "expo": "~58.0.16", "expo-constants": "~58.0.12",
    "expo-device": "~58.0.5", "expo-font": "~58.0.9", "expo-glass-effect": "~58.0.4", "expo-image": "~58.0.16",
    "expo-linking": "~58.0.13", "expo-router": "~58.0.24", "expo-splash-screen": "~58.0.10", "expo-status-bar": "~58.0.3",
    "expo-symbols": "~58.0.4", "expo-system-ui": "~58.0.6", "expo-web-browser": "~58.0.6",
    "react": "19.3.0", "react-dom": "19.3.0", "react-native": "0.88.0", "react-native-gesture-handler": "~3.3.0",
    "react-native-reanimated": "4.7.1", "react-native-safe-area-context": "~5.10.1", "react-native-screens": "~4.30.0",
    "react-native-web": "~0.21.4", "react-native-worklets": "0.13.0",
}
manifest("apps/mobile/package.json", {"name": "@health/mobile", "version": "0.1.0", "private": True,
    "main": "expo-router/entry", "scripts": {"start": "expo start", "android": "expo start --android",
    "ios": "expo start --ios", "typecheck": "tsc --noEmit"}, "dependencies": mobile_dependencies,
    "devDependencies": {"@types/react": "~19.3.0", "typescript": "~6.0.3"}})
manifest("apps/mobile/app.json", {"expo": {"name": "Personal Health Assistant", "slug": "personal-health-assistant",
    "version": "0.1.0", "scheme": "healthassistant", "orientation": "portrait", "userInterfaceStyle": "light",
    "plugins": ["expo-router"], "ios": {"supportsTablet": True, "bundleIdentifier": "com.example.healthassistant"},
    "android": {"package": "com.example.healthassistant"}}})
manifest("apps/mobile/tsconfig.json", {"extends": "expo/tsconfig.base", "compilerOptions": {"strict": True,
    "paths": {"@/*": ["./src/*"]}}, "include": ["src/**/*.ts", "src/**/*.tsx", "expo-env.d.ts", ".expo/types/**/*.ts"]})
add("apps/mobile/expo-env.d.ts", '/// <reference types="expo/types" />\n')
add("apps/mobile/metro.config.js", 'const { getDefaultConfig } = require("expo/metro-config");\nmodule.exports = getDefaultConfig(__dirname);\n')
add("apps/mobile/src/app/_layout.tsx", '''
    import { Stack } from "expo-router";
    import { SafeAreaProvider } from "react-native-safe-area-context";
    export default function Layout() {
      return <SafeAreaProvider><Stack><Stack.Screen name="(tabs)" options={{ headerShown: false }} />
        <Stack.Screen name="(auth)" options={{ headerShown: false }} />
        <Stack.Screen name="weekly-review" options={{ title: "Đánh giá tuần" }} />
      </Stack></SafeAreaProvider>;
    }
''')
add("apps/mobile/src/app/index.tsx", 'import { Redirect } from "expo-router";\nexport default function Index() { return <Redirect href="/(tabs)/dashboard" />; }\n')
add("apps/mobile/src/app/(auth)/_layout.tsx", 'import { Stack } from "expo-router";\nexport default function Layout() { return <Stack />; }\n')
add("apps/mobile/src/components/layouts/screen.tsx", '''
    import type { ReactNode } from "react";
    import { StyleSheet, Text, View } from "react-native";
    import { SafeAreaView } from "react-native-safe-area-context";
    export function Screen({ title, description, children }: { title: string; description: string; children?: ReactNode }) {
      return <SafeAreaView style={styles.root}><Text style={styles.title}>{title}</Text><Text style={styles.text}>{description}</Text>
        <View style={styles.card}><Text>Khung chức năng. Chưa kết nối dữ liệu và xử lý nghiệp vụ.</Text></View>{children}
      </SafeAreaView>;
    }
    const styles = StyleSheet.create({ root: { flex: 1, backgroundColor: "#f5f8fa", padding: 24, gap: 18 },
      title: { fontSize: 28, fontWeight: "700", color: "#172c39" }, text: { fontSize: 16, lineHeight: 25, color: "#48616d" },
      card: { backgroundColor: "white", padding: 20, borderRadius: 12 } });
''')
mobile_routes = {
    "dashboard": ("Tổng quan sức khỏe", "Xem hoạt động, chỉ số và kế hoạch cá nhân."),
    "profile": ("Hồ sơ cá nhân", "Quản lý thông tin và mục tiêu sức khỏe của bạn."),
    "tracking": ("Theo dõi hằng ngày", "Ghi nhận vận động, giấc ngủ, dinh dưỡng và chỉ số cơ thể."),
    "planner": ("Kế hoạch cá nhân", "Xem và điều chỉnh kế hoạch phù hợp với mục tiêu của bạn."),
    "assistant": ("Trợ lý AI", "Trao đổi với trợ lý dựa trên ngữ cảnh sức khỏe được phép sử dụng."),
}
tab_screens = "\n".join(f'<Tabs.Screen name="{route}" options={{{{ title: {json.dumps(title, ensure_ascii=False)} }}}} />' for route, (title, _) in mobile_routes.items())
add("apps/mobile/src/app/(tabs)/_layout.tsx", 'import { Tabs } from "expo-router";\nexport default function Layout() { return <Tabs screenOptions={{ headerShown: false }}>\n' + tab_screens + '\n</Tabs>; }\n')
for route, (title, description) in mobile_routes.items():
    add(f"apps/mobile/src/app/(tabs)/{route}.tsx", 'import { Screen } from "@/components/layouts/screen";\n'
        + ('import { Link } from "expo-router";\n' if route == "dashboard" else "")
        + f'export default function Page() {{ return <Screen title={json.dumps(title, ensure_ascii=False)} description={json.dumps(description, ensure_ascii=False)}>'
        + ('<Link href="/weekly-review">Xem đánh giá tuần</Link>' if route == "dashboard" else "") + '</Screen>; }\n')
for route, title in (("(auth)/login", "Đăng nhập"), ("(auth)/register", "Đăng ký"), ("weekly-review", "Đánh giá tuần")):
    add(f"apps/mobile/src/app/{route}.tsx", 'import { Screen } from "@/components/layouts/screen";\n'
        + f'export default function Page() {{ return <Screen title={json.dumps(title, ensure_ascii=False)} description="Luồng cá nhân trên ứng dụng di động." />; }}\n')

manifest("packages/contracts/package.json", {"name": "@health/contracts", "version": "0.1.0", "private": True,
    "types": "./src/index.ts", "exports": {".": "./src/index.ts"}, "scripts": {"typecheck": "tsc --noEmit"},
    "devDependencies": {"typescript": "~6.0.3"}})
manifest("packages/contracts/tsconfig.json", {"compilerOptions": {"target": "ES2022", "module": "ESNext",
    "moduleResolution": "Bundler", "strict": True, "noEmit": True, "skipLibCheck": True}, "include": ["src/**/*.ts"]})
add("packages/contracts/src/index.ts", '''
    export type UserRole = "admin" | "user";
    export interface HealthResponse { status: "ok"; service: "api" | "ai-service"; }
''')
for target in ("web", "mobile"):
    prefix = 'const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";' if target == "web" else '''import { Platform } from "react-native";
const API_URL = process.env.EXPO_PUBLIC_API_URL ?? (Platform.OS === "android" ? "http://10.0.2.2:8000" : "http://localhost:8000");'''
    add(f"apps/{target}/src/lib/api-client.ts", 'import type { HealthResponse } from "@health/contracts";\n' + prefix + '''
export async function getApiHealth(): Promise<HealthResponse> {
  const response = await fetch(`${API_URL}/health`);
  if (!response.ok) throw new Error(`API request failed: ${response.status}`);
  return response.json() as Promise<HealthResponse>;
}
''')
    add(f"apps/{target}/src/lib/utils.ts", 'export function formatMeasurement(value: number, unit: string): string { return `${value.toFixed(1)} ${unit}`; }\n')
    add(f"apps/{target}/src/types/index.ts", 'export type { HealthResponse, UserRole } from "@health/contracts";\n')

modules = ("auth", "users", "health_profile", "daily_tracking", "dashboard", "health_planner", "ai_assistant", "weekly_review")
add("apps/api/app/__init__.py", '"""Main HTTP API package."""\n')
add("apps/api/app/core/__init__.py", "")
add("apps/api/app/core/config.py", '''
    from pydantic_settings import BaseSettings, SettingsConfigDict
    class Settings(BaseSettings):
        model_config = SettingsConfigDict(env_file=".env", extra="ignore")
        database_url: str = "sqlite+pysqlite:///./health.db"
        ai_service_url: str = "http://localhost:8001"
        cors_origins: list[str] = ["http://localhost:3000"]
    settings = Settings()
''')
add("apps/api/app/core/database.py", '''
    from sqlalchemy import create_engine
    from sqlalchemy.orm import DeclarativeBase, sessionmaker
    from app.core.config import settings
    class Base(DeclarativeBase):
        pass
    engine = create_engine(settings.database_url, pool_pre_ping=True)
    SessionLocal = sessionmaker(bind=engine, autoflush=False)
''')
add("apps/api/app/core/security.py", '''
    from enum import StrEnum
    from pydantic import BaseModel
    class Role(StrEnum):
        ADMIN = "admin"
        USER = "user"
    class Principal(BaseModel):
        user_id: str
        role: Role
''')
add("apps/api/app/core/exceptions.py", '''
    class DomainError(Exception):
        """Base class for domain exceptions; map concrete errors to HTTP later."""
''')
add("apps/api/app/shared/__init__.py", "")
add("apps/api/app/shared/dependencies.py", '''
    from fastapi import Depends, HTTPException
    from app.core.database import SessionLocal
    from app.core.security import Principal, Role
    def get_db():
        with SessionLocal() as session:
            yield session
    def get_current_user() -> Principal:
        raise HTTPException(status_code=501, detail="Authentication is not configured in this scaffold")
    def require_admin(user: Principal = Depends(get_current_user)) -> Principal:
        if user.role != Role.ADMIN:
            raise HTTPException(status_code=403, detail="Administrator role required")
        return user
''')
add("apps/api/app/shared/pagination.py", '''
    from pydantic import BaseModel, Field
    class Pagination(BaseModel):
        page: int = Field(default=1, ge=1)
        page_size: int = Field(default=20, ge=1, le=100)
''')
imports, names = [], []
for name in modules:
    add(f"apps/api/app/modules/{name}/__init__.py", f'"""{name} module: implement schemas, services and repositories here."""\n')
    add(f"apps/api/app/modules/{name}/router.py", f'from fastapi import APIRouter\nrouter = APIRouter(prefix="/{name.replace("_", "-")}", tags=["{name}"])\n')
    imports.append(f"from .{name}.router import router as {name}_router")
    names.append(f"{name}_router")
add("apps/api/app/modules/__init__.py", "\n".join(imports) + "\n\nrouters = (" + ", ".join(names) + ",)\n")
add("apps/api/app/main.py", '''
    from typing import Literal
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware
    from pydantic import BaseModel
    from app.core.config import settings
    from app.modules import routers
    class HealthResponse(BaseModel):
        status: Literal["ok"] = "ok"
        service: Literal["api"] = "api"
    app = FastAPI(title="Personal Health Assistant API", version="0.1.0")
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins,
                       allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
    for router in routers:
        app.include_router(router, prefix="/api/v1")
    @app.get("/health", response_model=HealthResponse, tags=["system"])
    def health():
        return HealthResponse()
''')
add("apps/api/app/integrations/__init__.py", "")
add("apps/api/app/integrations/ai_client.py", '''
    import httpx
    from app.core.config import settings
    async def get_ai_service_health() -> dict:
        async with httpx.AsyncClient(base_url=settings.ai_service_url, timeout=10) as client:
            response = await client.get("/health")
            response.raise_for_status()
            return response.json()
''')
add("services/ai-service/app/__init__.py", '"""Internal AI service package."""\n')
add("services/ai-service/app/main.py", '''
    from typing import Literal
    from fastapi import FastAPI
    from pydantic import BaseModel
    class HealthResponse(BaseModel):
        status: Literal["ok"] = "ok"
        service: Literal["ai-service"] = "ai-service"
    app = FastAPI(title="Personal Health Assistant AI Service", version="0.1.0")
    @app.get("/health", response_model=HealthResponse, tags=["system"])
    def health():
        return HealthResponse()
''')
for agent, operation in (("health_planner", "create_plan"), ("health_assistant", "answer"), ("weekly_reviewer", "review_week")):
    add(f"services/ai-service/app/agents/{agent}.py", f'async def {operation}(context: dict) -> dict:\n    raise NotImplementedError("Configure context, guardrails and an LLM provider before enabling this agent")\n')
add("services/ai-service/app/llm/client.py", '''
    from typing import Protocol
    class LLMClient(Protocol):
        async def generate(self, *, system: str, user: str) -> str: ...
''')
for service, package, dependencies in (
    ("apps/api", "health-assistant-api", ["fastapi>=0.139,<1", "uvicorn[standard]>=0.51,<1", "pydantic-settings>=2.15,<3",
        "sqlalchemy>=2.0,<3", "psycopg[binary]>=3.2,<4", "alembic>=1.16,<2", "httpx>=0.28,<1"]),
    ("services/ai-service", "health-assistant-ai-service", ["fastapi>=0.139,<1", "uvicorn[standard]>=0.51,<1", "pydantic-settings>=2.15,<3", "httpx>=0.28,<1"]),
):
    add(f"{service}/pyproject.toml", '[build-system]\nrequires = ["setuptools>=77"]\nbuild-backend = "setuptools.build_meta"\n\n'
        + f'[project]\nname = "{package}"\nversion = "0.1.0"\nrequires-python = ">=3.11"\n'
        + 'dependencies = ' + json.dumps(dependencies) + '\n\n[project.optional-dependencies]\ndev = ["pytest>=9,<10", "httpx>=0.28,<1"]\n\n'
        + '[tool.setuptools.packages.find]\ninclude = ["app*"]\n\n[tool.pytest.ini_options]\ntestpaths = ["tests"]\npythonpath = ["."]\n')
    add(f"{service}/Dockerfile", 'FROM python:3.12-slim\nWORKDIR /service\nCOPY pyproject.toml ./\nCOPY app ./app\nRUN pip install --no-cache-dir .\nEXPOSE 8000\nCMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]\n')
    add(f"{service}/tests/.gitkeep", "")
add("scripts/seed_data.py", '"""Seed-data entrypoint; domain models and fixtures will be added later."""\n\nif __name__ == "__main__":\n    print("No domain fixtures configured yet.")\n')
add("scripts/init_db.sh", '#!/usr/bin/env sh\nset -eu\nprintf "%s\\n" "Add Alembic migrations in apps/api/alembic before initializing domain tables."\n')
add("scripts/export_openapi.py", '''
    """Export the current API schema without connecting to the database."""
    import json
    from pathlib import Path
    import sys
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "apps/api"))
    from app.main import app
    target = root / "packages/contracts/openapi.json"
    target.write_text(json.dumps(app.openapi(), ensure_ascii=False, indent=2) + "\\n", encoding="utf-8")
    print(target)
''')

directories = ["apps/web/public", "apps/api/alembic/versions", "infrastructure/docker", "infrastructure/nginx", "infrastructure/monitoring"]
for target in ("web", "mobile"):
    directories += [f"apps/{target}/src/{name}" for name in ("hooks", "stores", "components/ui", "components/charts", "components/forms")]
for feature in ("auth", "users", "health-profiles", "daily-tracking", "dashboard", "health-planner", "ai-sessions", "weekly-review", "reports", "settings"):
    directories.append(f"apps/web/src/features/{feature}")
for feature in ("auth", "health-profile", "daily-tracking", "dashboard", "health-planner", "ai-assistant", "weekly-review"):
    directories.append(f"apps/mobile/src/features/{feature}")
directories += [f"apps/mobile/src/{name}" for name in ("assets", "services", "constants")]
for name in ("agents", "prompts", "schemas", "context", "guardrails", "llm", "evaluation"):
    directories.append(f"services/ai-service/app/{name}")
    add(f"services/ai-service/app/{name}/__init__.py", "")
for name in ("architecture", "database", "api", "ai-design", "security", "roadmap"):
    directories.append(f"docs/{name}")


def main():
    created = 0
    for relative, content in FILES.items():
        path = ROOT / relative
        if path.exists():
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        created += 1
    for relative in directories:
        path = ROOT / relative
        path.mkdir(parents=True, exist_ok=True)
        if not any(path.iterdir()):
            (path / ".gitkeep").write_text("", encoding="utf-8")
    print(f"Created {created} scaffold files in {ROOT}")


if __name__ == "__main__":
    main()
