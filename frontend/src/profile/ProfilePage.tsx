import { useRef, useState, type FormEvent } from "react";
import { useOutletContext } from "react-router-dom";

import { ApiError } from "../api/client";
import type { AuthenticatedOutletContext } from "../app/AuthenticatedShell";
import { GoogleSignInButton } from "../auth/GoogleSignInButton";
import { isValidationError, validationFieldErrors } from "../auth/formErrors";
import type { AuthenticationMethod } from "../auth/types";
import "./ProfilePage.css";

const DISPLAY_NAME_FIELD = new Set(["display_name"] as const);
const METHOD_LABELS: Record<AuthenticationMethod, string> = {
  password: "Password",
  google: "Google",
};

export function ProfilePage() {
  const { auth } = useOutletContext<AuthenticatedOutletContext>();
  const [displayName, setDisplayName] = useState(auth.user.display_name);
  const [displayNameError, setDisplayNameError] = useState<
    string | undefined
  >();
  const [formError, setFormError] = useState<string | null>(null);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const submissionPending = useRef(false);
  const canLinkGoogle =
    auth.user.authentication_methods.includes("password") &&
    !auth.user.authentication_methods.includes("google");

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submissionPending.current) return;

    submissionPending.current = true;
    setSubmitting(true);
    setDisplayNameError(undefined);
    setFormError(null);
    setStatusMessage(null);
    try {
      const updatedUser = await auth.updateProfile({
        display_name: displayName,
      });
      setDisplayName(updatedUser.display_name);
      setStatusMessage("Profile updated.");
    } catch (error) {
      const fieldErrors = validationFieldErrors(error, DISPLAY_NAME_FIELD);
      setDisplayNameError(fieldErrors.display_name);
      setFormError(profileErrorMessage(error, fieldErrors.display_name));
    } finally {
      submissionPending.current = false;
      setSubmitting(false);
    }
  }

  return (
    <section className="profile-page" aria-labelledby="profile-title">
      <div className="profile-page__heading">
        <h1 id="profile-title">Profile</h1>
        <p>Manage the account information available in TrackSea.</p>
      </div>

      {statusMessage !== null && (
        <p className="profile-message profile-message--success" role="status">
          {statusMessage}
        </p>
      )}

      <section className="profile-section" aria-labelledby="account-title">
        <h2 id="account-title">Account</h2>
        <dl className="profile-details">
          <div>
            <dt>Display name</dt>
            <dd>{auth.user.display_name}</dd>
          </div>
          <div>
            <dt>Email</dt>
            <dd>{auth.user.email}</dd>
          </div>
          <div>
            <dt>Email verification</dt>
            <dd>{auth.user.email_verified ? "Verified" : "Not verified"}</dd>
          </div>
        </dl>
      </section>

      <section className="profile-section" aria-labelledby="display-name-title">
        <h2 id="display-name-title">Display name</h2>
        <form
          className="profile-form"
          onSubmit={handleSubmit}
          aria-busy={submitting}
          noValidate
        >
          <label htmlFor="profile-display-name">Display name</label>
          <input
            id="profile-display-name"
            name="display_name"
            type="text"
            autoComplete="name"
            required
            value={displayName}
            onChange={(event) => setDisplayName(event.target.value)}
            aria-invalid={displayNameError === undefined ? undefined : true}
            aria-describedby={
              displayNameError === undefined
                ? undefined
                : "profile-display-name-error"
            }
          />
          {displayNameError !== undefined && (
            <p
              id="profile-display-name-error"
              className="profile-message profile-message--error"
              role="alert"
            >
              {displayNameError}
            </p>
          )}
          {formError !== null && (
            <p className="profile-message profile-message--error" role="alert">
              {formError}
            </p>
          )}
          <button type="submit" disabled={submitting}>
            {submitting ? "Saving..." : "Save display name"}
          </button>
        </form>
      </section>

      <section className="profile-section" aria-labelledby="methods-title">
        <h2 id="methods-title">Authentication methods</h2>
        <ul className="profile-methods">
          {auth.user.authentication_methods.map((method) => (
            <li key={method}>{METHOD_LABELS[method]}</li>
          ))}
        </ul>

        {canLinkGoogle && (
          <div
            className="profile-google-link"
            aria-labelledby="link-google-title"
          >
            <h3 id="link-google-title">Link Google</h3>
            <p>Add Google as another way to access this TrackSea account.</p>
            <GoogleSignInButton
              mode="link"
              buttonText="continue_with"
              onSuccess={() => setStatusMessage("Google is now linked.")}
            />
          </div>
        )}
      </section>
    </section>
  );
}

function profileErrorMessage(
  error: unknown,
  displayNameError: string | undefined,
): string | null {
  if (
    error instanceof ApiError &&
    error.status === 403 &&
    error.code === "csrf_failed"
  ) {
    return "The request could not be verified. Please try again.";
  }
  if (isValidationError(error)) {
    return displayNameError === undefined
      ? "Check the display name and try again."
      : null;
  }
  if (
    error instanceof ApiError &&
    error.status === 401 &&
    error.code === "authentication_required"
  ) {
    return null;
  }
  return "Unable to update your profile. Please try again.";
}
