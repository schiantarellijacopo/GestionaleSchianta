/**
 * MiniBilancioTab — Mini Bilancio Periodico & Riclassificazione Automatica.
 * Conto Economico (Ricavi/Costi riclassificati dalla Prima Nota) + Stato
 * Patrimoniale (saldi conti real-time, debiti v/compagnia, ritenute erario).
 * Filtri: Oggi / Mese / Trimestre / Anno / Intervallo. Drill-down per voce.
 * Export PDF / Excel.
 */
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { openPdf } from "@/lib/pdf";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Download, FileSpreadsheet, Loader2 } from "lucide-react";
import { toast } from "sonner";

const fmtEur = (n) => new Intl.NumberFormat("it-IT", { style: "currency", currency: "EUR" }).format(Number(n) || 0);
const today = () => new Date().toISOString().slice(0, 10);

const PRESETS = [
    { key: "oggi", label: "Oggi" },
    { key: "mese", label: "Mese corrente" },
    { key: "trimestre", label: "Trimestre" },
    { key: "anno", label: "Anno in corso" },
    { key: "custom", label: "Personalizzato" },
];

function rangeFor(preset) {
    const now = new Date();
    const y = now.getFullYear();
    const t = today();
    if (preset === "oggi") return [t, t];
    if (preset === "mese") return [`${t.slice(0, 7)}-01`, t];
    if (preset === "trimestre") {
        const q = Math.floor(now.getMonth() / 3) * 3 + 1;
        return [`${y}-${String(q).padStart(2, "0")}-01`, t];
    }
    return [`${y}-01-01`, t];
}

