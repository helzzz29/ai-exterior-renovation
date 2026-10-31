import { type FormEvent, useRef, useState } from "react";
import { Ruler } from "lucide-react";
import { Link, useNavigate } from "react-router";
import { useCreateProject } from "@/api/hooks";
import { copy } from "@/copy";
import { PageHeader } from "@/components/layout";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";

function parsePositive(v: string): number | null | "bad" {
  if (!v.trim()) return null;
  const n = Number(v);
  return Number.isFinite(n) && n > 0 ? n : "bad";
}

type FieldName = "name" | "width" | "height" | "floors";
type Errors = Partial<Record<FieldName, string>>;

export function CreateProjectPage() {
  const create = useCreateProject();
  const navigate = useNavigate();
  const [values, setValues] = useState<Record<FieldName, string>>({ name: "", width: "", height: "", floors: "" });
  const [errors, setErrors] = useState<Errors>({});
  const refs = {
    name: useRef<HTMLInputElement>(null),
    width: useRef<HTMLInputElement>(null),
    height: useRef<HTMLInputElement>(null),
    floors: useRef<HTMLInputElement>(null),
  };

  const set = (field: FieldName, v: string) => {
    setValues((x) => ({ ...x, [field]: v }));
    // An error goes away as soon as the field is changed; it is checked again on submit.
    if (errors[field]) setErrors((x) => ({ ...x, [field]: undefined }));
  };

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    const next: Errors = {};
    if (!values.name.trim()) next.name = copy.create.nameRequired;
    const w = parsePositive(values.width);
    const h = parsePositive(values.height);
    if (w === "bad") next.width = copy.create.positive;
    if (h === "bad") next.height = copy.create.positive;
    let f: number | null = null;
    if (values.floors.trim()) {
      f = Number(values.floors);
      if (!Number.isInteger(f) || f < 1 || f > 10) next.floors = copy.create.floorsRange;
    }
    setErrors(next);
    const first = (Object.keys(refs) as FieldName[]).find((k) => next[k]);
    if (first) return refs[first].current?.focus();
    create.mutate(
      {
        name: values.name.trim(),
        measurements: {
          facade_width_ft: w as number | null,
          facade_height_ft: h as number | null,
          floors: f,
          reference_line: null,
        },
      },
      { onSuccess: (p) => navigate(`/projects/${p.id}/photo`) },
    );
  };

  const sizeField = (field: "width" | "height" | "floors", label: string, inputMode: "decimal" | "numeric") => (
    <Field id={field} label={label} error={errors[field]} className="justify-between">
      {(a) => (
        <Input
          {...a}
          ref={refs[field]}
          inputMode={inputMode}
          value={values[field]}
          onChange={(e) => set(field, e.target.value)}
        />
      )}
    </Field>
  );

  return (
    <div className="grid grid-cols-1 gap-8 lg:grid-cols-[minmax(0,40rem)_minmax(0,1fr)] lg:gap-12">
      <div className="space-y-6">
        <PageHeader title={copy.create.title} description={copy.create.intro} />
        <Card>
          <CardContent className="pt-5 sm:pt-6">
            <form className="space-y-6" onSubmit={onSubmit} noValidate>
              <Field id="name" label={copy.create.name} hint={copy.create.nameHint} error={errors.name}>
                {(a) => (
                  <Input
                    {...a}
                    ref={refs.name}
                    value={values.name}
                    maxLength={120}
                    placeholder={copy.create.namePlaceholder}
                    onChange={(e) => set("name", e.target.value)}
                    required
                    aria-required="true"
                  />
                )}
              </Field>
              <fieldset className="space-y-4 rounded-xl border bg-paper/50 p-4 sm:p-5">
                <legend className="flex items-center gap-2 px-1 text-sm font-semibold">
                  <Ruler className="size-4 text-primary" aria-hidden="true" />
                  {copy.create.measureTitle} ({copy.common.optional})
                </legend>
                <p className="text-sm leading-relaxed text-muted-foreground">{copy.create.measureHelp}</p>
                <div className="grid items-stretch gap-4 sm:grid-cols-3">
                  {sizeField("width", copy.create.width, "decimal")}
                  {sizeField("height", copy.create.height, "decimal")}
                  {sizeField("floors", copy.create.floors, "numeric")}
                </div>
              </fieldset>
              <div className="flex flex-col-reverse gap-3 sm:flex-row sm:items-center sm:justify-between">
                <Button asChild variant="ghost">
                  <Link to="/">{copy.create.cancel}</Link>
                </Button>
                <Button type="submit" size="lg" pending={create.isPending} className="sm:min-w-48">
                  {create.isPending ? copy.create.submitting : copy.create.submit}
                </Button>
              </div>
            </form>
          </CardContent>
        </Card>
      </div>
      <aside className="hidden lg:block" aria-labelledby="journey-title">
        <div className="sticky top-24 space-y-4 rounded-2xl border bg-paper p-6">
          <h2 id="journey-title" className="text-sm font-semibold tracking-wide text-primary uppercase">
            {copy.stepper.label}
          </h2>
          <ol className="space-y-3">
            {copy.stepper.steps.map((s, i) => (
              <li key={s} className="flex items-center gap-3 text-sm">
                <span className="grid size-7 shrink-0 place-items-center rounded-full border border-primary/30 bg-card text-xs font-semibold text-primary">
                  {i + 1}
                </span>
                {s}
              </li>
            ))}
          </ol>
        </div>
      </aside>
    </div>
  );
}
