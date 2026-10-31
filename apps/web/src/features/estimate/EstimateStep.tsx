import { Fragment, type ReactNode, useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Calculator, CheckCircle2, ChevronDown, Circle, Download, FileText, Loader2, Lock } from "lucide-react";
import { Link } from "react-router";
import { toast } from "sonner";
import { errorMessage } from "@/api/client";
import {
  isJobFinished,
  putRatesKeepalive,
  qk,
  useCreateReport,
  useEstimate,
  useFinaliseEstimate,
  useJob,
  useMaterials,
  useRates,
  useReports,
  useSaveRates,
} from "@/api/hooks";
import type { Estimate, Extras, LineItem, MaterialOut } from "@/api/types";
import { copy } from "@/copy";
import { StatusBadge } from "@/components/feedback";
import { PageHeader } from "@/components/layout";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { EmptyState, ErrorState, PageSkeleton, Spinner } from "@/components/states";
import { AUTOSAVE_MS } from "@/lib/config";
import { formatINR, formatNumber, formatTotalRange, unitWord } from "@/lib/format";
import { friendlyName, LABEL_STYLES } from "@/lib/labels";
import { DESKTOP, useMediaQuery } from "@/lib/useMediaQuery";
import { cn } from "@/lib/utils";
import { BackLink, DesignBar } from "@/features/wizard/DesignBar";
import { lookState } from "@/features/wizard/progress";
import { useWizard } from "@/features/wizard/context";
import { useActiveDesign } from "@/features/wizard/useActiveDesign";
import { NextSteps } from "./NextSteps";
import {
  buyText,
  currentReport,
  draftsFromOverrides,
  reportFileName,
  type ExtrasDraft,
  extrasDraft,
  type RateDrafts,
  rateErrors,
  reportReadiness,
  toRatesPut,
  uniqueMaterials,
} from "./logic";

async function downloadFile(url: string, fileName: string) {
  const res = await fetch(url, { credentials: "include" });
  if (!res.ok) throw new Error("download failed");
  const blob = await res.blob();
  const href = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = href;
  a.download = fileName;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(href), 10_000);
}

function companionCost(line: LineItem) {
  return line.companions.reduce((s, c) => s + c.cost, 0);
}

function PartName({ line }: { line: LineItem }) {
  return (
    <span className="inline-flex items-center gap-2 font-medium">
      <span className="size-2.5 shrink-0 rounded-full" style={{ background: LABEL_STYLES[line.label]?.colour }} aria-hidden="true" />
      {friendlyName(line.label)}
      {line.region_ids.length > 1 && (
        <span className="text-xs font-normal text-muted-foreground">×{line.region_ids.length}</span>
      )}
    </span>
  );
}

function Includes({ line }: { line: LineItem }) {
  if (!line.companions.length) return null;
  return (
    <span className="block text-xs font-normal text-muted-foreground">
      {copy.cost.includes(line.companions.map((c) => c.name.toLowerCase()).join(", "))}
    </span>
  );
}

function Derivation({ line, open, onToggle }: { line: LineItem; open: boolean; onToggle: () => void }) {
  return (
    <>
      <button
        type="button"
        className="inline-flex min-h-9 items-center gap-1 rounded-md text-sm font-medium text-primary hover:underline"
        aria-expanded={open}
        onClick={onToggle}
      >
        <ChevronDown className={cn("size-4 transition-transform", open && "rotate-180")} aria-hidden="true" />
        {open ? copy.cost.hideCalculation : copy.cost.howCalculated}
      </button>
      {open && (
        <ol className="mt-1 list-decimal space-y-1 rounded-lg bg-muted p-3 pl-8 text-sm" data-testid="derivation">
          {line.derivation.map((d, i) => (
            <li key={i}>{d}</li>
          ))}
        </ol>
      )}
    </>
  );
}

