import { Route, Routes } from "react-router-dom";

import { AuthenticatedShell } from "./app/AuthenticatedShell";
import { HomePage } from "./app/HomePage";
import { AuthStatus } from "./auth/AuthFormElements";
import { RegisterPage } from "./auth/RegisterPage";
import { RequireAuth } from "./auth/RequireAuth";
import { SignInPage } from "./auth/SignInPage";
import { ProfilePage } from "./profile/ProfilePage";

export function App() {
  return (
    <Routes>
      <Route path="/register" element={<RegisterPage />} />
      <Route path="/sign-in" element={<SignInPage />} />
      <Route
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
            <AuthenticatedShell />
          </RequireAuth>
        }
      >
        <Route index element={<HomePage />} />
        <Route path="/profile" element={<ProfilePage />} />
      </Route>
    </Routes>
  );
}
