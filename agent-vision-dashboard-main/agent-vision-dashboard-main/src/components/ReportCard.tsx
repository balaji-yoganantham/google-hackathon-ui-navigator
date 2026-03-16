import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Download, ExternalLink, FileText } from "lucide-react";
import type { ContentReport } from "@/lib/api";
import { exportDocx } from "@/lib/api";

const TTS_MESSAGE = "Analysis complete. Your report is ready.";

function speakReady() {
  try {
    if (!window.speechSynthesis) return;
    window.speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(TTS_MESSAGE);
    u.rate = 1.05;
    u.pitch = 1;
    window.speechSynthesis.speak(u);
  } catch {}
}

function reportTypeLabel(reports: ContentReport[]): string {
  if (!reports.length) return "Extraction Report";
  const ct = (reports[0].content_type || "page").toLowerCase();
  const n = reports.length;
  if (ct === "pdf") return n <= 1 ? "Legal Research Report" : `Precedent Research Report — ${n} Cases`;
  if (ct === "youtube") return "Video Analysis Report";
  return n <= 1 ? "Legal Research Report" : `Extracted Cases (${n})`;
}

function sectionLabel(reports: ContentReport[]): string {
  if (!reports.length) return "Extracted Cases (0)";
  const ct = (reports[0].content_type || "page").toLowerCase();
  const n = reports.length;
  if (ct === "pdf" && n > 1) return `Precedent Research — ${n} Cases`;
  if (ct === "youtube") return "Video Summary";
  return `Extracted Cases (${n})`;
}

