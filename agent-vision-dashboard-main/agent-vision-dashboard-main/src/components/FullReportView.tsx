import { Button } from "@/components/ui/button";
import { Download, FileText, X } from "lucide-react";
import { useAgentStore } from "@/store/agentStore";
import type { ContentReport } from "@/lib/api";
import { exportDocx } from "@/lib/api";
import { ReportCardList } from "@/components/ReportCard";
import { useState } from "react";
import { buildPrintHtml } from "@/components/ReportCard";

function reportTypeLabel(reports: ContentReport[]): string {
  if (!reports.length) return "Extraction Report";
  const ct = (reports[0].content_type || "page").toLowerCase();
  const n = reports.length;
  if (ct === "pdf") return n <= 1 ? "Legal Research Report" : `Precedent Research Report — ${n} Cases`;
  if (ct === "youtube") return "Video Analysis Report";
  if (ct === "qa") return n <= 1 ? "QA Scan Report" : `QA Scan Report — ${n} issues`;
  return n <= 1 ? "Research Report" : `Research Report — ${n} Sources`;
}

function sectionLabel(reports: ContentReport[]): string {
  if (!reports.length) return "Extracted Cases (0)";
  const ct = (reports[0].content_type || "page").toLowerCase();
  const n = reports.length;
  if (ct === "pdf" && n > 1) return `Precedent Research — ${n} Cases`;
  if (ct === "youtube") return "Video Summary";
  if (ct === "qa") return n > 1 ? `QA issues (${n})` : "Issues found";
  return n > 1 ? `Research — ${n} Sources` : "Research";
}

export function FullReportView({ onClose }: { onClose: () => void }) {
  const { task } = useAgentStore();
  const [exporting, setExporting] = useState(false);
  const reports = task?.reports ?? [];
  const sessionId = task?.sessionId ?? "";
  const goal = (task?.taskDescription || "").trim();
  const generatedDate = new Date().toLocaleDateString("en-US", { year: "numeric", month: "long", day: "numeric" });

  const handleOpenFullReport = () => {
    const html = buildPrintHtml(reports, goal);
    const w = window.open("", "_blank");
    if (w) {
      w.document.write(html);
      w.document.close();
      w.focus();
      setTimeout(() => w.print(), 300);
    }
  };

  const handleExportDocx = async () => {
    if (!sessionId) return;
    setExporting(true);
    try {
      const blob = await exportDocx(sessionId);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `report-${sessionId}.docx`;
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      // ignore
    } finally {
      setExporting(false);
    }
  };

  if (reports.length === 0) return null;

  return (
    <div className="flex-1 flex flex-col min-w-0 min-h-0 overflow-hidden bg-background">
      {/* Dark header — same max width as content for aligned edges */}
      <header
        className="shrink-0 py-8 text-center"
        style={{ background: "#0B132B" }}
      >
        <div className="max-w-3xl mx-auto w-full px-6">
          <div className="text-[13px] tracking-widest uppercase text-white/40">
            Intelligence Division
          </div>
          <h1 className="text-3xl font-extrabold text-white tracking-wide mt-2 mb-1">
            Percept
          </h1>
          <p className="text-base text-white/60 mb-4">
            {reportTypeLabel(reports)}
          </p>
          <div className="text-[13px] text-white/35">
            Generated {generatedDate}
          </div>
        </div>
      </header>

      {/* Scrollable body — same width as content for consistent alignment */}
      <div className="flex-1 overflow-y-auto overflow-x-hidden bg-muted/20">
        <div className="max-w-3xl mx-auto w-full px-6 py-6">
          {/* Research Query */}
          {goal && (
            <div className="w-full rounded-lg border border-sky-200 bg-sky-50 dark:bg-sky-950/30 dark:border-sky-800 p-5 mb-6">
              <div className="text-[11px] uppercase tracking-wide text-sky-600 dark:text-sky-400 font-semibold mb-1.5">
                Research Query
              </div>
              <p className="text-[15px] text-sky-900 dark:text-sky-100 font-medium">
                {goal}
              </p>
            </div>
          )}

          {/* Section label */}
          <div className="w-full text-xs uppercase tracking-wide text-muted-foreground font-semibold mb-4">
            {sectionLabel(reports)}
          </div>

          {/* Case cards — full width of container */}
          <div className="w-full">
            <ReportCardList
              reports={reports}
              sessionId={sessionId}
              embedded
            />
          </div>
        </div>
      </div>

      {/* Bottom action bar — aligned with content width */}
      <div className="shrink-0 border-t border-border bg-card/80 backdrop-blur-sm py-3.5">
        <div className="max-w-3xl mx-auto w-full px-6 flex items-center justify-between gap-4">
          <div className="flex items-center gap-2">
            <Button
              size="sm"
              className="gap-2 text-xs bg-[#0B132B] hover:bg-[#1a2744] text-white"
              onClick={handleOpenFullReport}
            >
              <FileText className="h-4 w-4" />
              Open Full Report
            </Button>
            <Button
              size="sm"
              variant="outline"
              className="gap-1.5 text-xs"
              onClick={handleExportDocx}
              disabled={exporting}
            >
              <Download className="h-3 w-3" />
              {exporting ? "..." : "Export .docx"}
            </Button>
          </div>
          <Button
            size="sm"
            variant="ghost"
            className="gap-1.5 text-xs shrink-0"
            onClick={onClose}
          >
            <X className="h-3 w-3" />
            Close Report
          </Button>
        </div>
      </div>
    </div>
  );
}
