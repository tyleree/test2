import { createContext, useContext, useState, ReactNode } from "react";

const ADMIN_TOKEN = "Cisco123";

// Check auth synchronously to avoid race conditions with ProtectedRoute
const getInitialAuthState = (): boolean => {
  // Check sessionStorage first
  if (typeof window !== 'undefined' && sessionStorage.getItem("admin_unlocked") === "true") {
    return true;
  }
  
  // Check URL parameters for token
  if (typeof window !== 'undefined') {
    const urlParams = new URLSearchParams(window.location.search);
    const tokenFromUrl = urlParams.get("token");
    if (tokenFromUrl === ADMIN_TOKEN) {
      sessionStorage.setItem("admin_unlocked", "true");
      return true;
    }
  }
  
  return false;
};

interface AuthContextType {
  isUnlocked: boolean;
  unlock: (token: string) => boolean;
  lock: () => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider = ({ children }: { children: ReactNode }) => {
  // Initialize synchronously to prevent race condition with ProtectedRoute
  const [isUnlocked, setIsUnlocked] = useState(getInitialAuthState);

  const unlock = (token: string): boolean => {
    if (token === ADMIN_TOKEN) {
      setIsUnlocked(true);
      sessionStorage.setItem("admin_unlocked", "true");
      return true;
    }
    return false;
  };

  const lock = () => {
    setIsUnlocked(false);
    sessionStorage.removeItem("admin_unlocked");
  };

  return (
    <AuthContext.Provider value={{ isUnlocked, unlock, lock }}>
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
};