export function buildPrintHtml(reports: ContentReport[], goal?: string): string {
  const dateStr = new Date().toLocaleDateString("en-US", { year: "numeric", month: "long", day: "numeric" });
  const isMulti = reports.length > 1;
  const caseCardsHtml = reports
    .map(
      (r, i) => {
        const isVideo = r.court?.startsWith("Channel:");
        const pillHtml =
          isMulti
            ? `<div style="margin-bottom:12px;"><span style="font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:1px;padding:4px 12px;border-radius:20px;${i === 0 ? "background:#f0f9ff;color:#0284c7;" : "background:#fffbeb;color:#d97706;"}">${i === 0 ? "Primary Case" : `Precedent ${i}`}</span></div>`
            : "";
        const badgeHtml = isVideo
          ? '<span style="background:#fef2f2;color:#dc2626;font-size:11px;font-weight:600;padding:4px 10px;border-radius:20px;">Video</span>'
          : '<span style="background:#ecfdf5;color:#059669;font-size:11px;font-weight:600;padding:4px 10px;border-radius:20px;">Extracted</span>';
        const meta = [r.court, r.date, r.docket ? `Docket: ${r.docket}` : ""].filter(Boolean).map((x) => `<span style="font-size:13px;color:#64748b;">${escapeHtml(x)}</span>`).join(" ");
        return `
    <div style="background:#fff;border:1px solid #e2e8f0;border-radius:10px;padding:32px;margin-bottom:24px;box-shadow:0 1px 3px rgba(0,0,0,0.08);">
      ${pillHtml}
      <div style="display:flex;align-items:flex-start;justify-content:space-between;margin-bottom:16px;flex-wrap:wrap;gap:8px;">
        <div>
          <h3 style="margin:0 0 6px 0;font-size:18px;font-weight:700;color:#1a202c;">${escapeHtml(r.title || "Report")}</h3>
          <div style="display:flex;gap:16px;flex-wrap:wrap;">${meta}</div>
        </div>
        ${badgeHtml}
      </div>
      <hr style="border:none;border-top:1px solid #f1f5f9;margin:16px 0;" />
      <div style="font-size:14px;line-height:1.75;color:#334155;white-space:pre-wrap;">${escapeHtml(r.content || "")}</div>
    </div>`;
      }
    )
    .join("");

  const goalHtml =
    goal && goal.trim()
      ? `
  <div style="background:#f0f9ff;border:1px solid #bae6fd;border-radius:10px;padding:20px 24px;margin-bottom:32px;">
    <div style="font-size:11px;text-transform:uppercase;letter-spacing:1px;color:#0284c7;font-weight:600;margin-bottom:6px;">Research Query</div>
    <div style="font-size:15px;color:#0c4a6e;font-weight:500;">${escapeHtml(goal.trim())}</div>
  </div>`
      : "";

  return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>UI Navigator Report</title>
<style>
  @media print {
    body { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
    .no-print { display: none !important; }
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: 'Segoe UI', system-ui, -apple-system, sans-serif; background: #f8fafc; color: #1a202c; }
</style>
</head>
<body>
<div style="background:#0B132B;padding:48px 32px 40px;text-align:center;">
  <div style="font-size:13px;letter-spacing:6px;color:rgba(255,255,255,0.4);text-transform:uppercase;margin-bottom:8px;">Intelligence Division</div>
  <h1 style="font-size:36px;font-weight:800;color:#ffffff;letter-spacing:2px;margin-bottom:6px;">UI Navigator</h1>
  <p style="font-size:16px;color:rgba(255,255,255,0.6);margin-bottom:20px;">${escapeHtml(reportTypeLabel(reports))}</p>
  <div style="font-size:13px;color:rgba(255,255,255,0.35);">Generated ${dateStr}</div>
</div>
<div style="max-width:800px;margin:0 auto;padding:32px 24px 64px;">
  ${goalHtml}
  <div style="font-size:12px;text-transform:uppercase;letter-spacing:1px;color:#94a3b8;font-weight:600;margin-bottom:16px;">${escapeHtml(sectionLabel(reports))}</div>
  ${caseCardsHtml}
</div>
<div class="no-print" style="position:fixed;bottom:24px;right:24px;background:#0B132B;color:white;padding:12px 24px;border-radius:8px;font-size:13px;cursor:pointer;box-shadow:0 4px 12px rgba(0,0,0,0.3);" onclick="window.print()">
  Print / Save as PDF
</div>
</body>
</html>`;
}

function escapeHtml(s: string): string {
  const div = document.createElement("div");
  div.textContent = s;
  return div.innerHTML;
}

export function ReportCard({
  report,
  index,
  totalCount = 1,
  onOpenSinglePrint,
}: {
  report: ContentReport;
  index?: number;
  /** Total number of reports (used for Primary vs Precedent pill and per-card Open). */
  totalCount?: number;
  /** When multiple reports, open print view for this single report. */
  onOpenSinglePrint?: (report: ContentReport) => void;
}) {
  const isVideo = report.court?.startsWith("Channel:");
  const pillLabel =
    totalCount > 1 && index != null
      ? index === 0
        ? "Primary Case"
        : `Precedent ${index}`
      : null;
  const pillStyle =
    totalCount > 1 && index != null
      ? index === 0
        ? "bg-sky-100 dark:bg-sky-900/40 text-sky-700 dark:text-sky-300 border-sky-300 dark:border-sky-700"
        : "bg-amber-100 dark:bg-amber-900/40 text-amber-700 dark:text-amber-300 border-amber-300 dark:border-amber-700"
      : "";

  return (
    <div className="w-full rounded-lg border border-border bg-card p-4 space-y-3 shadow-sm">
      {pillLabel && (
        <div>
          <span
            className={`inline-block text-[10px] font-bold uppercase tracking-wider px-3 py-1 rounded-full border ${pillStyle}`}
          >
            {pillLabel}
          </span>
        </div>
      )}
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <h3 className="text-sm font-bold text-foreground leading-tight">
            {report.title || "Report"}
          </h3>
          <div className="flex flex-wrap gap-x-3 gap-y-0.5 mt-1 text-[12px] text-muted-foreground">
            {report.court && <span>{report.court}</span>}
            {report.date && <span>{report.date}</span>}
            {report.docket && <span>Docket: {report.docket}</span>}
          </div>
        </div>
        <span
          className={`shrink-0 text-[11px] font-semibold px-2.5 py-1 rounded-full ${
            isVideo
              ? "bg-red-100 dark:bg-red-900/40 text-red-700 dark:text-red-300"
              : "bg-emerald-100 dark:bg-emerald-900/40 text-emerald-700 dark:text-emerald-300"
          }`}
        >
          {isVideo ? "Video" : "Extracted"}
        </span>
      </div>
      {report.url && (
        <p className="text-[10px] font-mono text-muted-foreground truncate">{report.url}</p>
      )}
      <hr className="border-border" />
      <div className="text-xs text-foreground leading-relaxed whitespace-pre-wrap break-words max-h-[500px] overflow-y-auto">
        {report.content || "No content."}
      </div>
      {onOpenSinglePrint && (
        <div className="pt-2 flex items-center gap-2 border-t border-border mt-3 pt-3">
          <Button
            size="sm"
            variant="ghost"
            className="gap-1.5 text-[11px] h-7 px-2.5 text-muted-foreground hover:text-sky-600 dark:hover:text-sky-400"
            onClick={() => onOpenSinglePrint(report)}
          >
            <FileText className="h-3.5 w-3.5" />
            Open as PDF
          </Button>
        </div>
      )}
    </div>
  );
}

export function ReportCardList({
  reports,
  sessionId,
  embedded = false,
}: {
  reports: ContentReport[];
  sessionId: string;
  /** When true, only render the card list (no Open/Export buttons). */
  embedded?: boolean;
}) {
  const ttsFired = useRef(false);
  const [exporting, setExporting] = useState(false);

  useEffect(() => {
    if (reports.length > 0 && !ttsFired.current) {
      ttsFired.current = true;
      speakReady();
    }
  }, [reports.length]);

  const handleOpenFullReport = () => {
    const html = buildPrintHtml(reports);
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
    <div className="w-full space-y-3">
      {!embedded && (
        <div className="flex items-center gap-2">
          <Button
            size="sm"
            variant="outline"
            className="gap-1.5 text-xs flex-1"
            onClick={handleOpenFullReport}
          >
            <ExternalLink className="h-3 w-3" />
            Open full report
          </Button>
          <Button
            size="sm"
            variant="outline"
            className="gap-1.5 text-xs"
            onClick={handleExportDocx}
            disabled={exporting}
          >
            <Download className="h-3 w-3" />
            {exporting ? "..." : ".docx"}
          </Button>
        </div>
      )}
      <div className="w-full space-y-4">
        {reports.map((r, i) => (
          <ReportCard
            key={i}
            report={r}
            index={i}
            totalCount={reports.length}
            onOpenSinglePrint={(single) => {
              const w = window.open("", "_blank");
              if (w) {
                w.document.write(buildPrintHtml([single]));
                w.document.close();
                w.focus();
                setTimeout(() => w.print(), 300);
              }
            }}
          />
        ))}
      </div>
    </div>
  );
}
