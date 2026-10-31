import { type FormEvent, type ReactNode, useEffect, useRef, useState } from "react";
import { ArrowRight, CheckCircle2, PenLine, Ruler, TriangleAlert } from "lucide-react";
import { Link, useNavigate } from "react-router";
import { useConfirmScale, useScale } from "@/api/hooks";
import type { BoxPx, Point, ScaleConfirm, ScaleOut } from "@/api/types";
import { copy } from "@/copy";
import { PageHeader } from "@/components/layout";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Field, FieldError } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ErrorState, PageSkeleton, Spinner } from "@/components/states";
import { formatFeet } from "@/lib/format";
import { BackLink } from "@/features/wizard/DesignBar";
import { useWizard } from "@/features/wizard/context";
import { LineDrawer } from "./LineDrawer";

export type ScaleVariant = "confirmed" | "high" | "medium" | "low";

/** Which of the three size-check screens to show. */
export function scaleVariant(s: ScaleOut): ScaleVariant {
  if (s.confirmed) return "confirmed";
  if (s.needs_measurement || s.confidence === "low") return "low";
  if (s.confidence === "high") return "high";
  return "medium";
}

function PhotoWithBox({ url, width, height, box }: { url: string; width: number; height: number; box: BoxPx | null }) {
  return (
    <div className="relative w-full overflow-hidden rounded-lg border bg-muted" style={{ aspectRatio: `${width} / ${height}` }}>
      <img src={url} alt={copy.size.photoAlt} className="absolute inset-0 size-full object-fill" />
      {box && (
        <div
          data-testid="reference-box"
          className="absolute rounded-sm border-4 border-warning shadow-[0_0_0_9999px_rgba(0,0,0,0.35)]"
          style={{
            left: `${(box.x0 / width) * 100}%`,
            top: `${(box.y0 / height) * 100}%`,
            width: `${((box.x1 - box.x0) / width) * 100}%`,
            height: `${((box.y1 - box.y0) / height) * 100}%`,
          }}
        />
      )}
    </div>
  );
}

type FormErrors = { width?: string; points?: string; length?: string };

