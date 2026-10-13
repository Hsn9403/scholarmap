"use client";

import { useEffect, useRef, useState } from "react";
import { useT } from "@/lib/i18n";
import styles from "./loading.module.css";

const TIP_INTERVAL = 5000;
const START_DELAY = 3000;
const FADE_MS = 500;

/** Display order — the two most useful tips come first. */
const QUEUE = [0, 5, 1, 2, 3, 4];

interface TipsCarouselProps {
  /** Called once every tip has had its turn, so the caller can move on. */
  onAllShown?: () => void;
}

/**
 * Rotating usage tips shown to new users while the pipeline runs.
 * Each tip pairs a short animated mock of the UI with one sentence.
 */
export function TipsCarousel({ onAllShown }: TipsCarouselProps) {
  const t = useT();
  const [step, setStep] = useState(-1);
  const [hiding, setHiding] = useState(false);

  const onAllShownRef = useRef(onAllShown);
  useEffect(() => {
    onAllShownRef.current = onAllShown;
  });

  useEffect(() => {
    const start = setTimeout(() => setStep(0), START_DELAY);
    return () => clearTimeout(start);
  }, []);

  useEffect(() => {
    if (step < 0) return;

    const hide = setTimeout(() => setHiding(true), TIP_INTERVAL - FADE_MS);
    const next = setTimeout(() => {
      if (step + 1 < QUEUE.length) {
        setHiding(false);
        setStep(step + 1);
      } else {
        onAllShownRef.current?.();
      }
    }, TIP_INTERVAL);

    return () => {
      clearTimeout(hide);
      clearTimeout(next);
    };
  }, [step]);

  const tip = step >= 0 ? TIPS[QUEUE[step]] : null;

  return (
    <div className="max-w-[600px] mx-auto w-full px-4 mb-4 min-h-[72px]">
      {tip && (
        // key remounts the card each step, so the CSS entrance animation replays
        <div
          key={step}
          className={`${styles.tipCard} ${hiding ? styles.tipCardHiding : ""}`}
        >
          <div className={styles.tipVisual} style={tip.visualStyle}>
            {tip.visual}
          </div>
          <div className={styles.tipText}>{t(tip.textKey)}</div>
        </div>
      )}
    </div>
  );
}

/** The pointing hand that taps each mocked control. */
function ClickHand() {
  return (
    <svg className={styles.clickHand} viewBox="0 0 90 69" fill="#1E293B" stroke="none">
      <g transform="translate(0,69) scale(0.1,-0.1)">
        <path d="M400 471 c-5 -11 -10 -52 -10 -91 l0 -70 -24 15 c-19 13 -29 14 -45 5 -27 -14 -27 -44 0 -78 24 -33 63 -87 86 -124 15 -23 25 -28 58 -28 22 0 46 4 54 9 9 6 21 5 33 -2 26 -17 52 2 59 44 4 19 16 56 28 82 33 70 23 118 -28 140 -21 10 -47 16 -57 16 -60 -6 -74 0 -74 32 0 43 -17 69 -45 69 -14 0 -29 -8 -35 -19z m54 -7 c3 -9 6 -47 6 -85 0 -55 3 -69 15 -69 10 0 15 10 15 30 0 19 5 30 14 30 7 0 16 -13 20 -30 7 -38 24 -39 28 -3 4 38 38 45 38 9 0 -14 5 -26 10 -26 6 0 10 7 10 16 0 9 6 14 13 12 22 -8 19 -65 -7 -127 -14 -33 -26 -70 -26 -81 0 -25 -18 -26 -35 -3 -13 17 -14 17 -32 0 -19 -17 -83 -24 -83 -9 0 4 -18 30 -40 57 -76 96 -82 106 -76 120 8 23 32 18 50 -10 9 -14 21 -23 26 -20 6 4 10 46 10 94 0 54 4 91 12 99 16 16 25 15 32 -4z" />
      </g>
    </svg>
  );
}

