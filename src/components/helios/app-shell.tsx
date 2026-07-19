import { Link, Outlet, useRouterState } from "@tanstack/react-router";
import { useHeliosAuth as useAuth } from "@/lib/auth/helios-auth";
import {
  LayoutDashboard,
  ListTree,
  FileCode2,
  ClipboardCheck,
  Database,
  Search,
  FlaskConical,
  Settings,
  Bell,
  Command,
  LogOut,
  ScanSearch,
  Rocket,
  KeyRound,
} from "lucide-react";
import { HeliosMark, StatusBadge } from "./primitives";
import { ProjectSelector } from "./project-selector";
import { ProjectSelectionProvider } from "@/contexts/project-selection";
import { useUserMe } from "@/hooks/use-user-me";
import { cn } from "@/lib/utils";

function UserIdentity() {
  const { user, loading, signOut } = useAuth();
  const { me } = useUserMe();

  if (loading || !user) {
    return <div className="size-7 border border-rule bg-paper-2" aria-hidden />;
  }

  const label =
    user.firstName || user.lastName
      ? [user.firstName, user.lastName].filter(Boolean).join(" ")
      : user.email;
  const orgLabel = me?.organization.linked
    ? me.organization.name
    : me?.organization.workos_org_id
      ? "org not linked"
      : null;

  return (
    <div className="flex items-center gap-3">
      <div className="text-right leading-tight hidden sm:block">
        <div className="font-mono text-[11px]">{label}</div>
        {orgLabel && <div className="label-eyebrow">{orgLabel}</div>}
      </div>
      <button
        type="button"
        onClick={() => void signOut({ returnTo: "/" })}
        title="Sign out"
        className="flex size-7 items-center justify-center border border-rule bg-paper-2 hover:bg-paper text-muted-foreground hover:text-foreground"
      >
        <LogOut className="size-3.5" strokeWidth={1.5} />
      </button>
    </div>
  );
}

const NAV = [
  { to: "/app/dashboard", label: "Dashboard", icon: LayoutDashboard, group: "Observe" },
  { to: "/app/traces", label: "Traces", icon: ListTree, group: "Observe" },
  { to: "/app/insights", label: "Insights", icon: ScanSearch, group: "Observe" },
  { to: "/app/rag-analytics", label: "RAG Analytics", icon: Search, group: "Observe" },
  { to: "/app/prompts", label: "Prompts", icon: FileCode2, group: "Improve" },
  { to: "/app/evaluations", label: "Evaluations", icon: ClipboardCheck, group: "Improve" },
  { to: "/app/datasets", label: "Datasets", icon: Database, group: "Improve" },
  { to: "/app/experiments", label: "Experiments", icon: FlaskConical, group: "Improve" },
  { to: "/app/getting-started", label: "Getting started", icon: Rocket, group: "Setup" },
  { to: "/app/settings/api-keys", label: "API keys", icon: KeyRound, group: "Setup" },
  { to: "/app/settings", label: "Project settings", icon: Settings, group: "Setup" },
] as const;

function AppShellLayout() {
  const pathname = useRouterState({ select: (r) => r.location.pathname });
  const groups = ["Observe", "Improve", "Setup"] as const;
  return (
    <div className="min-h-screen bg-paper text-foreground">
      <div className="flex">
        <aside className="hidden md:flex w-[240px] shrink-0 flex-col border-r border-rule bg-paper sticky top-0 h-screen">
          <div className="flex items-center justify-between border-b border-rule px-4 h-14">
            <Link to="/" className="flex items-center gap-2">
              <HeliosMark />
              <span className="font-serif text-lg tracking-tight">Helios</span>
            </Link>
            <span className="label-eyebrow">v1.0</span>
          </div>
          <ProjectSelector />
          <nav className="flex-1 overflow-y-auto py-2">
            {groups.map((g) => (
              <div key={g} className="px-2 py-3">
                <div className="label-eyebrow px-2 mb-2">{g}</div>
                <ul className="space-y-px">
                  {NAV.filter((n) => n.group === g).map((n) => {
                    const active =
                      n.to === "/app/settings" ? pathname === n.to : pathname.startsWith(n.to);
                    const Icon = n.icon;
                    return (
                      <li key={n.to}>
                        <Link
                          to={n.to}
                          className={cn(
                            "flex items-center gap-2.5 px-2 py-1.5 text-[13px] border border-transparent",
                            active
                              ? "bg-paper-2 border-rule text-foreground"
                              : "text-ink-soft hover:bg-paper-2 hover:text-foreground",
                          )}
                        >
                          <Icon className="size-3.5" strokeWidth={1.5} />
                          {n.label}
                        </Link>
                      </li>
                    );
                  })}
                </ul>
              </div>
            ))}
          </nav>
          <div className="border-t border-rule p-3">
            <div className="border border-rule p-3 bg-paper-2/60">
              <div className="label-eyebrow">SDK</div>
              <pre className="mt-2 font-mono text-[11px] leading-relaxed text-foreground">{`from helios_sdk import Helios
Helios.configure(...)`}</pre>
              <Link
                to="/app/getting-started"
                className="mt-2 inline-block text-[11px] underline underline-offset-2 text-muted-foreground hover:text-foreground"
              >
                Setup guide
              </Link>
            </div>
          </div>
        </aside>
        <div className="flex-1 min-w-0">
          <header className="sticky top-0 z-20 flex h-14 items-center justify-between border-b border-rule bg-paper/90 backdrop-blur px-6">
            <div className="flex items-center gap-3 flex-1 max-w-xl">
              <Search className="size-4 text-muted-foreground" strokeWidth={1.5} />
              <input
                placeholder="Search traces, prompts, evals…"
                className="flex-1 bg-transparent outline-none font-mono text-[13px] placeholder:text-muted-foreground"
              />
              <div className="flex items-center gap-1 label-eyebrow border border-rule px-1.5 py-0.5">
                <Command className="size-3" /> K
              </div>
            </div>
            <div className="flex items-center gap-4">
              <StatusBadge tone="success">ingest 1.2k/s</StatusBadge>
              <Bell className="size-4 text-muted-foreground" strokeWidth={1.5} />
              <UserIdentity />
            </div>
          </header>
          <main className="px-6 py-8">
            <Outlet />
          </main>
        </div>
      </div>
    </div>
  );
}

export function AppShell() {
  return (
    <ProjectSelectionProvider>
      <AppShellLayout />
    </ProjectSelectionProvider>
  );
}

export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
}: {
  eyebrow: string;
  title: string;
  description?: string;
  actions?: React.ReactNode;
}) {
  return (
    <div className="flex items-end justify-between gap-8 border-b border-rule pb-6 mb-8 flex-wrap">
      <div>
        <div className="label-eyebrow">{eyebrow}</div>
        <h1 className="mt-2 font-serif text-4xl tracking-tight">{title}</h1>
        {description && (
          <p className="mt-2 text-sm text-muted-foreground max-w-2xl">{description}</p>
        )}
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </div>
  );
}