function MeasurementForm({
  onSubmit,
  onCancel,
  busy,
}: {
  onSubmit: (body: ScaleConfirm) => void;
  /** Only when the form was opened from another size-check screen. */
  onCancel?: () => void;
  busy: boolean;
}) {
  const { project } = useWizard();
  const [tab, setTab] = useState<"width" | "line">("width");
  const [width, setWidth] = useState("");
  const [length, setLength] = useState("");
  const [points, setPoints] = useState<Point[]>([]);
  const [errors, setErrors] = useState<FormErrors>({});
  const photo = project.photo!;
  const widthInput = useRef<HTMLInputElement>(null);
  const lengthInput = useRef<HTMLInputElement>(null);
  const focusWidth = useRef(false);

  useEffect(() => {
    if (tab === "width" && focusWidth.current) {
      focusWidth.current = false;
      // After the tab switch has settled, so the tabs don't take focus back.
      const t = setTimeout(() => widthInput.current?.focus(), 0);
      return () => clearTimeout(t);
    }
  }, [tab]);

  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (tab === "width") {
      const w = Number(width);
      if (!width.trim() || !Number.isFinite(w) || w <= 0) {
        setErrors({ width: copy.size.positive });
        return widthInput.current?.focus();
      }
      setErrors({});
      onSubmit({ accept: false, facade_width_ft: w });
    } else {
      // The line comes first on screen, so it is checked first.
      if (points.length < 2) return setErrors({ points: copy.size.lineNeedsTwoPoints });
      const l = Number(length);
      if (!length.trim() || !Number.isFinite(l) || l <= 0) {
        setErrors({ length: copy.size.positive });
        return lengthInput.current?.focus();
      }
      setErrors({});
      onSubmit({
        accept: false,
        reference_line: { x1: points[0][0], y1: points[0][1], x2: points[1][0], y2: points[1][1], length_ft: l },
      });
    }
  };

  return (
    <form onSubmit={submit} className="space-y-5" noValidate>
      <Tabs
        value={tab}
        onValueChange={(v) => {
          setTab(v as "width" | "line");
          setErrors({});
        }}
      >
        <TabsList className="grid w-full grid-cols-2 sm:inline-grid sm:w-auto">
          <TabsTrigger value="width" className="whitespace-normal">
            <Ruler className="size-4 shrink-0" aria-hidden="true" />
            {copy.size.optionWidth}
          </TabsTrigger>
          <TabsTrigger value="line" className="whitespace-normal">
            <PenLine className="size-4 shrink-0" aria-hidden="true" />
            {copy.size.optionLine}
          </TabsTrigger>
        </TabsList>
        <TabsContent value="width" className="mt-5">
          <Field id="facade-width" label={copy.size.widthLabel} error={errors.width} className="sm:max-w-xs">
            {(a) => (
              <Input
                {...a}
                ref={widthInput}
                inputMode="decimal"
                value={width}
                onChange={(e) => {
                  setWidth(e.target.value);
                  if (errors.width) setErrors({});
                }}
              />
            )}
          </Field>
        </TabsContent>
        <TabsContent value="line" className="mt-5 space-y-4">
          <p className="text-sm leading-relaxed text-muted-foreground">{copy.size.lineHelp}</p>
          {/* Drawing needs a pointer; the width field is the keyboard and screen-reader route. */}
          <Button
            type="button"
            variant="link"
            className="h-auto px-0 text-left whitespace-normal"
            onClick={() => {
              setTab("width");
              setErrors({});
              focusWidth.current = true;
            }}
          >
            {copy.size.orWidth}
          </Button>
          <LineDrawer
            photoUrl={photo.url}
            width={photo.width}
            height={photo.height}
            points={points}
            onChange={(pts) => {
              setPoints(pts);
              if (errors.points && pts.length >= 2) setErrors((x) => ({ ...x, points: undefined }));
            }}
          />
          {errors.points && <FieldError>{errors.points}</FieldError>}
          <div className="flex flex-wrap items-end gap-3">
            <Field id="line-length" label={copy.size.lineLength} error={errors.length} className="w-full sm:max-w-xs">
              {(a) => (
                <Input
                  {...a}
                  ref={lengthInput}
                  inputMode="decimal"
                  value={length}
                  onChange={(e) => {
                    setLength(e.target.value);
                    if (errors.length) setErrors((x) => ({ ...x, length: undefined }));
                  }}
                />
              )}
            </Field>
            <Button type="button" variant="ghost" onClick={() => setPoints([])} disabled={!points.length}>
              {copy.size.lineReset}
            </Button>
          </div>
        </TabsContent>
      </Tabs>
      <div className="flex flex-col-reverse gap-2 border-t pt-5 sm:flex-row sm:items-center sm:justify-end">
        {onCancel && (
          <Button type="button" variant="ghost" onClick={onCancel}>
            {copy.common.cancel}
          </Button>
        )}
        <Button type="submit" size="lg" pending={busy}>
          {busy ? copy.size.saving : copy.size.save}
        </Button>
      </div>
    </form>
  );
}

