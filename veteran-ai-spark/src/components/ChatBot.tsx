import { useState, useRef, useEffect } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Card } from "@/components/ui/card";
import { Send, Bot, User } from "lucide-react";
interface Message {
  id: string;
  content: string;
  isUser: boolean;
  timestamp: Date;
}
export const ChatBot = () => {
  const [messages, setMessages] = useState<Message[]>([{
    id: "1",
    content: "Hello! I'm your Veterans Benefits AI assistant. I can help you understand your benefits using the 38 CFR regulations. What would you like to know?",
    isUser: false,
    timestamp: new Date()
  }]);
  const [inputValue, setInputValue] = useState("");
  const [isTyping, setIsTyping] = useState(false);
  const scrollAreaRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (scrollAreaRef.current) {
      scrollAreaRef.current.scrollTop = scrollAreaRef.current.scrollHeight;
    }
  }, [messages]);
  const handleSendMessage = async () => {
    if (!inputValue.trim()) return;
    const userMessage: Message = {
      id: Date.now().toString(),
      content: inputValue,
      isUser: true,
      timestamp: new Date()
    };
    setMessages(prev => [...prev, userMessage]);
    setInputValue("");
    setIsTyping(true);
    try {
      const res = await fetch('/ask', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt: userMessage.content })
      });

      if (!res.ok) {
        const text = await res.text();
        throw new Error(`HTTP ${res.status}: ${text}`);
      }

      const data = await res.json();
      const botContent = (data && (data.content || data.error)) || 'Sorry, I could not generate a response.';

      const botMessage: Message = {
        id: (Date.now() + 1).toString(),
        content: botContent,
        isUser: false,
        timestamp: new Date()
      };
      setMessages(prev => [...prev, botMessage]);
    } catch (err: any) {
      const errMessage: Message = {
        id: (Date.now() + 2).toString(),
        content: `Error: ${err?.message || 'Unknown error'}`,
        isUser: false,
        timestamp: new Date()
      };
      setMessages(prev => [...prev, errMessage]);
    } finally {
      setIsTyping(false);
    }
  };
  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  };
  return <Card className="w-full max-w-3xl h-[820px] md:max-w-4xl md:h-[900px] bg-card/80 backdrop-blur-sm border-border/50 animate-fadeInUp animate-glow">
      <div className="flex flex-col h-full">
        {/* Header */}
        <div className="flex items-center gap-3 p-4 border-b border-border/50">
          <div className="w-10 h-10 rounded-full bg-primary/20 flex items-center justify-center animate-float">
            <Bot className="w-6 h-6 text-accent" />
          </div>
          <div>
            <h3 className="font-semibold text-foreground">Veterans Benefits AI</h3>
            <p className="text-sm text-muted-foreground">
          </p>
          </div>
        </div>

        {/* Messages */}
        <ScrollArea className="flex-1 p-4" ref={scrollAreaRef}>
          <div className="space-y-4">
            {messages.map(message => <div key={message.id} className={`flex gap-3 animate-fadeInUp ${message.isUser ? "flex-row-reverse" : "flex-row"}`}>
                <div className={`w-8 h-8 rounded-full flex items-center justify-center ${message.isUser ? "bg-accent/20" : "bg-primary/20"}`}>
                  {message.isUser ? <User className="w-4 h-4 text-accent" /> : <Bot className="w-4 h-4 text-accent" />}
                </div>
                <div className={`max-w-[80%] p-3 rounded-lg ${message.isUser ? "bg-primary text-primary-foreground" : "bg-secondary text-secondary-foreground"}`}>
                  {message.isUser ? (
                    <p className="text-sm">{message.content}</p>
                  ) : (
                    <div className="prose prose-sm dark:prose-invert max-w-none overflow-auto max-h-72 md:max-h-96 pr-2">
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>{message.content}</ReactMarkdown>
                    </div>
                  )}
                </div>
              </div>)}
            
            {isTyping && <div className="flex gap-3 animate-fadeInUp">
                <div className="w-8 h-8 rounded-full bg-primary/20 flex items-center justify-center">
                  <Bot className="w-4 h-4 text-accent" />
                </div>
                <div className="bg-secondary p-3 rounded-lg">
                  <div className="flex space-x-1">
                    <div className="w-2 h-2 bg-muted-foreground rounded-full animate-bounce"></div>
                    <div className="w-2 h-2 bg-muted-foreground rounded-full animate-bounce" style={{
                  animationDelay: "0.1s"
                }}></div>
                    <div className="w-2 h-2 bg-muted-foreground rounded-full animate-bounce" style={{
                  animationDelay: "0.2s"
                }}></div>
                  </div>
                </div>
              </div>}
          </div>
        </ScrollArea>

        {/* Input */}
        <div className="p-4 border-t border-border/50">
          <div className="flex gap-2">
            <Input value={inputValue} onChange={e => setInputValue(e.target.value)} onKeyPress={handleKeyPress} placeholder="Ask about your veterans benefits..." className="flex-1 bg-input/50 border-border/50 focus:border-accent" />
            <Button onClick={handleSendMessage} disabled={!inputValue.trim() || isTyping} className="bg-primary hover:bg-primary/80 text-primary-foreground">
              <Send className="w-4 h-4" />
            </Button>
          </div>
        </div>
      </div>
    </Card>;
};