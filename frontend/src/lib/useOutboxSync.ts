import { useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";

import { syncOutbox } from "./outbox";

const INTERVAL_MS = 30_000;

/** Envoie la file hors ligne au démarrage, au retour du réseau, puis régulièrement. */
export function useOutboxSync() {
  const queryClient = useQueryClient();
  useEffect(() => {
    const run = async () => {
      if (!navigator.onLine) return;
      const result = await syncOutbox();
      if (result.sent || result.rejected)
        await queryClient.invalidateQueries({ queryKey: ["orgs"] });
    };
    void run();
    window.addEventListener("online", run);
    const timer = window.setInterval(run, INTERVAL_MS);
    return () => {
      window.removeEventListener("online", run);
      window.clearInterval(timer);
    };
  }, [queryClient]);
}
