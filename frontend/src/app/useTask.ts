import { useCallback, useMemo, useRef, useState } from "react";
import type { TaskRunner } from "../types";

export function useTask() {
  const lock = useRef(false);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const run = useCallback(async (label: string, work: () => Promise<void>) => {
    if (lock.current) return;
    lock.current = true;
    setBusy(label);
    setError("");
    try {
      await work();
    } catch (failure) {
      setError(
        failure instanceof Error
          ? failure.message
          : "Не удалось выполнить операцию",
      );
    } finally {
      lock.current = false;
      setBusy("");
    }
  }, []);
  const tasks = useMemo<TaskRunner>(
    () => ({
      run,
      isRunning: () => lock.current,
      reportError: setError,
    }),
    [run],
  );
  return { tasks, busy, error };
}