/** Desktop: one table row per line, with the calculation underneath. */
function LineRow({ line, highlight }: { line: LineItem; highlight: boolean }) {
  const [open, setOpen] = useState(false);
  return (
    <Fragment>
      <tr className="border-t align-top">
        <td className="py-3 pr-3">
          <PartName line={line} />
        </td>
        <td className="py-3 pr-3">
          {line.material_name}
          {highlight && (
            <Badge variant="warning" className="ml-1.5">
              {copy.cost.changed}
            </Badge>
          )}
        </td>
        <td className="py-3 pr-3 whitespace-nowrap">
          {formatNumber(line.measured_quantity)} {copy.cost.units[line.measured_unit]}
        </td>
        <td className="py-3 pr-3">{buyText(line)}</td>
        <td className="py-3 pr-3 text-right whitespace-nowrap tabular-nums">
          {formatINR(line.material_cost + companionCost(line))}
          <Includes line={line} />
        </td>
        <td className="py-3 pr-3 text-right whitespace-nowrap tabular-nums">{formatINR(line.labour_cost)}</td>
        <td className="py-3 text-right font-semibold whitespace-nowrap tabular-nums">{formatINR(line.total)}</td>
      </tr>
      <tr>
        <td colSpan={7} className="pb-2">
          <Derivation line={line} open={open} onToggle={() => setOpen((v) => !v)} />
        </td>
      </tr>
    </Fragment>
  );
}

/** Phones and tablets: the same values as a card, so nothing needs sideways scrolling. */
function LineCard({ line, highlight }: { line: LineItem; highlight: boolean }) {
  const [open, setOpen] = useState(false);
  const rows: [string, ReactNode][] = [
    [copy.cost.cols.size, `${formatNumber(line.measured_quantity)} ${copy.cost.units[line.measured_unit]}`],
    [copy.cost.cols.buy, buyText(line)],
    [
      copy.cost.cols.materialCost,
      <>
        {formatINR(line.material_cost + companionCost(line))}
        <Includes line={line} />
      </>,
    ],
    [copy.cost.cols.labour, formatINR(line.labour_cost)],
  ];
  return (
    <li className="space-y-2 border-t py-4 first:border-t-0 first:pt-0">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 space-y-0.5">
          <PartName line={line} />
          <p className="text-sm text-muted-foreground">
            {line.material_name}
            {highlight && (
              <Badge variant="warning" className="ml-1.5">
                {copy.cost.changed}
              </Badge>
            )}
          </p>
        </div>
        <p className="text-right">
          <span className="block text-xs text-muted-foreground">{copy.cost.cols.total}</span>
          <span className="font-semibold tabular-nums">{formatINR(line.total)}</span>
        </p>
      </div>
      <dl className="grid grid-cols-2 gap-x-4 gap-y-2 rounded-lg bg-paper/70 p-3 text-sm">
        {rows.map(([k, v]) => (
          <div key={k} className="min-w-0">
            <dt className="text-xs text-muted-foreground">{k}</dt>
            <dd className="tabular-nums">{v}</dd>
          </div>
        ))}
      </dl>
      <Derivation line={line} open={open} onToggle={() => setOpen((v) => !v)} />
    </li>
  );
}

function Totals({ e }: { e: Estimate }) {
  const rows: [string, number][] = [
    [copy.cost.summary.lines, e.lines_total],
    [copy.cost.summary.scaffolding, e.scaffolding],
    [copy.cost.summary.contingency, e.contingency],
    [copy.cost.summary.tax, e.tax],
  ];
  return (
    <dl className="ml-auto w-full max-w-sm space-y-1.5 border-t-2 pt-3 text-sm">
      {rows.map(([label, v]) => (
        <div key={label} className="flex justify-between gap-4">
          <dt className="text-muted-foreground">{label}</dt>
          <dd className="tabular-nums">{formatINR(v)}</dd>
        </div>
      ))}
      <div className="flex justify-between gap-4 border-t pt-2 text-base font-semibold">
        <dt>{copy.cost.summary.total}</dt>
        <dd className="tabular-nums" data-testid="grand-total">
          {formatINR(e.grand_total)}
        </dd>
      </div>
    </dl>
  );
}

