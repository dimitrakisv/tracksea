import { ApiError } from "../api/client";

export type AuthField = "display_name" | "email" | "password";
export type FieldErrors = Partial<Record<AuthField, string>>;

const FIELD_MESSAGES: Record<AuthField, string> = {
  display_name: "Enter a display name between 1 and 80 characters.",
  email: "Enter a valid email address.",
  password: "Check the password and try again.",
};

export function validationFieldErrors(
  error: unknown,
  allowedFields: ReadonlySet<AuthField>,
): FieldErrors {
  if (!(error instanceof ApiError) || error.status !== 422) return {};

  const fieldErrors: FieldErrors = {};
  for (const issue of error.validationIssues ?? []) {
    const field = issue.location.at(-1);
    if (
      typeof field === "string" &&
      isAuthField(field) &&
      allowedFields.has(field)
    ) {
      fieldErrors[field] = FIELD_MESSAGES[field];
    }
  }
  return fieldErrors;
}

export function isValidationError(error: unknown): boolean {
  return error instanceof ApiError && error.status === 422;
}

function isAuthField(value: string): value is AuthField {
  return value === "display_name" || value === "email" || value === "password";
}
