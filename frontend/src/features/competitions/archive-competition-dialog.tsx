import { useEffect } from "react";
import { toast } from "sonner";

import { ApiError } from "@/api/errors";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import type { Competition } from "@/features/competitions/api";
import { useArchiveCompetition } from "@/features/competitions/queries";

interface ArchiveCompetitionDialogProps {
  competition: Competition | null;
  onOpenChange: (open: boolean) => void;
}

export function ArchiveCompetitionDialog({
  competition,
  onOpenChange,
}: ArchiveCompetitionDialogProps): React.JSX.Element {
  const mutation = useArchiveCompetition();
  const resetMutation = mutation.reset;

  useEffect(() => {
    if (competition) resetMutation();
  }, [competition, resetMutation]);

  async function archive(): Promise<void> {
    if (!competition) return;
    try {
      await mutation.mutateAsync(competition.id);
      toast.success("League archived", {
        description: `${competition.display_name} was removed from active league lists.`,
      });
      onOpenChange(false);
    } catch {
      // The normalized mutation error remains visible in the dialog.
    }
  }

  return (
    <Dialog open={competition !== null} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Archive {competition?.display_name}?</DialogTitle>
          <DialogDescription>
            This is one-way in the current product. The league disappears from
            active lists, but its seasons, articles, and historical direct reads
            remain available.
          </DialogDescription>
        </DialogHeader>
        {mutation.error ? (
          <p
            role="alert"
            className="mt-5 rounded-md bg-destructive/10 p-3 text-sm text-destructive"
          >
            {mutation.error instanceof ApiError
              ? mutation.error.message
              : "The competition could not be archived."}
          </p>
        ) : null}
        <DialogFooter>
          <Button
            type="button"
            variant="ghost"
            onClick={() => {
              onOpenChange(false);
            }}
          >
            Keep competition
          </Button>
          <Button
            type="button"
            variant="destructive"
            disabled={mutation.isPending}
            onClick={() => void archive()}
          >
            {mutation.isPending ? "Archiving…" : "Archive competition"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
