import { useQueryClient } from "@tanstack/react-query";

export function useInvalidateProject(orgId: string, projectId: string) {
  const queryClient = useQueryClient();
  return () => queryClient.invalidateQueries({ queryKey: ["orgs", orgId, "projects", projectId] });
}
