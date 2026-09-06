import { useRef, useState, type FormEvent } from "react";
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom";

import { ApiError } from "../api/client";
import { AuthField, AuthStatus } from "./AuthFormElements";
import { GoogleSignInButton } from "./GoogleSignInButton";
import {
  isValidationError,
  validationFieldErrors,
  type FieldErrors,
} from "./formErrors";
import { useAuth } from "./useAuth";

const SIGN_IN_FIELDS = new Set(["email", "password"] as const);

export function SignInPage() {
  const auth = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const [linkGoogleAfterPasswordSignIn, setLinkGoogleAfterPasswordSignIn] =
    useState(() => hasGoogleLinkIntent(location.state));
  const submissionPending = useRef(false);

  if (auth.status === "loading") {
    return <AuthStatus message="Checking your session..." />;
  }
  if (auth.status === "authenticated") {
    if (linkGoogleAfterPasswordSignIn) {
      return (
        <GoogleLinkContinuation
          onSuccess={() => navigate("/", { replace: true })}
        />
      );
    }
    return <Navigate to="/" replace />;
  }
  if (auth.status === "error") {
    return (
      <AuthStatus message="Unable to determine the current session." isError />
    );
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submissionPending.current) return;

    submissionPending.current = true;
    setSubmitting(true);
    setFormError(null);
    setFieldErrors({});
    try {
      await auth.login({ email, password });
      if (!linkGoogleAfterPasswordSignIn) {
        navigate("/", { replace: true });
      }
    } catch (error) {
      const errors = validationFieldErrors(error, SIGN_IN_FIELDS);
      setFieldErrors(errors);
      setFormError(signInErrorMessage(error, errors));
      submissionPending.current = false;
      setSubmitting(false);
    }
  }

  return (
    <main className="auth-page">
      <section className="auth-panel" aria-labelledby="sign-in-title">
        <h1 id="sign-in-title">Sign in to TrackSea</h1>
        <p className="auth-panel__intro">Continue your marine journal.</p>

        <form onSubmit={handleSubmit} aria-busy={submitting} noValidate>
          <AuthField
            id="sign-in-email"
            name="email"
            label="Email"
            type="email"
            autoComplete="username"
            value={email}
            onChange={setEmail}
            error={fieldErrors.email}
          />
          <AuthField
            id="sign-in-password"
            name="password"
            label="Password"
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={setPassword}
            error={fieldErrors.password}
          />

          {formError !== null && (
            <p role="alert" className="auth-error">
              {formError}
            </p>
          )}

          <button type="submit" disabled={submitting}>
            {submitting ? "Signing in..." : "Sign in"}
          </button>
        </form>

        <div className="auth-divider" aria-hidden="true">
          <span>or</span>
        </div>
        <GoogleSignInButton
          mode="authenticate"
          buttonText="signin_with"
          onSuccess={() => navigate("/", { replace: true })}
          onAccountLinkRequired={() => setLinkGoogleAfterPasswordSignIn(true)}
        />

        {linkGoogleAfterPasswordSignIn && (
          <div className="auth-link-guidance" role="alert">
            <p>
              An existing TrackSea account uses this email. Sign in to your
              existing TrackSea account. If it is a password account, you can
              then link Google.
            </p>
          </div>
        )}

        <p className="auth-panel__alternate">
          Need an account? <Link to="/register">Create one</Link>
        </p>
      </section>
    </main>
  );
}

function GoogleLinkContinuation({ onSuccess }: { onSuccess(): void }) {
  return (
    <main className="auth-page">
      <section className="auth-panel" aria-labelledby="link-google-title">
        <h1 id="link-google-title">Link Google</h1>
        <p className="auth-panel__intro">
          Continue with Google again to provide a fresh credential for linking.
        </p>
        <GoogleSignInButton
          mode="link"
          buttonText="continue_with"
          onSuccess={onSuccess}
        />
        <p className="auth-panel__alternate">
          <Link to="/" replace>
            Continue without linking
          </Link>
        </p>
      </section>
    </main>
  );
}

function hasGoogleLinkIntent(state: unknown): boolean {
  return (
    typeof state === "object" &&
    state !== null &&
    "linkGoogleAfterPasswordSignIn" in state &&
    state.linkGoogleAfterPasswordSignIn === true
  );
}

function signInErrorMessage(
  error: unknown,
  fieldErrors: FieldErrors,
): string | null {
  if (error instanceof ApiError) {
    if (error.status === 401 && error.code === "invalid_credentials") {
      return "Email or password is incorrect.";
    }
    if (error.status === 429 && error.code === "rate_limited") {
      return error.retryAfterSeconds === undefined
        ? "Too many sign-in attempts. Try again later."
        : `Too many sign-in attempts. Try again in approximately ${error.retryAfterSeconds} seconds.`;
    }
    if (error.status === 403 && error.code === "csrf_failed") {
      return "The request could not be verified. Please try again.";
    }
  }
  if (isValidationError(error)) {
    return Object.keys(fieldErrors).length > 0
      ? null
      : "Check the sign-in details and try again.";
  }
  return "Unable to complete the request. Please try again.";
}
