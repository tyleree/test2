import { TypingText } from "@/components/TypingText";
import { ChatBot } from "@/components/ChatBot";
import { ThemeToggle } from "@/components/ThemeToggle";
import { Button } from "@/components/ui/button";
import { BarChart3, FileText, Lock, Unlock } from "lucide-react";
import { Link } from "react-router-dom";
import { useEffect, useState } from "react";
import { useAuth } from "@/contexts/AuthContext";

const Index = () => {
  const [showSubtitle, setShowSubtitle] = useState(false);
  const [showChat, setShowChat] = useState(false);
  const [showTokenInput, setShowTokenInput] = useState(false);
  const [tokenInput, setTokenInput] = useState("");
  const [tokenError, setTokenError] = useState(false);
  
  const { isUnlocked, unlock } = useAuth();

  useEffect(() => {
    // Show subtitle after main title finishes typing
    const subtitleTimer = setTimeout(() => {
      setShowSubtitle(true);
    }, 2000);

    // Show chat after subtitle appears
    const chatTimer = setTimeout(() => {
      setShowChat(true);
    }, 3500);

    return () => {
      clearTimeout(subtitleTimer);
      clearTimeout(chatTimer);
    };
  }, []);

  const handleTokenSubmit = () => {
    if (unlock(tokenInput)) {
      setShowTokenInput(false);
      setTokenError(false);
      setTokenInput("");
    } else {
      setTokenError(true);
      setTokenInput("");
    }
  };

  return (
    <div className="min-h-screen flex flex-col items-center justify-center bg-background relative overflow-x-hidden">
      {/* Theme Toggle */}
      <ThemeToggle />
      
      {/* Admin unlock button - small and subtle in corner */}
      <div className="absolute top-4 left-4 z-20">
        {!isUnlocked && !showTokenInput && (
          <Button 
            variant="ghost" 
            size="icon" 
            className="opacity-20 hover:opacity-100 transition-opacity"
            onClick={() => setShowTokenInput(true)}
            title="Admin Access"
          >
            <Lock className="h-4 w-4" />
          </Button>
        )}
        
        {showTokenInput && (
          <div className="flex items-center gap-2 bg-background/90 backdrop-blur p-2 rounded-lg border shadow-lg">
            <input
              type="password"
              value={tokenInput}
              onChange={(e) => setTokenInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleTokenSubmit()}
              placeholder="Enter token..."
              className={`w-32 px-2 py-1 text-sm border rounded bg-background ${tokenError ? 'border-red-500' : 'border-input'}`}
              autoFocus
            />
            <Button size="sm" onClick={handleTokenSubmit}>
              <Unlock className="h-3 w-3" />
            </Button>
            <Button size="sm" variant="ghost" onClick={() => { setShowTokenInput(false); setTokenError(false); setTokenInput(""); }}>
              ✕
            </Button>
          </div>
        )}
        
        {isUnlocked && (
          <span className="text-xs text-green-500 flex items-center gap-1">
            <Unlock className="h-3 w-3" /> Admin
          </span>
        )}
      </div>

      {/* Animated background elements */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        <div className="absolute top-1/4 left-1/4 w-64 h-64 bg-primary/10 rounded-full blur-3xl animate-float"></div>
        <div className="absolute bottom-1/4 right-1/4 w-96 h-96 bg-accent/10 rounded-full blur-3xl animate-float" style={{animationDelay: "1s"}}></div>
        <div className="absolute top-1/2 left-1/2 transform -translate-x-1/2 -translate-y-1/2 w-[800px] h-[800px] bg-primary/5 rounded-full blur-3xl animate-pulse"></div>
      </div>

      <div className="relative z-10 text-center space-y-8 px-4 max-w-4xl">
        {/* Main Title */}
        <div className="space-y-4">
          <h1 className="text-6xl md:text-8xl font-black text-foreground tracking-tight">
            <TypingText text="Veterans Benefits AI" speed={150} className="text-transparent bg-clip-text bg-gradient-to-r from-accent to-primary" />
          </h1>
          
          {/* Subtitle */}
          <div className={`transition-all duration-1000 ${showSubtitle ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-4'}`}>
            <p className="text-xl md:text-2xl text-muted-foreground font-medium">
              Advanced RAG based AI that uses the 38 CFR as its source
            </p>
          </div>
        </div>

        {/* Chat Bot */}
        <div className={`transition-all duration-1000 ${showChat ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-8'}`}>
          <div className="flex justify-center">
            <ChatBot />
          </div>
        </div>

        {/* Navigation Links - Only show when unlocked */}
        {isUnlocked && (
          <div className={`transition-all duration-1000 delay-500 ${showChat ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-4'}`}>
            <div className="flex justify-center gap-4 mt-6">
              <Button asChild variant="outline" size="sm" className="text-muted-foreground hover:text-foreground">
                <Link to="/stats">
                  <BarChart3 className="h-4 w-4 mr-2" />
                  View Statistics
                </Link>
              </Button>
              <Button asChild variant="outline" size="sm" className="text-muted-foreground hover:text-foreground">
                <Link to="/whitepaper">
                  <FileText className="h-4 w-4 mr-2" />
                  📄 Technical Whitepaper (LaTeX)
                </Link>
              </Button>
            </div>
          </div>
        )}
      </div>

      {/* Subtle grid pattern overlay */}
      <div className="absolute inset-0 opacity-20" style={{
        backgroundImage: "url('data:image/svg+xml,%3Csvg width=\"60\" height=\"60\" viewBox=\"0 0 60 60\" xmlns=\"http://www.w3.org/2000/svg\"%3E%3Cg fill=\"none\" fill-rule=\"evenodd\"%3E%3Cg fill=\"%23ffffff\" fill-opacity=\"0.02\"%3E%3Cpath d=\"M36 34v-4h-2v4h-4v2h4v4h2v-4h4v-2h-4zm0-30V0h-2v4h-4v2h4v4h2V6h4V4h-4zM6 34v-4H4v4H0v2h4v4h2v-4h4v-2H6zM6 4V0H4v4H0v2h4v4h2V6h4V4H6z\"/%3E%3C/g%3E%3C/g%3E%3C/svg%3E')"
      }}></div>
    </div>
  );
};

export default Index;
