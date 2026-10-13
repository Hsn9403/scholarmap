"use client";

import { useEffect, useRef, useState } from "react";
import { fetcher } from "@/lib/fetcher";
import { TaskStatusSchema, type TaskStatus } from "@/types";
import { useT } from "@/lib/i18n";

const STALL_TIMEOUT_MS = 120_000;
const PHASE1_TIMEOUT_MS = 30_000;
const MAX_FETCH_FAILS = 10;

/** Translation keys for the three ways a run can die client-side. */
const ERROR_KEYS = {
  openalex: "loading_error_openalex",
  stalled: "loading_error_stalled",
  connection: "loading_error_connection",
} as const;

interface UsePollingOptions {
  taskId: string | null;
  intervalMs?: number;
  onComplete?: () => void;
  /** Fired once for any terminal failure: server error, stall, or lost connection. */
  onError?: (message: string) => void;
}

export interface PollingState {
  /** Monotonic — never goes backwards, so the progress bar only ever fills. */
  progress: number;
  message: string;
  isComplete: boolean;
  error: string | null;
}

/**
 * Poll /api/status/<taskId> until the pipeline completes or stalls.
 *
 * A pipeline can die silently, so beyond the server-reported status this also
 * fails the task when progress stops moving (30s while still in phase 1, 120s
 * otherwise) or when the status endpoint becomes unreachable.
 */
export function usePolling({
  taskId,
  intervalMs = 1000,
  onComplete,
  onError,
}: UsePollingOptions): PollingState {
  const t = useT();
  const [state, setState] = useState<PollingState>({
    progress: 0,
    message: t("loading_initializing"),
    isComplete: false,
    error: null,
  });

  // Read through a ref so retranslating never restarts the polling interval
  const tRef = useRef(t);
  useEffect(() => {
    tRef.current = t;
  });

  // Kept in refs so changing a callback never restarts the interval
  const onCompleteRef = useRef(onComplete);
  const onErrorRef = useRef(onError);
  useEffect(() => {
    onCompleteRef.current = onComplete;
    onErrorRef.current = onError;
  });

  useEffect(() => {
    if (!taskId) return;

    let stopped = false;
    let lastPct = 0;
    let lastProgressChange = Date.now();
    let fetchFailCount = 0;
    let timer: ReturnType<typeof setInterval> | null = null;

    const stop = () => {
      stopped = true;
      if (timer) clearInterval(timer);
    };

    const fail = (error: string) => {
      stop();
      setState((s) => ({ ...s, error }));
      onErrorRef.current?.(error);
    };

    const failWith = (key: keyof typeof ERROR_KEYS) => fail(tRef.current(ERROR_KEYS[key]));

    const poll = async () => {
      if (stopped) return;

      let data: TaskStatus;
      try {
        const raw = await fetcher<unknown>(`/api/status/${taskId}`);
        const parsed = TaskStatusSchema.safeParse(raw);
        if (!parsed.success) {
          fetchFailCount++;
          if (fetchFailCount >= MAX_FETCH_FAILS) failWith("connection");
          return;
        }
        data = parsed.data;
        fetchFailCount = 0;
      } catch {
        fetchFailCount++;
        if (fetchFailCount >= MAX_FETCH_FAILS) failWith("connection");
        return;
      }

      const pct = data.progress ?? 0;
      if (pct > lastPct) {
        lastPct = pct;
        lastProgressChange = Date.now();
      }
      setState((s) => ({
        ...s,
        progress: Math.max(s.progress, pct),
        message: data.message || s.message,
      }));

      if (data.status === "completed") {
        stop();
        setState((s) => ({
          ...s,
          progress: 100,
          message: tRef.current("loading_completed"),
          isComplete: true,
        }));
        onCompleteRef.current?.();
        return;
      }

      if (data.status === "error") {
        fail(data.message || tRef.current(ERROR_KEYS.stalled));
        return;
      }

      const elapsed = Date.now() - lastProgressChange;
      if (lastPct <= 10 && elapsed > PHASE1_TIMEOUT_MS) {
        failWith("openalex");
      } else if (elapsed > STALL_TIMEOUT_MS) {
        failWith("stalled");
      }
    };

    poll();
    timer = setInterval(poll, intervalMs);
    return stop;
  }, [taskId, intervalMs]);

  return state;
}
