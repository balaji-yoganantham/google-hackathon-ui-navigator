import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Bot, LogOut, User } from "lucide-react";

export function DashboardHeader() {
  return (
    <header className="glass-header h-16 border-b border-border flex items-center justify-between px-6 shrink-0 z-50">
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-2">
          <Bot className="h-6 w-6 text-primary" />
          <div>
            <h1 className="text-sm font-semibold text-foreground leading-none">UI Navigator</h1>
            <p className="text-xs text-muted-foreground mt-0.5">Gemini Visual Agent</p>
          </div>
        </div>
        <Badge variant="outline" className="text-[10px] font-mono border-primary/30 text-primary px-1.5 py-0">
          Planner + Executor Agents
        </Badge>
      </div>

      <div className="flex items-center gap-3">
        <Button variant="outline" size="sm" className="gap-2 text-xs">
          <User className="h-3.5 w-3.5" />
          Sign In
        </Button>
      </div>
    </header>
  );
}
