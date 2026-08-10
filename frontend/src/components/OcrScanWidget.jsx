/**
 * OcrScanWidget — mostra il riepilogo dell'ultimo scan OCR Drive/OneDrive.
 *
 * Uso previsto:
 *   - Dashboard principale (grid superiore)
 *   - Pagina Documenti Inbox (sotto l'header)
 *
 * Props:
 *   - variant: "compact" | "full"  (default: "full")
 *   - onClickPending: callback quando l'utente clicca sui "in attesa" (naviga a /documenti-inbox)
 */
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "@/lib/api";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { CloudDownload, CheckCircle2, AlertTriangle, UserPlus, RefreshCw, Sparkles } from "lucide-react";
import { toast } from "sonner";

export default function OcrScanWidget({ variant = "full", onClickPending }) {
    const [summary, setSummary] = useState(null);
    const [scanning, setScanning] = useState(false);

    const load = () => {
        api.get("/librerie/cloud-storage/scan-summary")
            .then((r) => setSummary(r.data))
            .catch(() => setSummary({ error: true }));
    };
    useEffect(() => { load(); }, []);

    const runScanNow = async () => {
        setScanning(true);
        try {
            const fd = new FormData();
            fd.append("provider", "google_drive");
            const r = await api.post("/librerie/cloud-storage/scan-now", fd, {
                timeout: 900_000,
            });
            if (r.data.skipped) {
                toast.info(r.data.reason || "Scan saltato");
            } else {
                toast.success(`Scan completato: ${r.data.letti} letti, ${r.data.abbinati} abbinati, ${r.data.in_attesa} in attesa`);
            }
            load();
        } catch (e) {
            toast.error(e.response?.data?.detail || "Errore scan");
        } finally { setScanning(false); }
    };

    if (!summary || summary.error) {
        return null; // silenzioso se non c'è cloud collegato
    }

    const latest = summary.latest_run;
    const cum = summary.cumulative || {};
    const pending = summary.pending_manual_smistamento || 0;

    // Nessun run mai effettuato → mostra invito
    if (!latest) {
        return (
            <Card className="p-3 bg-slate-50 border-slate-200" data-testid="ocr-widget-empty">
                <div className="flex items-center gap-2 text-xs text-slate-600">
                    <CloudDownload size={14} /> OCR notturno: nessun run ancora eseguito.
                    <Button size="sm" variant="ghost" onClick={runScanNow} disabled={scanning}
                            className="ml-auto text-[11px] h-6"
                            data-testid="btn-scan-now-empty">
                        {scanning ? "Scan…" : "Scansiona INBOX ora"}
                    </Button>
                </div>
            </Card>
        );
    }

    const lastDate = new Date(latest.ended_at || latest.created_at);
    const timeStr = lastDate.toLocaleString("it-IT", {
        day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit",
    });

    if (variant === "compact") {
        return (
            <Card className="p-2.5 border-l-4 border-l-violet-500 bg-gradient-to-r from-violet-50 to-sky-50"
                  data-testid="ocr-widget-compact">
                <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2 text-xs text-slate-700">
                        <CloudDownload size={14} className="text-violet-600" />
                        <span className="font-semibold">OCR {timeStr}:</span>
                        <span>{latest.letti} letti,</span>
                        <span className="text-emerald-700 font-semibold">{latest.abbinati} abbinati,</span>
                        {pending > 0 && (
                            <button onClick={onClickPending}
                                    className="text-amber-700 font-semibold hover:underline"
                                    data-testid="btn-pending-inline">
                                {pending} da smistare
                            </button>
                        )}
                        {latest.anagrafiche_create > 0 && (
                            <span className="text-sky-700"><UserPlus size={11} className="inline" /> {latest.anagrafiche_create} nuove</span>
                        )}
                    </div>
                    <Button size="sm" variant="ghost" onClick={runScanNow} disabled={scanning}
                            className="text-[11px] h-6" data-testid="btn-scan-now-compact">
                        <RefreshCw size={11} className={`mr-1 ${scanning ? "animate-spin" : ""}`} />
                        {scanning ? "…" : "Scan"}
                    </Button>
                </div>
            </Card>
        );
    }

    // Variant "full"
    return (
        <Card className="p-4 bg-gradient-to-br from-white to-violet-50/40 border border-violet-100"
              data-testid="ocr-widget-full">
            <div className="flex items-start justify-between mb-3">
                <div>
                    <div className="text-xs font-semibold uppercase tracking-wider text-violet-700 flex items-center gap-1">
                        <CloudDownload size={12} /> OCR Notturno Google Drive
                    </div>
                    <div className="text-[10px] text-slate-500 mt-0.5">
                        Ultimo scan: <strong>{timeStr}</strong>
                        {latest.manual && <span className="ml-1 italic">(manuale)</span>}
                    </div>
                </div>
                <Button size="sm" onClick={runScanNow} disabled={scanning}
                        className="bg-violet-600 hover:bg-violet-700 h-8 text-[11px]"
                        data-testid="btn-scan-now-full">
                    <RefreshCw size={12} className={`mr-1 ${scanning ? "animate-spin" : ""}`} />
                    {scanning ? "Scansione in corso…" : "Scansiona ora"}
                </Button>
            </div>

            <div className="grid grid-cols-4 gap-2 mb-3">
                <StatBox label="File letti" value={latest.letti} color="slate" icon={CloudDownload} />
                <StatBox label="Abbinati" value={latest.abbinati} color="emerald" icon={CheckCircle2} />
                <StatBox
                    label={pending > 0 ? "Da smistare" : "In attesa"}
                    value={pending || latest.in_attesa}
                    color="amber"
                    icon={AlertTriangle}
                    onClick={pending > 0 ? onClickPending : undefined}
                />
                <StatBox label="Anagraf. create" value={latest.anagrafiche_create || 0} color="sky" icon={UserPlus} />
            </div>

            {pending > 0 && (
                <div className="bg-amber-50 border border-amber-300 rounded p-2 text-[11px] mb-2 flex items-center justify-between">
                    <div className="text-amber-900">
                        <AlertTriangle size={11} className="inline mr-1" />
                        <strong>{pending}</strong> documento/i in attesa di smistamento manuale.
                    </div>
                    <Link to="/documenti-inbox" className="text-amber-800 font-semibold hover:underline text-[11px]"
                          data-testid="link-inbox">
                        Vai a smistarli →
                    </Link>
                </div>
            )}

            <div className="text-[10px] text-slate-500 border-t border-slate-100 pt-2 flex items-center gap-3">
                <span><Sparkles size={9} className="inline text-violet-500" /> Totali storici:</span>
                <span>{cum.runs || 0} run</span>
                <span>·</span>
                <span>{cum.letti || 0} file letti</span>
                <span>·</span>
                <span>{cum.abbinati || 0} abbinati</span>
                <span>·</span>
                <span>{cum.anagrafiche_create || 0} anagrafiche</span>
            </div>
        </Card>
    );
}

const STAT_COLORS = {
    slate: "bg-slate-50 border-slate-200 text-slate-700",
    emerald: "bg-emerald-50 border-emerald-200 text-emerald-700",
    amber: "bg-amber-50 border-amber-200 text-amber-700",
    sky: "bg-sky-50 border-sky-200 text-sky-700",
};

function StatBox({ label, value, color, icon: Icon, onClick }) {
    const Wrap = onClick ? "button" : "div";
    return (
        <Wrap
            onClick={onClick}
            className={`p-2 rounded border ${STAT_COLORS[color]} ${onClick ? "hover:shadow cursor-pointer transition" : ""} text-center`}
            data-testid={`ocr-stat-${label.toLowerCase().replace(/[^a-z]/g, "-")}`}
        >
            <div className="flex items-center justify-center gap-1 text-[9px] uppercase tracking-wider opacity-70">
                <Icon size={10} /> {label}
            </div>
            <div className="text-lg font-bold mt-0.5">{value}</div>
        </Wrap>
    );
}