export function ScaleStep() {
  const { project } = useWizard();
  const navigate = useNavigate();
  const scale = useScale(project.id);
  const confirm = useConfirmScale(project.id);
  const [editing, setEditing] = useState(false);
  const autoConfirmed = useRef(false);
  const variant = scale.data ? scaleVariant(scale.data) : null;

  const done = () => navigate(`/projects/${project.id}/materials`);
  const send = (body: ScaleConfirm) =>
    confirm.mutate(body, {
      onSuccess: () => {
        setEditing(false);
        done();
      },
    });

  // High: the user's own measurement is all we need, so this screen confirms itself.
  useEffect(() => {
    if (variant === "high" && !autoConfirmed.current) {
      autoConfirmed.current = true;
      confirm.mutate({ accept: true }, { onSuccess: done });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [variant]);

  const header = (
    <PageHeader id="size-title" eyebrow={copy.stepper.stepOf(3, 6)} title={copy.size.title} description={copy.size.intro} />
  );
  const wrap = (body: ReactNode) => (
    <section className="space-y-6" aria-labelledby="size-title">
      {header}
      <div className="max-w-4xl">{body}</div>
      <BackLink projectId={project.id} from="size" />
    </section>
  );

  if (scale.isPending) return wrap(<PageSkeleton label={copy.size.loading} />);
  if (scale.isError) return wrap(<ErrorState error={scale.error} onRetry={() => void scale.refetch()} />);
  const s = scale.data;
  const photo = project.photo!;
  const width = s.facade_width_ft ? formatFeet(Math.round(s.facade_width_ft)) : null;

  let body;
  if (editing) {
    body = (
      <Card>
        <CardHeader>
          <CardTitle>{copy.size.enterMeasurement}</CardTitle>
        </CardHeader>
        <CardContent>
          <MeasurementForm onSubmit={send} onCancel={() => setEditing(false)} busy={confirm.isPending} />
        </CardContent>
      </Card>
    );
  } else if (variant === "confirmed") {
    body = (
      <Card>
        <CardContent className="flex flex-col gap-4 pt-5 sm:flex-row sm:items-center sm:pt-6">
          <span className="grid size-12 shrink-0 place-items-center rounded-full bg-success-soft text-success" aria-hidden="true">
            <CheckCircle2 className="size-6" />
          </span>
          <div className="space-y-1">
            <h2 className="text-lg font-semibold tracking-tight">{copy.size.confirmedTitle}</h2>
            <p>{width ? copy.size.confirmedBody(width) : copy.size.confirmedNoWidth}</p>
          </div>
        </CardContent>
        <CardFooter>
          <Button asChild>
            <Link to={`/projects/${project.id}/materials`}>
              {copy.size.toMaterials}
              <ArrowRight aria-hidden="true" />
            </Link>
          </Button>
          <Button variant="outline" onClick={() => setEditing(true)}>
            {copy.size.change}
          </Button>
        </CardFooter>
      </Card>
    );
  } else if (variant === "high") {
    body = (
      <Card aria-live="polite">
        <CardHeader>
          <CardTitle>{copy.size.highTitle}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <p>{width ? copy.size.highBody(width) : copy.size.highNoWidth}</p>
          {confirm.isPending && <Spinner />}
        </CardContent>
      </Card>
    );
  } else if (variant === "medium") {
    body = (
      <Card>
        <CardHeader>
          <CardTitle>{copy.size.mediumTitle}</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-5 md:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)] md:items-start">
          <figure className="space-y-2">
            <PhotoWithBox url={photo.url} width={photo.width} height={photo.height} box={s.reference_box} />
            <figcaption className="text-xs text-muted-foreground">{copy.size.guideCaption}</figcaption>
          </figure>
          <p className="text-base leading-relaxed" data-testid="scale-explanation">
            {s.explanation}
          </p>
        </CardContent>
        <CardFooter>
          <Button size="lg" onClick={() => send({ accept: true })} pending={confirm.isPending}>
            {copy.size.lookRight}
          </Button>
          <Button size="lg" variant="outline" onClick={() => setEditing(true)}>
            {copy.size.enterMeasurement}
          </Button>
        </CardFooter>
      </Card>
    );
  } else {
    body = (
      <Card className="border-warning">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <TriangleAlert className="size-5 shrink-0 text-warning-foreground" aria-hidden="true" />
            {copy.size.lowTitle}
          </CardTitle>
          <p className="text-sm leading-relaxed">{copy.size.lowBody}</p>
        </CardHeader>
        <CardContent>
          <MeasurementForm onSubmit={send} busy={confirm.isPending} />
        </CardContent>
      </Card>
    );
  }

  return wrap(body);
}
