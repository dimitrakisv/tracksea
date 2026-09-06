import { Route, Routes } from "react-router-dom";

import { AuthStatus } from "./auth/AuthFormElements";
import { RegisterPage } from "./auth/RegisterPage";
import { RequireAuth } from "./auth/RequireAuth";
import { SignInPage } from "./auth/SignInPage";
import { SystemStatus } from "./components/SystemStatus";

export function App() {
  return (
    <Routes>
      <Route path="/register" element={<RegisterPage />} />
      <Route path="/sign-in" element={<SignInPage />} />
      <Route
        path="/"
        element={
          <RequireAuth
            loadingFallback={<AuthStatus message="Checking your session..." />}
            errorFallback={
              <AuthStatus
                message="Unable to determine the current session."
                isError
              />
            }
          >
            <SystemStatus />
          </RequireAuth>
        }
      />
    </Routes>
  );
}
