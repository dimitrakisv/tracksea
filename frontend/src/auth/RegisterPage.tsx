import { useRef, useState, type FormEvent } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";

import { ApiError } from "../api/client";
import { AuthField, AuthStatus } from "./AuthFormElements";
import {
  isValidationError,
  validationFieldErrors,
  type FieldErrors,
} from "./formErrors";
import { useAuth } from "./useAuth";

const REGISTRATION_FIELDS = new Set([
  "display_name",
  "email",
  "password",
] as const);

export function RegisterPage() {
  const auth = useAuth();
  const navigate = useNavigate();
  const [displayName, setDisplayName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const submissionPending = useRef(false);

  if (auth.status === "loading") {
    return <AuthStatus message="Checking your session..." />;
  }
  if (auth.status === "authenticated") {
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
      await auth.register({ display_name: displayName, email, password });
      navigate("/", { replace: true });
    } catch (error) {
      const errors = validationFieldErrors(error, REGISTRATION_FIELDS);
      setFieldErrors(errors);
      setFormError(registrationErrorMessage(error, errors));
      submissionPending.current = false;
      setSubmitting(false);
    }
  }

  return (
    <main className="auth-page">
      <section className="auth-panel" aria-labelledby="register-title">
        <h1 id="register-title">Create your TrackSea account</h1>
        <p className="auth-panel__intro">Start your personal marine journal.</p>

        <form onSubmit={handleSubmit} aria-busy={submitting} noValidate>
          <AuthField
            id="register-display-name"
            name="display_name"
            label="Display name"
            autoComplete="name"
            value={displayName}
            onChange={setDisplayName}
            error={fieldErrors.display_name}
          />
          <AuthField
            id="register-email"
            name="email"
            label="Email"
            type="email"
            autoComplete="email"
            value={email}
            onChange={setEmail}
            error={fieldErrors.email}
          />
          <AuthField
            id="register-password"
            name="password"
            label="Password"
            type="password"
            autoComplete="new-password"
            value={password}
            onChange={setPassword}
            error={fieldErrors.password}
            description="Use at least 15 characters. Spaces and Unicode are allowed; very common passwords may be rejected."
          />

          {formError !== null && (
            <p role="alert" className="auth-error">
              {formError}
            </p>
          )}

          <button type="submit" disabled={submitting}>
            {submitting ? "Creating account..." : "Create account"}
          </button>
        </form>

        <p className="auth-panel__alternate">
          Already have an account? <Link to="/sign-in">Sign in</Link>
        </p>
      </section>
    </main>
  );
}

function registrationErrorMessage(
  error: unknown,
  fieldErrors: FieldErrors,
): string | null {
  if (error instanceof ApiError) {
    if (error.status === 409 && error.code === "account_conflict") {
      return "An account cannot be created with these details.";
    }
    if (error.status === 403 && error.code === "csrf_failed") {
      return "The request could not be verified. Please try again.";
    }
  }
  if (isValidationError(error)) {
    return Object.keys(fieldErrors).length > 0
      ? null
      : "Check the account details and try again.";
  }
  return "Unable to complete the request. Please try again.";
}
