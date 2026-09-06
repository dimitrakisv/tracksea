import type { ReactNode } from "react";
import { Navigate } from "react-router-dom";

import { useAuth } from "./useAuth";

interface RequireAuthProps {
  children: ReactNode;
  loadingFallback?: ReactNode;
  errorFallback?: ReactNode;
}

export function RequireAuth({
  children,
  loadingFallback = null,
  errorFallback = null,
}: RequireAuthProps) {
  const auth = useAuth();
  if (auth.status === "loading") return loadingFallback;
  if (auth.status === "anonymous") {
    return <Navigate to="/sign-in" replace />;
  }
  if (auth.status === "error") return errorFallback;
  return children;
}
