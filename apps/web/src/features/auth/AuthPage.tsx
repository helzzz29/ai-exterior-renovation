import { type FormEvent, useRef, useState } from "react";
import {
  ArrowRight,
  Calculator,
  Check,
  House,
  Layers,
  Lock,
  Mail,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import { Link, Navigate, useLocation, useNavigate } from "react-router";
import { errorMessage } from "@/api/client";
import { useLogin, useMe } from "@/api/hooks";
import { copy } from "@/copy";
import { FacadeArt } from "@/components/FacadeArt";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader } from "@/components/ui/card";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { IS_MOCK, SIGNUP_OPEN } from "@/lib/config";
import { DEMO_HINT } from "./demo";

/** Login and sign-up. App.tsx keys this by mode, so switching between them starts with a clean form. */
export function AuthPage({ mode }: { mode: "login" | "register" }) {
  const me = useMe();
  const login = useLogin(mode);
  const navigate = useNavigate();
  const location = useLocation();
  const [email, setEmail] = useState(IS_MOCK && mode === "login" ? DEMO_HINT.email : "");
  const [password, setPassword] = useState(IS_MOCK && mode === "login" ? DEMO_HINT.password : "");
  const [showPassword, setShowPassword] = useState(false);
  const [errors, setErrors] = useState<{ email?: string; password?: string }>({});
  const [formError, setFormError] = useState<string | null>(null);
  const emailRef = useRef<HTMLInputElement>(null);
  const passwordRef = useRef<HTMLInputElement>(null);
  const isLogin = mode === "login";
  const from = (location.state as { from?: string } | null)?.from ?? "/";

  if (me.data) return <Navigate to={from} replace />;

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    setFormError(null);
    const next: typeof errors = {};
    if (!/^\S+@\S+\.\S+$/.test(email.trim())) next.email = copy.auth.badEmail;
    if (password.length < 8) next.password = copy.auth.shortPassword;
    setErrors(next);
    if (next.email) return emailRef.current?.focus();
    if (next.password) return passwordRef.current?.focus();
    login.mutate(
      { email: email.trim(), password },
      {
        onSuccess: () => navigate(from, { replace: true }),
        onError: (err) => setFormError(errorMessage(err)),
      },
    );
  };

  const featureIcons = [
    <Layers key="f1" className="size-3.5 text-emerald-600 shrink-0" />,
    <Sparkles key="f2" className="size-3.5 text-emerald-600 shrink-0" />,
    <Calculator key="f3" className="size-3.5 text-emerald-600 shrink-0" />,
  ];

  return (
    <main className="h-dvh max-h-dvh overflow-y-auto lg:overflow-hidden bg-slate-50/50 lg:grid lg:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)]">
      {/* Left Column: Architectural Showcase & Value Propositions */}
      <aside className="relative hidden h-full max-h-dvh flex-col justify-between overflow-hidden border-r border-emerald-100/80 bg-gradient-to-br from-emerald-50/80 via-white to-emerald-50/40 p-6 xl:p-8 text-slate-800 lg:flex">
        {/* Subtle grid pattern background */}
        <div
          className="pointer-events-none absolute inset-0 opacity-[0.22] [background-image:radial-gradient(#059669_1px,transparent_1px)] [background-size:24px_24px]"
          aria-hidden="true"
        />

        {/* Brand Header */}
        <div className="relative z-10 flex items-center gap-2.5 shrink-0">
          <div className="flex size-9 items-center justify-center rounded-xl bg-emerald-600 text-white shadow-md shadow-emerald-600/25">
            <House className="size-4.5" aria-hidden="true" />
          </div>
          <div className="flex items-center gap-2">
            <span className="text-lg font-bold tracking-tight text-slate-900">{copy.app.name}</span>
            <span className="inline-flex items-center rounded-full border border-emerald-200/80 bg-emerald-100/60 px-2 py-0.5 text-[11px] font-semibold text-emerald-800">
              {copy.app.tagline}
            </span>
          </div>
        </div>

        {/* Central Architectural Elevation Showcase */}
        <div className="relative z-10 my-auto py-1 shrink min-h-0 flex items-center justify-center">
          <FacadeArt className="mx-auto" />
        </div>

        {/* Value Proposition & Feature Points */}
        <div className="relative z-10 max-w-lg space-y-2.5 shrink-0">
          <div>
            <h2 className="text-base xl:text-lg font-bold leading-tight tracking-tight text-slate-900">
              {copy.auth.sideTitle}
            </h2>
          </div>

          <div className="grid gap-1.5">
            {copy.auth.sidePoints.map((pt, idx) => (
              <div
                key={pt}
                className="flex items-center gap-2.5 rounded-lg border border-emerald-100/90 bg-white/85 px-2.5 py-1.5 shadow-xs backdrop-blur-xs transition hover:border-emerald-200 hover:bg-white"
              >
                <div className="flex size-6 shrink-0 items-center justify-center rounded-md bg-emerald-50 text-emerald-700 border border-emerald-100">
                  {featureIcons[idx] ?? <Check className="size-3 text-emerald-600" />}
                </div>
                <p className="text-xs text-slate-700 leading-tight">
                  <span className="font-semibold text-slate-900 mr-1.5">
                    {idx === 0
                      ? "Structure Detection:"
                      : idx === 1
                        ? "Material Library:"
                        : "Accurate BOQ:"}
                  </span>
                  {pt}
                </p>
              </div>
            ))}
          </div>

          <div className="flex items-center gap-3 pt-1 text-[10.5px] text-slate-400 font-medium border-t border-emerald-100/60">
            <span className="flex items-center gap-1">
              <ShieldCheck className="size-3.5 text-emerald-600" /> Grade-A AI Accuracy
            </span>
            <span>•</span>
            <span>Indian Contractor Rates (INR)</span>
            <span>•</span>
            <span>1-Click PDF & BOQ Export</span>
          </div>
        </div>
      </aside>

      {/* Right Column: Clean White & Emerald Authentication Form */}
      <div className="relative flex h-full max-h-dvh flex-col items-center justify-center overflow-y-auto lg:overflow-hidden bg-white px-4 py-6 sm:px-6 lg:bg-slate-50/40">
        {/* Subtle background glow */}
        <div
          className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_top_right,#ecfdf5,transparent_55%)] opacity-70"
          aria-hidden="true"
        />

        <div className="relative z-10 w-full max-w-md my-auto space-y-4">
          {/* Mobile Header (only visible on small screens) */}
          <div className="flex flex-col items-center gap-1.5 text-center lg:hidden">
            <span className="grid size-10 place-items-center rounded-xl bg-emerald-600 text-white shadow-md shadow-emerald-600/20">
              <House className="size-5" aria-hidden="true" />
            </span>
            <p className="text-xl font-bold tracking-tight text-slate-900">{copy.app.name}</p>
            <p className="max-w-xs text-xs text-slate-500">{copy.app.tagline}</p>
          </div>

          {/* Elevated Auth Card */}
          <Card className="overflow-hidden rounded-2xl border border-emerald-100/90 bg-white shadow-lg shadow-slate-200/50">
            {/* Top decorative emerald gradient bar */}
            <div className="h-1.5 w-full bg-gradient-to-r from-emerald-500 via-teal-500 to-emerald-400" />

            <CardHeader className="p-5 pb-2 sm:p-6 sm:pb-3">
              <div className="mb-1 flex items-center justify-between">
                <span className="inline-flex items-center gap-1 rounded-md bg-emerald-50 px-2 py-0.5 text-[11px] font-semibold text-emerald-800 border border-emerald-200/60">
                  <House className="size-3 text-emerald-600" />
                  Renova Studio
                </span>
                {isLogin && (
                  <button
                    type="button"
                    onClick={() => {
                      setEmail(DEMO_HINT.email);
                      setPassword(DEMO_HINT.password);
                      setErrors({});
                      setFormError(null);
                    }}
                    className="inline-flex items-center gap-1 rounded-md border border-emerald-200 bg-emerald-50/80 px-2 py-0.5 text-[11px] font-semibold text-emerald-700 transition hover:bg-emerald-100/80"
                    title="Fill demo login credentials"
                  >
                    <Sparkles className="size-3 text-emerald-600" />
                    <span>Auto-fill Demo</span>
                  </button>
                )}
              </div>

              <h1 className="text-xl sm:text-2xl font-bold leading-tight tracking-tight text-slate-900">
                {isLogin ? copy.auth.loginTitle : copy.auth.registerTitle}
              </h1>
              <CardDescription className="text-xs sm:text-sm text-slate-500">
                {isLogin ? copy.auth.loginIntro : copy.auth.registerIntro}
              </CardDescription>
            </CardHeader>

            <CardContent className="p-5 pt-0 sm:p-6 sm:pt-0 pb-5 sm:pb-6">
              <form className="space-y-3.5" onSubmit={onSubmit} noValidate>
                <Field
                  id="email"
                  label={copy.auth.email}
                  labelClassName="text-xs font-semibold text-slate-700"
                  error={errors.email}
                >
                  {(f) => (
                    <div className="relative">
                      <Input
                        {...f}
                        ref={emailRef}
                        type="email"
                        autoComplete="email"
                        value={email}
                        placeholder="you@example.com"
                        onChange={(e) => {
                          setEmail(e.target.value);
                          if (errors.email) setErrors((x) => ({ ...x, email: undefined }));
                        }}
                        className="h-10 rounded-xl border-slate-200 pl-9 text-sm focus-visible:border-emerald-500 focus-visible:ring-emerald-500/20"
                        required
                      />
                      <Mail
                        className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-slate-400"
                        aria-hidden="true"
                      />
                    </div>
                  )}
                </Field>

                <Field
                  id="password"
                  label={copy.auth.password}
                  labelClassName="text-xs font-semibold text-slate-700"
                  hint={isLogin ? undefined : copy.auth.passwordHint}
                  error={errors.password}
                >
                  {(f) => (
                    <div className="relative">
                      <Input
                        {...f}
                        ref={passwordRef}
                        type={showPassword ? "text" : "password"}
                        autoComplete={isLogin ? "current-password" : "new-password"}
                        value={password}
                        placeholder="••••••••"
                        onChange={(e) => {
                          setPassword(e.target.value);
                          if (errors.password) setErrors((x) => ({ ...x, password: undefined }));
                        }}
                        className="h-10 rounded-xl border-slate-200 pl-9 pr-16 text-sm focus-visible:border-emerald-500 focus-visible:ring-emerald-500/20"
                        required
                      />
                      <Lock
                        className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-slate-400"
                        aria-hidden="true"
                      />
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        aria-controls="password"
                        className="absolute right-1 top-1/2 h-7 -translate-y-1/2 rounded-lg px-2 text-xs font-medium text-slate-600 hover:bg-slate-100 hover:text-slate-900"
                        onClick={() => setShowPassword((v) => !v)}
                      >
                        {showPassword ? copy.auth.hidePassword : copy.auth.showPassword}
                      </Button>
                    </div>
                  )}
                </Field>

                {formError && <Alert variant="destructive">{formError}</Alert>}

                <Button
                  type="submit"
                  className="h-10.5 w-full rounded-xl bg-emerald-600 text-sm font-semibold text-white shadow-md shadow-emerald-600/20 transition hover:bg-emerald-700 active:bg-emerald-800"
                  size="lg"
                  pending={login.isPending}
                >
                  {login.isPending ? (
                    isLogin ? (
                      copy.auth.loggingIn
                    ) : (
                      copy.auth.registering
                    )
                  ) : (
                    <span className="inline-flex items-center gap-1.5">
                      {isLogin ? copy.auth.loginButton : copy.auth.registerButton}
                      <ArrowRight className="size-4" />
                    </span>
                  )}
                </Button>
              </form>

              {SIGNUP_OPEN ? (
                <div className="mt-4 border-t border-slate-100 pt-3.5 text-center text-xs sm:text-sm">
                  <Link
                    className="font-medium text-emerald-700 transition hover:text-emerald-800 hover:underline underline-offset-4"
                    to={isLogin ? "/register" : "/login"}
                  >
                    {isLogin ? copy.auth.toRegister : copy.auth.toLogin}
                  </Link>
                </div>
              ) : (
                <p className="mt-4 border-t border-slate-100 pt-3.5 text-center text-xs text-slate-500">
                  {copy.auth.inviteOnly}
                </p>
              )}
            </CardContent>
          </Card>

          {/* Bottom Security & Privacy Badge */}
          <div className="flex items-center justify-center gap-1.5 text-center text-[11px] text-slate-400">
            <ShieldCheck className="size-3.5 text-emerald-600" />
            <span>256-bit encrypted • Private project workspace</span>
          </div>
        </div>
      </div>
    </main>
  );
}
