import { useState } from "react";
import { motion } from "framer-motion";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { SearchCheck } from "lucide-react";
import { useAgentStore } from "@/store/agentStore";

function normalizeUrl(input: string): string {
  const trimmed = input.trim();
  if (!trimmed) return "";
  if (/^https?:\/\//i.test(trimmed)) return trimmed;
  return `https://${trimmed}`;
}

interface QAScanViewProps {
  onTaskStarted?: () => void;
}

export function QAScanView({ onTaskStarted }: QAScanViewProps) {
  const { setQaScanRequest, isLoading } = useAgentStore();
  const [url, setUrl] = useState("");
  const [error, setError] = useState("");

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    const normalized = normalizeUrl(url);
    if (!normalized) {
      setError("Please enter a URL.");
      return;
    }
    try {
      new URL(normalized);
    } catch {
      setError("Please enter a valid URL.");
      return;
    }
    if (!/^https:\/\//i.test(normalized)) {
      setError("URL must use http or https.");
      return;
    }
    setQaScanRequest(normalized);
    onTaskStarted?.();
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25 }}
      className="p-6 max-w-2xl mx-auto"
    >
      <Card className="card-modern overflow-hidden shadow-sm border-border">
        <CardHeader className="space-y-1 pb-4">
          <CardTitle className="text-lg font-semibold text-foreground flex items-center gap-2">
            <SearchCheck className="h-5 w-5 text-primary" />
            QA Scan
          </CardTitle>
          <CardDescription className="text-sm text-muted-foreground">
            Enter a website URL to run an automated QA scan. The agent will explore the page and report accessibility, link, and UI issues.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="qa-scan-url" className="text-sm font-medium text-foreground">
                Website URL
              </Label>
              <Input
                id="qa-scan-url"
                type="url"
                placeholder="https://example.com"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                className="input-modern w-full"
                disabled={isLoading}
              />
              {error && (
                <p className="text-xs text-destructive" role="alert">
                  {error}
                </p>
              )}
            </div>
            <Button
              type="submit"
              disabled={!url.trim() || isLoading}
              className="w-full gap-2 bg-primary hover:bg-primary/90 text-primary-foreground shadow-sm"
            >
              <SearchCheck className="h-4 w-4" />
              {isLoading ? "Running…" : "Run QA scan"}
            </Button>
          </form>
        </CardContent>
      </Card>
    </motion.div>
  );
}
