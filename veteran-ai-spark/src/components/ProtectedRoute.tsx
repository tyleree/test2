import { useAuth } from "@/contexts/AuthContext";
import { Navigate } from "react-router-dom";
import { ReactNode } from "react";

interface ProtectedRouteProps {
  children: ReactNode;
}

export const ProtectedRoute = ({ children }: ProtectedRouteProps) => {
  const { isUnlocked } = useAuth();

  if (!isUnlocked) {
    // Redirect to home page if not unlocked
    return <Navigate to="/" replace />;
  }

  return <>{children}</>;
};

