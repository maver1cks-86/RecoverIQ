import { useCallback, useEffect, useState } from "react";
import { getHealth } from "../api/health";

export type ConnectionState = "checking" | "connected" | "unavailable";

export function useBackendHealth() {
  const [state, setState] = useState<ConnectionState>("checking");

  const check = useCallback(async () => {
    setState("checking");
    try {
      const result = await getHealth();
      setState(result.status === "healthy" ? "connected" : "unavailable");
    } catch {
      setState("unavailable");
    }
  }, []);

  useEffect(() => {
    void check();
  }, [check]);

  return { state, check };
}
