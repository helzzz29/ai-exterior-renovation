import { type FormEvent, useRef, useState } from "react";
import { Check, House } from "lucide-react";
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

  return (
    <main className="min-h-dvh bg-paper lg:grid lg:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)]">
      <aside className="hidden flex-col justify-between border-r border-border/70 bg-[linear-gradient(160deg,var(--accent),var(--paper)_55%)] p-10 text-primary lg:flex xl:p-14">
        <div className="flex items-center gap-2.5 font-semibold tracking-tight text-foreground">
          <span className="grid size-9 place-items-center rounded-xl bg-primary text-primary-foreground shadow-sm">
            <House className="size-5" aria-hidden="true" />
          </span>
          {copy.app.name}
        </div>
        <FacadeArt className="mx-auto max-w-md" />
        <div className="max-w-md space-y-4 text-foreground">
          <p className="text-2xl font-semibold leading-snug tracking-tight">{copy.auth.sideTitle}</p>
          <ul className="space-y-2.5 text-sm text-muted-foreground">
            {copy.auth.sidePoints.map((pt) => (
              <li key={pt} className="flex gap-2.5">
                <Check className="mt-0.5 size-4 shrink-0 text-primary" aria-hidden="true" />
                {pt}
              </li>
            ))}
          </ul>
        </div>
      </aside>

      <div className="grid min-h-dvh place-items-center px-4 py-10 sm:px-6 lg:min-h-0">
        <div className="w-full max-w-md space-y-6">
          <div className="flex flex-col items-center gap-2 text-center lg:hidden">
            <span className="grid size-12 place-items-center rounded-2xl bg-primary text-primary-foreground shadow-raised">
              <House className="size-6" aria-hidden="true" />
            </span>
            <p className="text-xl font-semibold tracking-tight">{copy.app.name}</p>
            <p className="max-w-xs text-sm text-muted-foreground">{copy.app.tagline}</p>
          </div>
          <Card className="shadow-raised">
            <CardHeader className="sm:pt-8">
              <h1 className="text-xl font-semibold leading-tight tracking-tight">
                {isLogin ? copy.auth.loginTitle : copy.auth.registerTitle}
              </h1>
              <CardDescription>{isLogin ? copy.auth.loginIntro : copy.auth.registerIntro}</CardDescription>
            </CardHeader>
            <CardContent className="sm:pb-8">
              <form className="space-y-4" onSubmit={onSubmit} noValidate>
                <Field id="email" label={copy.auth.email} error={errors.email}>
                  {(f) => (
                    <Input
                      {...f}
                      ref={emailRef}
                      type="email"
                      autoComplete="email"
                      value={email}
                      onChange={(e) => {
                        setEmail(e.target.value);
                        if (errors.email) setErrors((x) => ({ ...x, email: undefined }));
                      }}
                      required
                    />
                  )}
                </Field>
                <Field
                  id="password"
                  label={copy.auth.password}
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
                        onChange={(e) => {
                          setPassword(e.target.value);
                          if (errors.password) setErrors((x) => ({ ...x, password: undefined }));
                        }}
                        className="pr-20"
                        required
                      />
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        aria-controls="password"
                        className="absolute top-1/2 right-1 h-8 -translate-y-1/2 px-3 text-xs sm:h-8"
                        onClick={() => setShowPassword((v) => !v)}
                      >
                        {showPassword ? copy.auth.hidePassword : copy.auth.showPassword}
                      </Button>
                    </div>
                  )}
                </Field>
                {formError && <Alert variant="destructive">{formError}</Alert>}
                <Button type="submit" className="w-full" size="lg" pending={login.isPending}>
                  {login.isPending
                    ? isLogin
                      ? copy.auth.loggingIn
                      : copy.auth.registering
                    : isLogin
                      ? copy.auth.loginButton
                      : copy.auth.registerButton}
                </Button>
              </form>
              {SIGNUP_OPEN ? (
                <p className="mt-5 text-center text-sm">
                  <Link className="font-medium text-primary underline-offset-4 hover:underline" to={isLogin ? "/register" : "/login"}>
                    {isLogin ? copy.auth.toRegister : copy.auth.toLogin}
                  </Link>
                </p>
              ) : (
                <p className="mt-5 text-center text-sm text-muted-foreground">{copy.auth.inviteOnly}</p>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </main>
  );
}
