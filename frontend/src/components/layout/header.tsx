"use client";

import Link from "next/link";
import { useI18n, type Lang } from "@/lib/i18n";
import { Home, Network } from "lucide-react";

export function Header() {
  const { t, lang, setLang } = useI18n();

  return (
    <header
      className="flex-shrink-0"
      style={{
        background: "linear-gradient(135deg, #0066CC 0%, #0052A3 100%)",
        boxShadow: "0 4px 20px rgba(0,102,204,0.15)",
      }}
    >
      <div className="px-4 sm:px-6 lg:px-8 max-w-[1600px] mx-auto">
        <div className="flex items-center h-20 gap-8">
          {/* Logo */}
          <Link
            href="/"
            className="flex-shrink-0 flex items-center gap-2 text-white hover:opacity-90 transition-opacity"
          >
            <Network className="w-8 h-8" strokeWidth={2} />
            <span className="text-2xl font-bold tracking-tight">Scholarmap</span>
          </Link>

          {/* Nav */}
          <div className="flex-1 flex items-center justify-between pl-2">
            <nav className="flex items-center gap-2">
              <NavLink href="/" icon={<Home className="w-4 h-4" />} label={t("header_home")} />
            </nav>

            <div
              className="flex items-center rounded-lg overflow-hidden"
              style={{ border: "1px solid rgba(255,255,255,0.3)" }}
            >
              <LangButton code="fr" current={lang} onSelect={setLang} />
              <div className="w-px bg-white/30 h-4" />
              <LangButton code="en" current={lang} onSelect={setLang} />
            </div>
          </div>
        </div>
      </div>
    </header>
  );
}

/** FR / EN toggle. Flask holds the language in the session, so this round-trips. */
function LangButton({
  code,
  current,
  onSelect,
}: {
  code: Lang;
  current: Lang;
  onSelect: (lang: Lang) => void;
}) {
  const active = code === current;
  return (
    <button
      type="button"
      onClick={() => !active && onSelect(code)}
      className="px-2.5 py-1.5 text-xs font-bold transition-colors cursor-pointer border-none"
      style={
        active
          ? { background: "rgba(255,255,255,0.95)", color: "#0066CC" }
          : { background: "transparent", color: "rgba(255,255,255,0.7)" }
      }
    >
      {code.toUpperCase()}
    </button>
  );
}

function NavLink({
  href,
  icon,
  label,
}: {
  href: string;
  icon: React.ReactNode;
  label: string;
}) {
  return (
    <Link
      href={href}
      className="px-5 py-2.5 text-sm font-semibold rounded-lg shadow-md hover:shadow-lg hover:scale-105 transition-all duration-200 flex items-center gap-2 whitespace-nowrap"
      style={{ background: "rgba(255,255,255,0.95)", color: "#0066CC" }}
    >
      {icon}
      {label}
    </Link>
  );
}
