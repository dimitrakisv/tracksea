import "./AuthPage.css";

interface AuthFieldProps {
  id: string;
  name: string;
  label: string;
  type?: "text" | "email" | "password";
  autoComplete: string;
  value: string;
  onChange(value: string): void;
  error?: string;
  description?: string;
}

export function AuthField({
  id,
  name,
  label,
  type = "text",
  autoComplete,
  value,
  onChange,
  error,
  description,
}: AuthFieldProps) {
  const descriptionId =
    description === undefined ? undefined : `${id}-description`;
  const errorId = error === undefined ? undefined : `${id}-error`;
  const describedBy =
    [descriptionId, errorId].filter(Boolean).join(" ") || undefined;

  return (
    <div className="auth-field">
      <label htmlFor={id}>{label}</label>
      <input
        id={id}
        name={name}
        type={type}
        autoComplete={autoComplete}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        required
        aria-invalid={error === undefined ? undefined : true}
        aria-describedby={describedBy}
      />
      {description !== undefined && (
        <p id={descriptionId} className="auth-field__hint">
          {description}
        </p>
      )}
      {error !== undefined && (
        <p id={errorId} className="auth-field__error" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}

export function AuthStatus({
  message,
  isError = false,
}: {
  message: string;
  isError?: boolean;
}) {
  return (
    <main className="auth-status">
      <p role={isError ? "alert" : "status"}>{message}</p>
    </main>
  );
}
