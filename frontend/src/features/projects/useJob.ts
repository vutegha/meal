import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { aiApi, type Job } from "@/lib/api";

/** Suit une tâche longue (IA) jusqu'à sa fin, puis appelle onSucceeded. */
export function useJob(orgId: string, onSucceeded: (job: Job) => Promise<unknown> | void) {
  const [jobId, setJobId] = useState<string | null>(null);
  const query = useQuery({
    queryKey: ["orgs", orgId, "jobs", jobId],
    queryFn: async () => {
      const job = await aiApi.job(orgId, jobId!);
      if (job.status === "succeeded") await onSucceeded(job);
      return job;
    },
    enabled: jobId !== null,
    refetchInterval: (q) => {
      const status = q.state.data?.status;
      return status === "succeeded" || status === "failed" ? false : 2000;
    },
  });
  const status = query.data?.status;
  return {
    start: (job: Job) => setJobId(job.id),
    running: jobId !== null && status !== "succeeded" && status !== "failed",
    error: status === "failed" ? query.data?.error : (query.error ?? null),
  };
}
