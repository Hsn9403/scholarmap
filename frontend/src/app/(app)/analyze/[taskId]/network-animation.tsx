"use client";

import { useT } from "@/lib/i18n";
import styles from "./loading.module.css";

const COLORS = {
  person: "#2D7FF9",
  corporate: "#F39C12",
  institution: "#9B59B6",
  patent: "#34495E",
  publication: "#27AE60",
} as const;

type NodeColor = keyof typeof COLORS;

const CENTER = { x: 600, y: 200 };

/** Six co-authors around the researcher. */
const RING1 = [
  { x: 710, y: 200 },
  { x: 655, y: 295 },
  { x: 545, y: 295 },
  { x: 490, y: 200 },
  { x: 545, y: 105 },
  { x: 655, y: 105 },
];

/** Second ring — mixed entity types discovered through the co-authors. */
const RING2: { x: number; y: number; r: number; color: NodeColor; from: number }[] = [
  { x: 800, y: 200, r: 10, color: "corporate", from: 0 },
  { x: 762, y: 103, r: 9, color: "institution", from: 0 },
  { x: 762, y: 337, r: 9, color: "patent", from: 1 },
  { x: 655, y: 375, r: 9, color: "publication", from: 1 },
  { x: 545, y: 375, r: 9, color: "corporate", from: 2 },
  { x: 438, y: 337, r: 9, color: "institution", from: 2 },
  { x: 400, y: 200, r: 10, color: "patent", from: 3 },
  { x: 438, y: 103, r: 9, color: "publication", from: 3 },
  { x: 545, y: 25, r: 9, color: "corporate", from: 4 },
  { x: 655, y: 25, r: 9, color: "institution", from: 5 },
];

/** Outer network — the far reach of the graph, pulsing as it is discovered. */
const OUTER: { x: number; y: number; r: number; color: NodeColor; from: number }[] = [
  { x: 960, y: 160, r: 9, color: "corporate", from: 0 },
  { x: 960, y: 250, r: 8, color: "publication", from: 0 },
  { x: 920, y: 340, r: 9, color: "institution", from: 2 },
  { x: 280, y: 340, r: 8, color: "patent", from: 5 },
  { x: 240, y: 160, r: 9, color: "corporate", from: 6 },
  { x: 240, y: 250, r: 8, color: "publication", from: 6 },
  { x: 280, y: 60, r: 8, color: "institution", from: 7 },
  { x: 920, y: 60, r: 9, color: "corporate", from: 1 },
  { x: 400, y: 20, r: 8, color: "patent", from: 8 },
  { x: 800, y: 20, r: 9, color: "publication", from: 9 },
];

const LEGEND: { color: NodeColor; key: string }[] = [
  { color: "person", key: "loading_legend_person" },
  { color: "corporate", key: "loading_legend_corporate" },
  { color: "institution", key: "loading_legend_institution" },
  { color: "patent", key: "loading_legend_patent" },
  { color: "publication", key: "loading_legend_publication" },
];

/** Same hue as the node it lands on, faded down to an edge stroke. */
const EDGE_STROKE: Record<NodeColor, string> = {
  person: "rgba(45,127,249,0.18)",
  corporate: "rgba(243,156,18,0.2)",
  institution: "rgba(155,89,182,0.2)",
  patent: "rgba(52,73,94,0.2)",
  publication: "rgba(39,174,96,0.2)",
};

/**
 * Decorative graph that draws itself outward from the researcher while the
 * pipeline runs. Purely CSS-timed — it carries no pipeline state.
 */
export function NetworkAnimation() {
  const t = useT();

  return (
    <>
      <svg
        viewBox="0 0 1200 400"
        xmlns="http://www.w3.org/2000/svg"
        preserveAspectRatio="xMidYMid meet"
        style={{ width: "100%", display: "block", flex: 1, minHeight: 260 }}
        aria-hidden
      >
        <defs>
          <filter id="glow" x="-60%" y="-60%" width="220%" height="220%">
            <feGaussianBlur stdDeviation="5" result="b" />
            <feMerge>
              <feMergeNode in="b" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>

        {/* Center → ring 1 */}
        {RING1.map((n, i) => (
          <line
            key={`e1-${i}`}
            x1={CENTER.x}
            y1={CENTER.y}
            x2={n.x}
            y2={n.y}
            stroke="rgba(45,127,249,0.25)"
            strokeWidth={1.5}
            className={styles.edge}
            style={{ animationDelay: `${0.55 + i * 0.15}s` }}
          />
        ))}

        {/* Ring 1 → ring 2 */}
        {RING2.map((n, i) => (
          <line
            key={`e2-${i}`}
            x1={RING1[n.from].x}
            y1={RING1[n.from].y}
            x2={n.x}
            y2={n.y}
            stroke="rgba(45,127,249,0.18)"
            strokeWidth={1.5}
            className={styles.edge}
            style={{ animationDelay: `${1.75 + i * 0.1}s` }}
          />
        ))}

        {/* Ring 2 → outer */}
        {OUTER.map((n, i) => (
          <line
            key={`e3-${i}`}
            x1={RING2[n.from].x}
            y1={RING2[n.from].y}
            x2={n.x}
            y2={n.y}
            stroke={EDGE_STROKE[n.color]}
            strokeWidth={1.5}
            className={styles.edge}
            style={{ animationDelay: `${3.2 + i * 0.1}s` }}
          />
        ))}

        {/* Expanding ring behind the researcher */}
        <circle
          cx={CENTER.x}
          cy={CENTER.y}
          r={24}
          fill="none"
          stroke="rgba(45,127,249,0.3)"
          strokeWidth={1.5}
          className={styles.ring}
        />

        {/* The researcher */}
        <circle
          cx={CENTER.x}
          cy={CENTER.y}
          r={22}
          fill={COLORS.person}
          filter="url(#glow)"
          className={styles.centerNode}
        />

        {RING1.map((n, i) => (
          <circle
            key={`n1-${i}`}
            cx={n.x}
            cy={n.y}
            r={13}
            fill={COLORS.person}
            className={styles.node}
            style={{ animationDelay: `${0.4 + i * 0.15}s` }}
          />
        ))}

        {RING2.map((n, i) => (
          <circle
            key={`n2-${i}`}
            cx={n.x}
            cy={n.y}
            r={n.r}
            fill={COLORS[n.color]}
            className={styles.node}
            style={{ animationDelay: `${1.65 + i * 0.1}s` }}
          />
        ))}

        {OUTER.map((n, i) => (
          <circle
            key={`n3-${i}`}
            cx={n.x}
            cy={n.y}
            r={n.r}
            fill={COLORS[n.color]}
            className={styles.discovered}
            style={{ animationDelay: `${3.25 + i * 0.1}s, ${3.6 + i * 0.1}s` }}
          />
        ))}
      </svg>

      <div className={styles.legend}>
        {LEGEND.map(({ color, key }) => (
          <span key={key} className={styles.legendItem}>
            <span className={styles.legendDot} style={{ background: COLORS[color] }} />
            {t(key)}
          </span>
        ))}
      </div>
    </>
  );
}
