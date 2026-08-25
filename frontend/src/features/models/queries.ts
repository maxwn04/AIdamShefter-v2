import { useQuery } from "@tanstack/react-query";

import { queryKeys } from "@/api/query-keys";
import { getModelCatalog } from "@/features/models/api";

export function useModelCatalog() {
  return useQuery({
    queryKey: queryKeys.models.catalog(),
    queryFn: ({ signal }) => getModelCatalog(signal),
  });
}
