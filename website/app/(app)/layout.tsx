"use client";

import { useEffect, useState, type ReactNode } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";
import { useBusiness } from "@/lib/business";
import { useLang } from "@/lib/i18n";
import { applyTheme, currentTheme } from "@/lib/theme";
import { Icon } from "@/components/Icon";

type NavItem = { key: string; href: string; icon: string; ready?: boolean; children?: NavItem[] };
type NavGroup = { group: string; items: NavItem[] };

// Mirrors the desktop sidebar exactly (timber/ui/main_window.py): same sections,
// labels, icons, order, and sub-items. Items whose web page isn't built yet are
// left without `ready` so they render as "soon".
const NAV: NavGroup[] = [
  {
    group: "nav_dashboard",
    items: [
      { key: "dashboard", href: "/dashboard", icon: "dashboard", ready: true },
      { key: "reports", href: "/reports", icon: "pie-chart", ready: true },
    ],
  },
  {
    group: "nav_entry",
    items: [
      { key: "trade", href: "/buy-sell", icon: "cart", ready: true },
      { key: "trades", href: "/trades", icon: "receipt", ready: true },
      { key: "payment", href: "/payments", icon: "wallet", ready: true },
      { key: "search", href: "/search", icon: "search", ready: true },
    ],
  },
  {
    group: "nav_money",
    items: [
      { key: "bank_accounts", href: "/bank", icon: "landmark", ready: true, children: [
        { key: "bank_book", href: "/bank-book", icon: "book-open", ready: true },
      ] },
      { key: "transfers", href: "/transfers", icon: "transfer", ready: true },
      { key: "expenses", href: "/expenses", icon: "trending-down", ready: true },
      { key: "cheques", href: "/cheques", icon: "file-check", ready: true },
      { key: "loans", href: "/loans", icon: "hand-coins", ready: true },
    ],
  },
  {
    group: "nav_ledgers",
    items: [
      { key: "financial_position", href: "/position", icon: "pie-chart", ready: true },
      { key: "party_ledger", href: "/ledger", icon: "book-user", ready: true },
      { key: "factory_ledger", href: "/factory-ledger", icon: "factory", ready: true, children: [
        { key: "factory_sub_ledger", href: "/factory-sub-ledger", icon: "book-text", ready: true },
      ] },
      { key: "trade_ledger", href: "/trade-ledger", icon: "book-text", ready: true },
      { key: "profit_ledger", href: "/profit", icon: "trending-up", ready: true },
      { key: "overdue_report", href: "/overdue", icon: "alarm-clock", ready: true },
      { key: "aging", href: "/aging", icon: "calendar-clock", ready: true },
    ],
  },
  {
    group: "nav_manage",
    items: [
      { key: "master_data", href: "/master", icon: "database", ready: true },
    ],
  },
  {
    group: "nav_settings",
    items: [
      { key: "settings", href: "/settings", icon: "settings", ready: true },
    ],
  },
];

const ALL_ITEMS = NAV.flatMap((g) => g.items.flatMap((it) => [it, ...(it.children ?? [])]));

// The desktop shows the page-bar export buttons ONLY on single-report screens
// (main_window: _exp_pdf.setVisible(single)); hidden on Master Data, Dashboard, etc.
const EXPORT_ROUTES = new Set<string>([]);

