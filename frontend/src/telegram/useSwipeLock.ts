import { useEffect } from "react";
import { tg } from "../api";
let locks = 0;
export function useSwipeLock(enabled: boolean) {
  useEffect(() => {
    if (!enabled || (tg?.isVersionAtLeast && !tg.isVersionAtLeast("7.7")))
      return;
    if (locks++ === 0)
      try {
        tg?.disableVerticalSwipes?.();
      } catch {}
    return () => {
      if (--locks === 0)
        try {
          tg?.enableVerticalSwipes?.();
        } catch {}
    };
  }, [enabled]);
}
