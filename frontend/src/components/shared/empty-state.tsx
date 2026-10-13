"use client";

import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import { useT } from "@/lib/i18n";

/** Centred spinner used while a screen's data loads. */
export function CenteredSpinner() {
  return (
    <div className="flex-1 flex items-center justify-center py-24">
      <div className="w-8 h-8 border-2 border-[#0066CC] border-t-transparent rounded-full animate-spin" />
    </div>
  );
}

/** Dead end: explain what went wrong and offer the way back home. */
export function EmptyState({ message }: { message: string }) {
  const t = useT();

  return (
    <div className="max-w-2xl mx-auto w-full px-4 py-16 text-center">
      <p className="text-base mb-6" style={{ color: "#1E293B" }}>
        {message}
      </p>
      <Link
        href="/"
        className="inline-flex items-center gap-1 text-sm font-medium hover:underline"
        style={{ color: "#0066CC" }}
      >
        <ArrowLeft className="w-4 h-4" />
        {t("back_to_home")}
      </Link>
    </div>
  );
}