function RateField({
  id,
  label,
  value,
  usual,
  error,
  onChange,
  onBlur,
}: {
  id: string;
  label: string;
  value: string | undefined;
  usual: number;
  error?: string;
  onChange: (v: string | undefined) => void;
  onBlur: () => void;
}) {
  const changed = value != null && value.trim() !== "" && Number(value) !== usual;
  return (
    <Field id={id} label={label} error={error} labelClassName="text-xs">
      {(a) => (
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
          <div className="relative w-36">
            <span className="pointer-events-none absolute top-1/2 left-3 -translate-y-1/2 text-sm text-muted-foreground" aria-hidden="true">
              ₹
            </span>
            <Input
              {...a}
              inputMode="decimal"
              value={value ?? String(usual)}
              placeholder={String(usual)}
              onChange={(e) => onChange(e.target.value)}
              onBlur={onBlur}
              data-changed={changed ? "true" : "false"}
              className={cn("pl-7 tabular-nums", changed && "border-warning bg-warning-soft font-semibold")}
            />
          </div>
          {changed && (
            <Button type="button" variant="link" size="sm" className="px-0" onClick={() => onChange(undefined)}>
              {copy.cost.resetPrice}
            </Button>
          )}
        </div>
      )}
    </Field>
  );
}

export function EstimateStep() {
  const { project } = useWizard();
  const qc = useQueryClient();
  const { designs, list, active, setActive } = useActiveDesign(project.id);
  const estimate = useEstimate(active?.id);
  const rates = useRates(project.id);
  const materials = useMaterials();
  const saveRates = useSaveRates(project.id);
  const finalise = useFinaliseEstimate(project.id, active?.id ?? "");
  const createReport = useCreateReport();
  const reports = useReports(active?.id);
  const [reportJobId, setReportJobId] = useState<string | null>(null);
  const reportJob = useJob(reportJobId);
  const desktop = useMediaQuery(DESKTOP);

  const [drafts, setDrafts] = useState<RateDrafts | null>(null);
  const [extras, setExtras] = useState<ExtrasDraft | null>(null);
  const [editVersion, setEditVersion] = useState(0);
  const savedVersion = useRef(0);
  const inFlightVersion = useRef<number | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const errors = drafts ? rateErrors(drafts, extras) : {};
  const hasErrors = Object.keys(errors).length > 0;

  // The latest edit, for saving on blur and when the screen closes.
  const latest = useRef<{ drafts: RateDrafts | null; extras: ExtrasDraft | null; version: number; base: Extras | undefined }>({
    drafts: null,
    extras: null,
    version: 0,
    base: undefined,
  });
  latest.current = { drafts, extras, version: editVersion, base: rates.data?.extras };
  const saveRatesRef = useRef(saveRates.mutate);
  saveRatesRef.current = saveRates.mutate;

  /** The edit that still needs sending, or null when there is nothing (valid) to send. */
  const unsent = () => {
    const l = latest.current;
    if (!l.drafts || !l.extras || !l.base) return null;
    if (l.version === savedVersion.current || inFlightVersion.current === l.version) return null;
    if (Object.keys(rateErrors(l.drafts, l.extras)).length) return null;
    return { version: l.version, body: toRatesPut(l.drafts, l.extras, l.base) };
  };

  const send = (version: number, body: ReturnType<typeof toRatesPut>) => {
    inFlightVersion.current = version;
    saveRates.mutate(body, {
      onSuccess: () => {
        savedVersion.current = Math.max(savedVersion.current, version);
      },
      onSettled: () => {
        if (inFlightVersion.current === version) inFlightVersion.current = null;
      },
    });
  };

  /** Save straight away (on leaving a field), instead of waiting for the typing pause. */
  const flush = () => {
    const next = unsent();
    if (!next) return;
    if (timer.current) clearTimeout(timer.current);
    timer.current = null;
    send(next.version, next.body);
  };

  useEffect(() => {
    if (rates.data && drafts === null) {
      setDrafts(draftsFromOverrides(rates.data.overrides));
      setExtras(extrasDraft(rates.data.extras));
    }
  }, [rates.data, drafts]);

  // Save price changes shortly after typing stops; the estimate is then fetched again.
  useEffect(() => {
    if (editVersion === savedVersion.current || !drafts || !extras || !rates.data || hasErrors) return;
    const v = editVersion;
    const body = toRatesPut(drafts, extras, rates.data.extras);
    timer.current = setTimeout(() => {
      timer.current = null;
      send(v, body);
    }, AUTOSAVE_MS * 2);
    return () => {
      if (timer.current) clearTimeout(timer.current);
      timer.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [editVersion, hasErrors]);

  // Leaving the screen (or closing the tab) before the pause is over still saves the last price.
  useEffect(() => {
    const onUnload = () => {
      const next = unsent();
      if (next) void putRatesKeepalive(project.id, next.body);
    };
    window.addEventListener("beforeunload", onUnload);
    return () => {
      window.removeEventListener("beforeunload", onUnload);
      const next = unsent();
      if (next) saveRatesRef.current(next.body);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // set when the user asked for a report that first had to be built: download it once it exists
  const [downloadWhenReady, setDownloadWhenReady] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [downloaded, setDownloaded] = useState(false);

  useEffect(() => {
    if (reportJobId && isJobFinished(reportJob.data)) {
      if (reportJob.data?.status === "failed") {
        toast.error(reportJob.data.error || copy.errors.generic);
        setDownloadWhenReady(false);
      }
      setReportJobId(null);
      void qc.invalidateQueries({ queryKey: qk.reports(active?.id ?? "none") });
    }
  }, [reportJob.data, reportJobId, qc, active?.id]);

  const save = (url: string) => {
    setDownloading(true);
    downloadFile(url, reportFileName(project.name, estimate.data?.version))
      .then(() => {
        setDownloaded(true);
        toast.success(copy.cost.downloaded);
      })
      .catch((err) => toast.error(errorMessage(err)))
      .finally(() => setDownloading(false));
  };

  // the report the user asked for has been built: download it straight away
  const readyReport = currentReport(reports.data, estimate.data?.version, active?.render?.id);
  useEffect(() => {
    if (!downloadWhenReady || reportJobId || downloading || !readyReport) return;
    setDownloadWhenReady(false);
    save(readyReport.download_url);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [downloadWhenReady, reportJobId, downloading, readyReport?.id]);

  const header = (
    <PageHeader id="cost-title" eyebrow={copy.stepper.stepOf(6, 6)} title={copy.cost.title} description={copy.cost.intro} />
  );
  const wrap = (body: ReactNode) => (
    <section className="space-y-5" aria-labelledby="cost-title">
      {header}
      {active && <DesignBar designs={list} active={active} onSelect={setActive} />}
      {body}
      <BackLink projectId={project.id} from="cost" />
    </section>
  );

  const materialsLink = `/projects/${project.id}/materials${active ? `?design=${active.id}` : ""}`;
  const emptyState = (
    <EmptyState
      icon={<Calculator />}
      title={copy.cost.noLines}
      action={
        <Button asChild>
          <Link to={materialsLink}>{copy.look.goToMaterials}</Link>
        </Button>
      }
    />
  );

  if (designs.isPending || (active && estimate.isPending)) return wrap(<PageSkeleton label={copy.cost.loading} />);
  if (designs.isError) return wrap(<ErrorState error={designs.error} onRetry={() => void designs.refetch()} />);
  if (estimate.isError) return wrap(<ErrorState error={estimate.error} onRetry={() => void estimate.refetch()} />);
  if (!active || !estimate.data) return wrap(emptyState);

  const eo = estimate.data;
  const e = eo.estimate;
  if (!e.lines.length) return wrap(emptyState);

  const catalogue: Record<string, MaterialOut> = Object.fromEntries((materials.data ?? []).map((m) => [m.id, m]));
  const overridden = new Set((rates.data?.overrides ?? []).map((o) => o.material_id));
  const ready = reportReadiness(active.render, eo);
  const latestReport = currentReport(reports.data, eo.version, active.render?.id);
  const reportBusy =
    downloading || createReport.isPending || !!reportJobId || (downloadWhenReady && !latestReport);
  const dirty = editVersion !== savedVersion.current;
  const updating = saveRates.isPending || estimate.isFetching || (dirty && !hasErrors);

  const setRate = (materialId: string, field: "material" | "labour", v: string | undefined) => {
    setDrafts((d) => ({ ...(d ?? {}), [materialId]: { ...(d?.[materialId] ?? {}), [field]: v } }));
    setEditVersion((n) => n + 1);
  };
  const setExtra = (field: keyof ExtrasDraft, v: string) => {
    setExtras((x) => (x ? { ...x, [field]: v } : x));
    setEditVersion((n) => n + 1);
  };

  // One button: download the up-to-date report, building it first when needed.
  const onDownload = () => {
    if (latestReport) return save(latestReport.download_url);
    setDownloadWhenReady(true);
    createReport.mutate(active.id, {
      onSuccess: (res) => setReportJobId(res.job_id),
      onError: (err) => {
        setDownloadWhenReady(false);
        toast.error(errorMessage(err));
      },
    });
  };

  const look = lookState(active.render);
  const lookLink = `/projects/${project.id}/look?design=${active.id}`;
  const estimateNeed = e.provisional ? copy.cost.estimateNeeds.rough : eo.finalised && eo.stale ? copy.cost.estimateNeeds.stale : copy.cost.estimateNeeds.draft;
  const lookNeed = look === "accepted" ? copy.cost.needAccept : copy.cost.lookNeeds[look];

  return wrap(
    <div className="space-y-5">
      <Card className="overflow-hidden">
        <CardContent className="flex flex-col gap-4 bg-[linear-gradient(120deg,var(--accent),var(--card)_60%)] pt-5 sm:flex-row sm:items-end sm:justify-between sm:pt-6">
          <div className="space-y-2">
            <p className="text-xs font-semibold tracking-wide text-primary uppercase">{copy.cost.summaryTitle}</p>
            <p className="text-2xl font-semibold tracking-tight sm:text-3xl" data-testid="total-range" aria-live="polite">
              {formatTotalRange(e.grand_total, e.range_low, e.range_high)}
            </p>
            <span className="block" data-testid="estimate-kind">
              <StatusBadge
                tone={e.provisional ? "attention" : "done"}
                label={e.provisional ? copy.cost.rough : copy.cost.measured}
              />
            </span>
            {e.provisional && (
              <p className="text-sm text-muted-foreground">
                {copy.cost.roughHelp}{" "}
                <Link className="font-medium text-primary underline" to={`/projects/${project.id}/size`}>
                  {copy.stale.sizeAction}
                </Link>
              </p>
            )}
          </div>
          <div className="min-h-6">{updating && <Spinner label={copy.cost.updating} />}</div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">{copy.cost.linesTitle}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {desktop ? (
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-muted-foreground">
                  <th className="pb-2 pr-3 font-medium">{copy.cost.cols.part}</th>
                  <th className="pb-2 pr-3 font-medium">{copy.cost.cols.material}</th>
                  <th className="pb-2 pr-3 font-medium">{copy.cost.cols.size}</th>
                  <th className="pb-2 pr-3 font-medium">{copy.cost.cols.buy}</th>
                  <th className="pb-2 pr-3 text-right font-medium">{copy.cost.cols.materialCost}</th>
                  <th className="pb-2 pr-3 text-right font-medium">{copy.cost.cols.labour}</th>
                  <th className="pb-2 text-right font-medium">{copy.cost.cols.total}</th>
                </tr>
              </thead>
              <tbody>
                {e.lines.map((l) => (
                  <LineRow key={`${l.label}-${l.material_id}`} line={l} highlight={l.rate_overridden || overridden.has(l.material_id)} />
                ))}
              </tbody>
            </table>
          ) : (
            <ul>
              {e.lines.map((l) => (
                <LineCard key={`${l.label}-${l.material_id}`} line={l} highlight={l.rate_overridden || overridden.has(l.material_id)} />
              ))}
            </ul>
          )}
          <Totals e={e} />
          {e.openings.length > 0 && <p className="text-xs text-muted-foreground">{copy.cost.openings}</p>}
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 items-start gap-5 lg:grid-cols-2">
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base">{copy.cost.prices}</CardTitle>
            <p className="text-sm text-muted-foreground">{copy.cost.pricesHelp}</p>
            <p className="text-xs text-muted-foreground">
              {copy.cost.pricesShared} {copy.cost.blankIsUsual}
            </p>
          </CardHeader>
          <CardContent className="space-y-4">
            {uniqueMaterials(e.lines).map((l) => {
              const usual = catalogue[l.material_id];
              const d = drafts?.[l.material_id];
              return (
                <div key={l.material_id} className="space-y-2 border-b pb-4 last:border-0 last:pb-0" data-testid={`rates-${l.material_id}`}>
                  <p className="text-sm font-semibold">{l.material_name}</p>
                  <div className="grid gap-3 sm:grid-cols-2">
                    <RateField
                      id={`mat-${l.material_id}`}
                      label={copy.cost.materialPrice(unitWord(l.purchase_unit, 1))}
                      value={d?.material}
                      usual={usual?.material_rate ?? l.material_rate}
                      error={errors[`mat-${l.material_id}`]}
                      onChange={(v) => setRate(l.material_id, "material", v)}
                      onBlur={flush}
                    />
                    <RateField
                      id={`lab-${l.material_id}`}
                      label={copy.cost.labourPrice(copy.cost.units[l.measured_unit])}
                      value={d?.labour}
                      usual={usual?.labour_rate ?? l.labour_rate}
                      error={errors[`lab-${l.material_id}`]}
                      onChange={(v) => setRate(l.material_id, "labour", v)}
                      onBlur={flush}
                    />
                  </div>
                </div>
              );
            })}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base">{copy.cost.extras}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {extras && (
              <>
                <Field id="x-scaffolding" label={copy.cost.scaffolding} hint={copy.cost.scaffoldingNote} error={errors["x-scaffolding"]}>
                  {(a) => (
                    <Input {...a} inputMode="decimal" className="w-36 tabular-nums" value={extras.scaffolding} onChange={(ev) => setExtra("scaffolding", ev.target.value)} onBlur={flush} />
                  )}
                </Field>
                <Field id="x-contingency" label={copy.cost.contingency} error={errors["x-contingency"]}>
                  {(a) => (
                    <Input {...a} inputMode="decimal" className="w-36 tabular-nums" value={extras.contingency} onChange={(ev) => setExtra("contingency", ev.target.value)} onBlur={flush} />
                  )}
                </Field>
                <Field id="x-tax" label={copy.cost.tax} error={errors["x-tax"]}>
                  {(a) => (
                    <Input {...a} inputMode="decimal" className="w-36 tabular-nums" value={extras.tax} onChange={(ev) => setExtra("tax", ev.target.value)} onBlur={flush} />
                  )}
                </Field>
              </>
            )}
            <details className="rounded-lg bg-muted p-3 text-sm">
              <summary className="font-medium">{copy.cost.assumptions}</summary>
              <ul className="mt-2 list-disc space-y-1 pl-5">
                {e.assumptions.map((a) => (
                  <li key={a}>{a}</li>
                ))}
              </ul>
            </details>
            <p className="text-xs text-muted-foreground">{copy.cost.advisory}</p>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardContent className="space-y-5 pt-5 sm:pt-6">
          <div className="flex flex-wrap items-center gap-3">
            {eo.finalised && !eo.stale ? (
              <p className="flex items-center gap-2 font-medium text-success" data-testid="finalised">
                <CheckCircle2 className="size-5" aria-hidden="true" />
                {copy.cost.finalised(eo.version)}
              </p>
            ) : (
              <Button
                size="lg"
                onClick={() => finalise.mutate()}
                disabled={e.provisional || updating || hasErrors}
                pending={finalise.isPending}
              >
                {copy.cost.finalise}
              </Button>
            )}
            {e.provisional && <span className="text-sm text-muted-foreground">{copy.cost.finaliseNeedsSize}</span>}
            {hasErrors && <span className="text-sm font-medium text-destructive">{copy.cost.fixToUpdate}</span>}
          </div>

          <div className="space-y-3 rounded-xl border bg-paper/60 p-4">
            {ready.canDownload ? (
              <p className="flex items-center gap-2 text-sm font-medium text-success">
                <CheckCircle2 className="size-4" aria-hidden="true" />
                {copy.cost.reportReady}
              </p>
            ) : (
              <div id="report-needs">
                <p className="text-sm font-semibold">{copy.cost.reportLocked}</p>
                <ul className="mt-2 space-y-2 text-sm" data-testid="report-checklist">
                  <li className="flex items-start gap-2">
                    {ready.lookAccepted ? (
                      <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-success" aria-hidden="true" />
                    ) : (
                      <Circle className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
                    )}
                    {ready.lookAccepted ? (
                      <span>{copy.cost.needAccept}</span>
                    ) : (
                      <Link to={lookLink} className="font-medium text-primary underline-offset-4 hover:underline">
                        {lookNeed}
                      </Link>
                    )}
                  </li>
                  <li className="flex items-start gap-2">
                    {ready.estimateFinal ? (
                      <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-success" aria-hidden="true" />
                    ) : (
                      <Circle className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
                    )}
                    <span>
                      {ready.estimateFinal ? copy.cost.needFinalise : estimateNeed}
                      {!ready.estimateFinal && !e.provisional && (
                        <span className="block text-xs text-muted-foreground">{copy.cost.finaliseAbove}</span>
                      )}
                    </span>
                  </li>
                </ul>
              </div>
            )}
            <div className="flex flex-wrap items-center gap-3">
              <Button
                size="lg"
                variant={ready.canDownload ? "default" : "outline"}
                disabled={!ready.canDownload || reportBusy}
                aria-describedby={ready.canDownload ? undefined : "report-needs"}
                onClick={onDownload}
              >
                {reportBusy ? (
                  <Loader2 className="animate-spin" aria-hidden="true" />
                ) : ready.canDownload ? (
                  <Download aria-hidden="true" />
                ) : (
                  <Lock aria-hidden="true" />
                )}
                {reportBusy ? copy.cost.preparingReport : copy.cost.download}
              </Button>
              {reportBusy && (
                <span className="text-sm text-muted-foreground" role="status">
                  {copy.cost.preparingHint}
                </span>
              )}
              {!reportBusy && ready.canDownload && (
                <span className="inline-flex items-center gap-1.5 text-xs text-muted-foreground">
                  <FileText className="size-3.5" aria-hidden="true" />
                  {reportFileName(project.name, eo.version)}
                </span>
              )}
            </div>
          </div>
        </CardContent>
      </Card>
      {ready.canDownload && <NextSteps projectId={project.id} designId={active.id} downloaded={downloaded} />}
    </div>,
  );
}
