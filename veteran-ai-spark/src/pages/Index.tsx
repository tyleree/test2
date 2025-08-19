import { TypingText } from "@/components/TypingText";
import { ChatBot } from "@/components/ChatBot";
import { ThemeToggle } from "@/components/ThemeToggle";
import { useEffect, useState } from "react";

const Index = () => {
  const [showSubtitle, setShowSubtitle] = useState(false);
  const [showChat, setShowChat] = useState(false);

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

  return (
    <div className="min-h-screen flex flex-col items-center justify-center bg-background relative overflow-hidden">
      {/* Theme Toggle */}
      <ThemeToggle />
      {/* Animated background elements */}
      <div className="absolute inset-0 overflow-hidden">
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
      </div>

      {/* Subtle grid pattern overlay */}
      <div className="absolute inset-0 opacity-20" style={{
        backgroundImage: "url('data:image/svg+xml,%3Csvg width=\"60\" height=\"60\" viewBox=\"0 0 60 60\" xmlns=\"http://www.w3.org/2000/svg\"%3E%3Cg fill=\"none\" fill-rule=\"evenodd\"%3E%3Cg fill=\"%23ffffff\" fill-opacity=\"0.02\"%3E%3Cpath d=\"M36 34v-4h-2v4h-4v2h4v4h2v-4h4v-2h-4zm0-30V0h-2v4h-4v2h4v4h2V6h4V4h-4zM6 34v-4H4v4H0v2h4v4h2v-4h4v-2H6zM6 4V0H4v4H0v2h4v4h2V6h4V4H6z\"/%3E%3C/g%3E%3C/g%3E%3C/svg%3E')"
      }}></div>
    </div>
  );
};

export default Index;
