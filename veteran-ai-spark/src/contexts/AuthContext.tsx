import { createContext, useContext, useState, useEffect, ReactNode } from "react";

const ADMIN_TOKEN = "Cisco123";

interface AuthContextType {
  isUnlocked: boolean;
  unlock: (token: string) => boolean;
  lock: () => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider = ({ children }: { children: ReactNode }) => {
  const [isUnlocked, setIsUnlocked] = useState(false);

  useEffect(() => {
    // Check if already unlocked in this session
    const unlocked = sessionStorage.getItem("admin_unlocked") === "true";
    if (unlocked) {
      setIsUnlocked(true);
      return;
    }
    
    // Also check for token in URL parameters (auto-unlock if valid)
    const urlParams = new URLSearchParams(window.location.search);
    const tokenFromUrl = urlParams.get("token");
    if (tokenFromUrl === ADMIN_TOKEN) {
      setIsUnlocked(true);
      sessionStorage.setItem("admin_unlocked", "true");
    }
  }, []);

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