/** A mocked filter pill being tapped. */
function FilterPill({
  label,
  count,
  dotColor,
  caret,
  width,
}: {
  label: string;
  count: string;
  dotColor: string;
  caret?: boolean;
  width: number;
}) {
  return (
    <div className={styles.clickDemo} style={{ width, height: 36 }}>
      <div className={styles.clickPill}>
        <span className={styles.clickPillDot} style={{ background: dotColor }} />
        <span style={{ fontWeight: 600 }}>{label}</span>
        <span className={styles.clickPillCount}>{count}</span>
        {caret && <span className={styles.clickPillCaret}>▼</span>}
      </div>
      <ClickHand />
    </div>
  );
}

interface Tip {
  /** Translation key — the copy lives in webapp/translations. */
  textKey: string;
  visual: React.ReactNode;
  visualStyle?: React.CSSProperties;
}

const TIPS: Tip[] = [
  // 0 — corporate filter toggle
  {
    textKey: "loading_tip_corporate",
    visualStyle: { width: 64, height: 44 },
    visual: (
      <div className={styles.toggleTrack}>
        <div className={styles.toggleThumb} />
      </div>
    ),
  },
  // 1 — click a co-author node
  {
    textKey: "loading_tip_click_node",
    visualStyle: { width: 52, height: 36 },
    visual: (
      <div className={styles.clickDemo} style={{ width: 52, height: 36 }}>
        <div className={styles.clickNode} />
        <div className={styles.clickRipple} />
        <ClickHand />
      </div>
    ),
  },
  // 2 — co-author filter
  {
    textKey: "loading_tip_filters",
    visualStyle: { width: 120, height: 36 },
    visual: <FilterPill label="Co-auteurs" count="49" dotColor="#2D7FF9" width={120} />,
  },
  // 3 — publications hidden by default
  {
    textKey: "loading_tip_publications",
    visualStyle: { width: 130, height: 36 },
    visual: (
      <FilterPill label="Publications" count="14" dotColor="#22C55E" caret width={130} />
    ),
  },
  // 4 — CONNEXION panel
  {
    textKey: "loading_tip_connexion",
    visualStyle: {
      width: 160,
      height: 92,
      overflow: "hidden",
      borderRadius: 8,
      boxShadow: "0 2px 10px rgba(0,0,0,0.12)",
    },
    visual: (
      <div className={styles.connexionMini}>
        <div className={styles.connexionMiniHeader}>
          <span className={styles.connexionMiniLabel}>CONNEXION</span>
          <span className={styles.connexionMiniClose}>×</span>
        </div>
        <div className={styles.connexionMiniBody}>
          <div className={styles.connexionMiniCorp}>Medtronic France S.A.S</div>
          <div className={styles.connexionMiniTag}>LIEN DIRECT :</div>
          <div className={styles.connexionMiniRow}>
            → <span className={styles.blurred}>Édgar Duval</span>
          </div>
          <div className={styles.connexionMiniTag} style={{ marginTop: 3 }}>
            POURQUOI ?
          </div>
          <div className={styles.connexionMiniRow}>
            → 4 paiement(s) - <span className={styles.blurred}>182 442 €</span>
          </div>
          <div className={styles.connexionMiniRow} style={{ color: "#94A3B8" }}>
            Autres prestations ↗
          </div>
          <div className={styles.connexionMiniTag} style={{ marginTop: 4 }}>
            LIEN IDENTIFIÉ :
          </div>
          <div className={styles.connexionMiniRow}>
            → <span className={styles.blurred}>Dominique Midy</span>
          </div>
          <div className={styles.connexionMiniTag} style={{ marginTop: 3 }}>
            POURQUOI ?
          </div>
          <div className={styles.connexionMiniRow}>
            → Co-auteur avec <span className={styles.blurred}>Édgar D.</span>
          </div>
          <div className={styles.connexionMiniRow}>
            → 1 paiement(s) - <span className={styles.blurred}>27 280 €</span>
          </div>
        </div>
      </div>
    ),
  },
];
