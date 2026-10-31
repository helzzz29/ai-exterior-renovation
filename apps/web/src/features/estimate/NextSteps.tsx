import { FolderOpen, Palette, PartyPopper, Plus } from "lucide-react";
import { Link } from "react-router";
import { copy } from "@/copy";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";

/** End of the journey: tells the homeowner what they can do once the report is ready. */
export function NextSteps({
  projectId,
  designId,
  downloaded,
}: {
  projectId: string;
  designId: string;
  downloaded: boolean;
}) {
  return (
    <Card data-testid="next-steps" className="border-primary/30 bg-[linear-gradient(120deg,var(--accent),var(--card)_70%)]">
      <CardContent className="space-y-4 pt-5 sm:pt-6">
        <div className="flex items-start gap-3">
          <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-card text-primary shadow-xs" aria-hidden="true">
            <PartyPopper className="size-5" />
          </span>
          <div className="space-y-1">
            <h2 className="text-lg font-semibold tracking-tight">{downloaded ? copy.next.titleDone : copy.next.title}</h2>
            <p className="text-sm leading-relaxed text-muted-foreground">{copy.next.intro}</p>
          </div>
        </div>
        <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap">
          <Button asChild>
            <Link to="/">
              <FolderOpen aria-hidden="true" />
              {copy.next.home}
            </Link>
          </Button>
          {/* Opens the same design in step 4: it does not make a new design. */}
          <Button asChild variant="outline">
            <Link to={`/projects/${projectId}/materials?design=${designId}`}>
              <Palette aria-hidden="true" />
              {copy.next.anotherDesign}
            </Link>
          </Button>
          <Button asChild variant="outline">
            <Link to="/projects/new">
              <Plus aria-hidden="true" />
              {copy.next.newProject}
            </Link>
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
