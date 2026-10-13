"use client";

import { useState } from "react";
import { ExternalLink } from "lucide-react";
import { shortOpenAlexId } from "@/lib/analyze";
import type { OACandidate } from "@/types";

const SELECTED_BORDER = "#7C3AED";
const SELECTED_BG = "#F5F3FF";
const IDLE_BORDER = "#E2E8F0";
const IDLE_BG = "#FAFAFA";

interface OACandidateCardProps {
  candidate: OACandidate;
  selected: boolean;
  onSelect: () => void;
}

/** One OpenAlex profile, selectable like a radio. Used by every disambiguation screen. */
export function OACandidateCard({
  candidate: c,
  selected,
  onSelect,
}: OACandidateCardProps) {
  const [showAllAffils, setShowAllAffils] = useState(false);

  const affils = c.all_affiliations;
  const hasExtra = affils.length > 3;
  const shown = showAllAffils ? affils : affils.slice(0, 3);

  return (
    <label className="block cursor-pointer">
      <input
        type="radio"
        name="openalex_id"
        value={c.openalex_id}
        checked={selected}
        onChange={onSelect}
        className="sr-only"
      />
      <div
        className="p-5 rounded-xl border-2 transition-all duration-200"
        style={{
          borderColor: selected ? SELECTED_BORDER : IDLE_BORDER,
          background: selected ? SELECTED_BG : IDLE_BG,
        }}
        onMouseOver={(e) => {
          e.currentTarget.style.borderColor = SELECTED_BORDER;
          e.currentTarget.style.background = SELECTED_BG;
        }}
        onMouseOut={(e) => {
          e.currentTarget.style.borderColor = selected ? SELECTED_BORDER : IDLE_BORDER;
          e.currentTarget.style.background = selected ? SELECTED_BG : IDLE_BG;
        }}
      >
        <div className="flex items-start space-x-4">
          {/* Radio indicator */}
          <div
            className="mt-1 w-5 h-5 rounded-full border-2 flex-shrink-0 flex items-center justify-center"
            style={{ borderColor: "#C4B5FD" }}
          >
            {selected && (
              <div className="w-2.5 h-2.5 rounded-full" style={{ background: SELECTED_BORDER }} />
            )}
          </div>

          <div className="flex-1 min-w-0">
            <p className="font-semibold text-base" style={{ color: "#1E293B" }}>
              {c.name}
            </p>

            {affils.length > 0 && (
              <p className="text-sm text-gray-500 mt-1">
                {shown.join(" · ")}
                {hasExtra && (
                  <button
                    type="button"
                    className="ml-1 text-xs font-medium hover:underline"
                    style={{ color: SELECTED_BORDER }}
                    onClick={(e) => {
                      e.preventDefault();
                      e.stopPropagation();
                      setShowAllAffils((v) => !v);
                    }}
                  >
                    {showAllAffils ? "voir moins" : "voir plus"}
                  </button>
                )}
              </p>
            )}

            <div className="flex items-center gap-4 mt-2">
              <span className="text-xs text-gray-400">
                {c.works_count} works · {c.cited_by_count.toLocaleString("fr-FR")} citations
              </span>
              <a
                href={`https://openalex.org/${shortOpenAlexId(c.openalex_id)}`}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1 text-xs hover:underline"
                style={{ color: SELECTED_BORDER }}
                onClick={(e) => e.stopPropagation()}
              >
                Voir le profil OpenAlex
                <ExternalLink className="w-3 h-3" />
              </a>
            </div>
          </div>
        </div>
      </div>
    </label>
  );
}