export default function MiniBilancioTab() {
    const [preset, setPreset] = useState("anno");
    const [dal, setDal] = useState(rangeFor("anno")[0]);
    const [al, setAl] = useState(rangeFor("anno")[1]);
    const [data, setData] = useState(null);
    const [drill, setDrill] = useState(null);
    const [exporting, setExporting] = useState(false);

    const pick = (p) => {
        setPreset(p);
        if (p !== "custom") { const [d1, d2] = rangeFor(p); setDal(d1); setAl(d2); }
    };

    useEffect(() => {
        if (!dal || !al) return;
        api.get("/cervello/mini-bilancio", { params: { dal, al } })
            .then((r) => setData(r.data))
            .catch(() => toast.error("Errore caricamento mini bilancio"));
    }, [dal, al]);

    const openDrill = async (row) => {
        setDrill({ voce: row.voce, loading: true, rows: [], totale: 0 });
        try {
            const r = await api.get("/cervello/mini-bilancio/dettaglio", { params: { key: row.key, dal, al } });
            setDrill({ voce: row.voce, loading: false, rows: r.data.rows, totale: r.data.totale });
        } catch { setDrill(null); toast.error("Errore dettaglio"); }
    };

    const exportXlsx = async () => {
        setExporting(true);
        try {
            const r = await api.get("/cervello/mini-bilancio/export", { params: { dal, al, formato: "xlsx" }, responseType: "blob" });
            const url = URL.createObjectURL(r.data);
            const a = document.createElement("a");
            a.href = url; a.download = `mini_bilancio_${dal}_${al}.xlsx`; a.click();
            URL.revokeObjectURL(url);
        } catch { toast.error("Errore export Excel"); }
        setExporting(false);
    };

    if (!data) return <div className="py-10 text-center text-slate-400"><Loader2 className="animate-spin inline mr-2" size={18} />Caricamento…</div>;

    const VoceTable = ({ title, rows, tot, totLabel, color }) => (
        <Card className="p-0 overflow-hidden">
            <div className={`px-3 py-2 text-white text-sm font-semibold ${color}`}>{title}</div>
            <table className="w-full text-sm">
                <tbody>
                    {rows.filter((r) => r.totale !== 0 || r.auto).map((r) => (
                        <tr key={r.key} className="border-b border-slate-100 hover:bg-sky-50 cursor-pointer transition-colors"
                            onClick={() => openDrill(r)} data-testid={`mb-voce-${r.key}`}>
                            <td className="px-3 py-1.5">
                                {r.voce}
                                {r.auto && <span className="ml-1 text-[9px] uppercase text-sky-600 border border-sky-200 rounded px-1">auto</span>}
                            </td>
                            <td className="px-3 py-1.5 text-right font-mono">{fmtEur(r.totale)}</td>
                        </tr>
                    ))}
                    <tr className="bg-slate-50 font-bold">
                        <td className="px-3 py-2">{totLabel}</td>
                        <td className="px-3 py-2 text-right font-mono" data-testid={`mb-${totLabel.toLowerCase().replaceAll(" ", "-")}`}>{fmtEur(tot)}</td>
                    </tr>
                </tbody>
            </table>
        </Card>
    );

    return (
        <div className="space-y-4 pt-3" data-testid="mini-bilancio-tab">
            <div className="flex flex-wrap items-center gap-2">
                {PRESETS.map((p) => (
                    <button key={p.key} onClick={() => pick(p.key)} data-testid={`mb-preset-${p.key}`}
                        className={`px-3 py-1.5 rounded-full text-xs font-medium border transition-colors ${preset === p.key ? "bg-violet-700 text-white border-violet-700" : "bg-white text-slate-600 border-slate-200 hover:bg-slate-50"}`}>
                        {p.label}
                    </button>
                ))}
                {preset === "custom" && (
                    <div className="flex items-center gap-1">
                        <Input type="date" className="h-8 w-36" value={dal} onChange={(e) => setDal(e.target.value)} data-testid="mb-dal" />
                        <span className="text-slate-400 text-xs">→</span>
                        <Input type="date" className="h-8 w-36" value={al} onChange={(e) => setAl(e.target.value)} data-testid="mb-al" />
                    </div>
                )}
                <div className="ml-auto flex gap-2">
                    <Button variant="outline" size="sm" onClick={() => openPdf("/cervello/mini-bilancio/export", { dal, al, formato: "pdf" })} data-testid="mb-export-pdf">
                        <Download size={14} className="mr-1" /> PDF
                    </Button>
                    <Button variant="outline" size="sm" onClick={exportXlsx} disabled={exporting} data-testid="mb-export-xlsx">
                        <FileSpreadsheet size={14} className="mr-1" /> {exporting ? "…" : "Excel"}
                    </Button>
                </div>
            </div>

            <div className="grid lg:grid-cols-3 gap-4">
                {/* A. CONTO ECONOMICO */}
                <div className="lg:col-span-2 space-y-3">
                    <VoceTable title={`RICAVI (Entrate di competenza) — ${dal} → ${al}`} rows={data.ricavi}
                        tot={data.totale_ricavi} totLabel="TOTALE RICAVI" color="bg-emerald-700" />
                    <VoceTable title="COSTI (Uscite di gestione)" rows={data.costi}
                        tot={data.totale_costi} totLabel="TOTALE COSTI" color="bg-rose-700" />
                    <Card className={`p-4 flex items-center justify-between ${data.risultato >= 0 ? "bg-emerald-50 border-emerald-200" : "bg-rose-50 border-rose-200"}`}>
                        <div>
                            <div className="text-[10px] uppercase tracking-wider text-slate-500">Risultato economico (Utile / Perdita)</div>
                            <div className="text-xs text-slate-400">Totale Ricavi − Totale Costi</div>
                        </div>
                        <div className={`text-3xl font-bold font-mono ${data.risultato >= 0 ? "text-emerald-700" : "text-rose-700"}`} data-testid="mb-risultato">
                            {fmtEur(data.risultato)}
                        </div>
                    </Card>
                </div>

                {/* B. STATO PATRIMONIALE */}
                <div className="space-y-3">
                    <Card className="p-0 overflow-hidden">
                        <div className="px-3 py-2 bg-sky-800 text-white text-sm font-semibold">SALDI FINANZIARI (al {al})</div>
                        <table className="w-full text-sm">
                            <tbody>
                                {data.saldi_conti.map((s) => (
                                    <tr key={s.id} className="border-b border-slate-100">
                                        <td className="px-3 py-1.5">{s.nome}</td>
                                        <td className={`px-3 py-1.5 text-right font-mono ${s.saldo < 0 ? "text-rose-600" : "text-slate-800"}`}>{fmtEur(s.saldo)}</td>
                                    </tr>
                                ))}
                                <tr className="bg-slate-50 font-bold">
                                    <td className="px-3 py-2">TOTALE LIQUIDITÀ</td>
                                    <td className="px-3 py-2 text-right font-mono" data-testid="mb-liquidita">{fmtEur(data.totale_liquidita)}</td>
                                </tr>
                            </tbody>
                        </table>
                    </Card>
                    <Card className="p-0 overflow-hidden">
                        <div className="px-3 py-2 bg-violet-800 text-white text-sm font-semibold">DEBITI V/COMPAGNIA (Partite di giro)</div>
                        <table className="w-full text-sm">
                            <tbody>
                                {data.debiti_compagnie.slice(0, 12).map((d, i) => (
                                    <tr key={i} className="border-b border-slate-100">
                                        <td className="px-3 py-1.5">{d.compagnia}</td>
                                        <td className="px-3 py-1.5 text-right font-mono">{fmtEur(d.saldo)}</td>
                                    </tr>
                                ))}
                                <tr className="bg-slate-50 font-bold">
                                    <td className="px-3 py-2">NETTO DA VERSARE</td>
                                    <td className="px-3 py-2 text-right font-mono" data-testid="mb-debiti">{fmtEur(data.totale_debiti_compagnie)}</td>
                                </tr>
                                <tr>
                                    <td className="px-3 py-1.5 text-slate-500">Ritenute d'Acconto &amp; Erario (compagnia)</td>
                                    <td className="px-3 py-1.5 text-right font-mono" data-testid="mb-ritenute-erario">{fmtEur(data.ritenute_erario)}</td>
                                </tr>
                                <tr>
                                    <td className="px-3 py-1.5 text-slate-500">Ritenute d'Acconto v/Collaboratori</td>
                                    <td className="px-3 py-1.5 text-right font-mono" data-testid="mb-ritenute-collaboratori">{fmtEur(data.ritenute_collaboratori || 0)}</td>
                                </tr>
                            </tbody>
                        </table>
                    </Card>
                    <div className="text-[11px] text-slate-400 px-1">
                        💡 Clicca una voce di Ricavo/Costo per il dettaglio delle righe di Prima Nota che la compongono.
                    </div>
                </div>
            </div>

            {/* Drill-down */}
            <Dialog open={!!drill} onOpenChange={(o) => !o && setDrill(null)}>
                <DialogContent className="max-w-2xl" data-testid="mb-drill-dialog">
                    <DialogHeader><DialogTitle>Dettaglio — {drill?.voce}</DialogTitle></DialogHeader>
                    {drill?.loading ? (
                        <div className="py-6 text-center text-slate-400"><Loader2 className="animate-spin inline mr-2" size={16} />Caricamento…</div>
                    ) : (
                        <div className="max-h-[55vh] overflow-y-auto">
                            <table className="w-full text-sm">
                                <thead className="sticky top-0 bg-white">
                                    <tr className="text-left text-xs text-slate-500 border-b">
                                        <th className="py-1 pr-2">Data</th><th className="py-1 pr-2">Descrizione</th>
                                        <th className="py-1 pr-2">Pagamento</th><th className="py-1 text-right">Importo</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {(drill?.rows || []).map((r) => (
                                        <tr key={r.id + r.importo} className="border-b border-slate-50">
                                            <td className="py-1 pr-2 font-mono text-xs">{r.data}</td>
                                            <td className="py-1 pr-2">{r.descrizione}</td>
                                            <td className="py-1 pr-2 text-xs text-slate-500">{r.mezzo_pagamento || "—"}</td>
                                            <td className="py-1 text-right font-mono">{fmtEur(r.importo)}</td>
                                        </tr>
                                    ))}
                                    {(drill?.rows || []).length === 0 && (
                                        <tr><td colSpan={4} className="py-4 text-center text-slate-400">Nessun movimento nel periodo</td></tr>
                                    )}
                                </tbody>
                                <tfoot>
                                    <tr className="font-bold border-t">
                                        <td colSpan={3} className="py-2">Totale</td>
                                        <td className="py-2 text-right font-mono">{fmtEur(drill?.totale)}</td>
                                    </tr>
                                </tfoot>
                            </table>
                        </div>
                    )}
                </DialogContent>
            </Dialog>
        </div>
    );
}