export default function AppLayout({ children }: { children: ReactNode }) {
  const { user, loading, logout } = useAuth();
  const { t } = useLang();
  const { name: businessName } = useBusiness();
  const router = useRouter();
  const pathname = usePathname();
  const [navOpen, setNavOpen] = useState(true);   // sidebar: open on desktop, drawer on mobile
  const [menuOpen, setMenuOpen] = useState(false);
  const [closed, setClosed] = useState<Set<string>>(new Set());
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  function toggleExpand(k: string) {
    setExpanded((s) => {
      const n = new Set(s);
      n.has(k) ? n.delete(k) : n.add(k);
      return n;
    });
  }

  // Apply the saved theme on load (defaults to light, like the desktop).
  useEffect(() => { applyTheme(currentTheme()); }, []);
  useEffect(() => {
    if (!loading && !user) router.replace("/login");
  }, [loading, user, router]);
  // Start closed on phones/tablets, open on desktop — the drawer takes over below 880px.
  useEffect(() => { setNavOpen(window.innerWidth > 880); }, []);
  // Close the drawer after navigating on small screens.
  function closeOnMobile() { if (window.innerWidth <= 880) setNavOpen(false); }

  function toggleGroup(g: string) {
    setClosed((s) => {
      const n = new Set(s);
      n.has(g) ? n.delete(g) : n.add(g);
      return n;
    });
  }

  if (loading || !user) return <div className="center muted">Loading…</div>;

  const active = ALL_ITEMS.find((it) => it.href === pathname);
  // Routes reached from within a page (not the sidebar) still need a page-bar title.
  const EXTRA_TITLES: Record<string, string> = { "/audit": "Audit Log" };
  const pageTitle = active ? t(active.key) : (EXTRA_TITLES[pathname] ?? "");
  // The desktop chip shows the BUSINESS initials (brand mark), not the user's,
  // and the dropdown reads "Abdul Sattar Woods | {user}" + the role label.
  const APP_NAME = businessName;
  const brandMark =
    APP_NAME.split(" ").filter(Boolean).slice(0, 3).map((w) => w[0]).join("").toUpperCase() || "A";
  const roleLabel =
    ({ admin: "Administrator", manager: "Manager", viewer: "Viewer" } as Record<string, string>)[
      (user.role || "").toLowerCase()
    ] || user.role || "";
  const chipName = `${APP_NAME} | ${user.name || user.username}`;

  // Renders a nav item; parents with children get a caret that expands the
  // sub-items (collapsed by default, like the desktop's Bank Accounts / Factory
  // Ledger). A sub-item renders indented.
  function renderNavItem(it: NavItem, sub: boolean) {
    const isParent = !!it.children?.length;
    const childActive = it.children?.some((c) => c.href === pathname) ?? false;
    const open = expanded.has(it.key) || childActive;
    const cls =
      "nav-item" + (sub ? " sub" : "") +
      (pathname === it.href ? " active" : "") + (it.ready ? "" : " disabled");
    const inner = (
      <>
        <span className="nav-icon"><Icon name={it.icon} size={19} /></span>
        <span className="nav-label">{t(it.key)}</span>
        {!it.ready && <span className="soon">{t("soon")}</span>}
        {isParent && (
          <span
            className={"nav-caret" + (open ? " open" : "")}
            onClick={(e) => { e.preventDefault(); e.stopPropagation(); toggleExpand(it.key); }}
          >
            <Icon name="chevron-right" size={14} />
          </span>
        )}
      </>
    );
    return (
      <div key={it.key}>
        {it.ready ? (
          <Link href={it.href} className={cls} onClick={closeOnMobile}>{inner}</Link>
        ) : (
          <span className={cls}>{inner}</span>
        )}
        {isParent && open && it.children!.map((c) => renderNavItem(c, true))}
      </div>
    );
  }

  return (
    <div className={"app" + (navOpen ? " nav-open" : "")}>
      <div className="topbar">
        {/* dark brand block: menu toggle + app name */}
        <div className="brand-block">
          <button className="menu-toggle" onClick={() => setNavOpen((o) => !o)} aria-label="Menu">
            <Icon name="menu" size={20} />
          </button>
          <span className="brand">{APP_NAME}</span>
        </div>

        {/* purple gradient header bar: bell + divider + avatar chip (no chevron) */}
        <header className="header-main">
          <div className="grow" />
          <button className="hicon" title="Notifications" aria-label="Notifications">
            <Icon name="bell" size={19} />
          </button>
          <span className="hdivider" />
          <button className="avatar-btn" onClick={() => setMenuOpen((o) => !o)} aria-label="Account">
            <span className="avatar">{brandMark}</span>
          </button>
        </header>
      </div>

      {menuOpen && (
        <>
          <div className="menu-backdrop" onClick={() => setMenuOpen(false)} />
          <div className="header-menu">
            {/* header row: brand-mark avatar + "Abdul Sattar Woods | {user}" + role */}
            <div className="menu-head">
              <span className="avatar menu-avatar">{brandMark}</span>
              <div className="who">
                <div className="n">{chipName}</div>
                <div className="r">{roleLabel}</div>
              </div>
            </div>
            <div className="menu-sep" />
            <Link href="/settings" onClick={() => setMenuOpen(false)}>
              <Icon name="user" size={16} className="mi-account" />
              {t("account")}
            </Link>
            <div className="menu-sep" />
            <button className="mi-logout" onClick={() => { logout(); router.replace("/login"); }}>
              <Icon name="logout" size={16} />
              {t("logout")}
            </button>
          </div>
        </>
      )}

      <div className="body">
        {/* dims the page behind the slide-in sidebar on phones/tablets */}
        {navOpen && <div className="nav-backdrop" onClick={() => setNavOpen(false)} />}
        {/* dark sidebar with collapsible sections */}
        <aside className="sidebar">
          <nav className="nav">
            {NAV.map((g) => (
              <div className={"nav-group" + (closed.has(g.group) ? " closed" : "")} key={g.group}>
                <button className="nav-group-label" onClick={() => toggleGroup(g.group)}>
                  {t(g.group)}
                  <span className="chev"><Icon name="chevron-down" size={14} /></span>
                </button>
                {g.items.map((it) => renderNavItem(it, false))}
              </div>
            ))}
          </nav>
        </aside>

        {/* window-coloured area: page bar (title + export) + floating panel */}
        <div className="content-wrap">
          <div className="page-bar">
            <span className="title">{pageTitle}</span>
            <div className="grow" />
            {EXPORT_ROUTES.has(pathname) && (
              <>
                <button className="export-btn" onClick={() => alert("Export will be enabled with the Reports screen.")}>
                  <Icon name="download" size={15} /> {t("export_pdf")}
                </button>
                <button className="export-btn" onClick={() => alert("Export will be enabled with the Reports screen.")}>
                  <Icon name="download" size={15} /> {t("export_excel")}
                </button>
              </>
            )}
          </div>
          <div className="content-panel">{children}</div>
        </div>
      </div>
    </div>
  );
}
