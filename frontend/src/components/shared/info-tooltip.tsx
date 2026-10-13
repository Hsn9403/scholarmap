import { Info } from "lucide-react";

interface InfoTooltipProps {
  children: React.ReactNode;
  /** Which edge the bubble hangs from — "right" keeps it inside narrow cards. */
  align?: "center" | "right";
  widthClass?: string;
}

/** Small "?" affordance revealing an explanation on hover. */
export function InfoTooltip({
  children,
  align = "center",
  widthClass = "w-64",
}: InfoTooltipProps) {
  const isRight = align === "right";

  return (
    <div className="relative group flex-shrink-0">
      <Info className="w-4 h-4 text-gray-400 cursor-help" />
      <div
        className={`absolute top-full mt-2 ${widthClass} px-3 py-2 rounded-lg text-xs text-white opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none z-10 ${
          isRight ? "right-0" : "left-1/2 -translate-x-1/2"
        }`}
        style={{ background: "#1E293B" }}
      >
        <div
          className={`absolute bottom-full border-4 border-transparent ${
            isRight ? "right-2" : "left-1/2 -translate-x-1/2"
          }`}
          style={{ borderBottomColor: "#1E293B" }}
        />
        {children}
      </div>
    </div>
  );
}
