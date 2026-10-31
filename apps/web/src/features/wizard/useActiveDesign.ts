import { useCallback } from "react";
import { useSearchParams } from "react-router";
import { useDesigns } from "@/api/hooks";
import type { DesignOut } from "@/api/types";

/** The design being worked on in steps 4-6 lives in the URL (`?design=`), so steps share it. */
export function useActiveDesign(projectId: string, enabled = true) {
  const [params, setParams] = useSearchParams();
  const designs = useDesigns(projectId, enabled);
  const wanted = params.get("design");
  const list: DesignOut[] = designs.data ?? [];
  const active = list.find((d) => d.id === wanted) ?? list[0] ?? null;
  const setActive = useCallback(
    (id: string) =>
      setParams(
        (prev) => {
          const next = new URLSearchParams(prev);
          next.set("design", id);
          return next;
        },
        { replace: true },
      ),
    [setParams],
  );
  return { designs, list, active, setActive };
}
