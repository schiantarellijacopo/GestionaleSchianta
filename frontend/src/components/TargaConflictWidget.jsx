/**
 * TargaConflictWidget — quando una polizza/applicazione riporta una TARGA,
 * mostra TUTTE le altre polizze (RCA, Infortuni Conducente, Tutela Legale, …)
 * e applicazioni matricola che riportano la stessa targa. Aiuta a coordinare
 * sostituzioni o cessazioni per non lasciare scoperture.
 */
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "@/lib/api";
import { Card } from "@/components/ui/card";
import { AlertTriangle, Car, ExternalLink, ChevronDown, ChevronUp } from "lucide-react";

export default function TargaConflictWidget({ targa, excludeId, compact = false }) {
    const [data, setData] = useState(null);
    const [expanded, setExpanded] = useState(!compact);

    useEffect(() => {
        if (!targa) return;
        const params = excludeId ? { exclude_id: excludeId } : {};
        api.get(`/polizze/by-targa/${encodeURIComponent(targa.trim().toUpperCase())}`, { params })
            .then((r) => setData(r.data))
            .catch(() => setData(null));
    }, [targa, excludeId]);

    if (!targa || !data) return null;
    const pol = data.polizze || [];
    const app = data.applicazioni || [];
    const tot = pol.length + app.length;
    if (tot === 0) return null;

    return (
        <Card className="border-l-4 border-amber-500 bg-amber-50 p-3 my-3" data-testid="targa-conflict-widget">
            <div className="flex items-center gap-2 cursor-pointer" onClick={() => setExpanded((p) => !p)}>
                <AlertTriangle className="text-amber-600 shrink-0" size={16} />
                <div className="flex-1">
                    <div className="text-sm font-semibold text-amber-900">
                        ⚠ Targa <span className="font-mono bg-amber-200 px-1.5 py-0.5 rounded">{targa}</span> presente su altre {tot} polizz{tot === 1 ? "a" : "e"}
                    </div>
                    <div className="text-[11px] text-amber-700">
                        Ricordati di coordinare modifiche/cessazioni (es. sostituzione veicolo) anche su Infortuni Conducente, Tutela Legale, Kasko ecc.
                    </div>
                </div>
                {expanded ? <ChevronUp size={14} className="text-amber-700" /> : <ChevronDown size={14} className="text-amber-700" />}
            </div>
            {expanded && (
                <div className="mt-2 space-y-1.5">
                    {pol.map((p) => (
                        <Link key={p.id} to={`/polizze/${p.id}`}
                            className="flex items-center gap-2 p-2 bg-white border border-amber-200 rounded hover:bg-sky-50 hover:border-sky-300 group"
                            data-testid={`tcw-pol-${p.id}`}>
                            <Car size={12} className="text-sky-600 shrink-0" />
                            <div className="flex-1 min-w-0">
                                <div className="text-sm font-medium truncate">
                                    <span className="font-mono text-sky-700">N. {p.numero_polizza}</span>
                                    <span className="ml-2 text-slate-700">{p.ramo}</span>
                                    {p.prodotto && <span className="ml-1 text-slate-500 text-xs">· {p.prodotto}</span>}
                                </div>
                                <div className="text-[11px] text-slate-500">
                                    {p.contraente_nome || "—"} · {p.compagnia_nome || "—"} ·
                                    <span className={`ml-1 ${p.stato === "attiva" ? "text-emerald-700" : "text-slate-500"}`}>
                                        {p.stato}
                                    </span>
                                    {(p.scadenza || p.data_scadenza) && <span className="ml-1">· scad. {p.scadenza || p.data_scadenza}</span>}
                                </div>
                            </div>
                            <ExternalLink size={12} className="text-slate-400 group-hover:text-sky-600" />
                        </Link>
                    ))}
                    {app.map((a) => (
                        <Link key={a.id} to={`/polizze/${a.polizza_id}`}
                            className="flex items-center gap-2 p-2 bg-white border border-violet-200 rounded hover:bg-violet-50 group"
                            data-testid={`tcw-app-${a.id}`}>
                            <Car size={12} className="text-violet-600 shrink-0" />
                            <div className="flex-1 min-w-0">
                                <div className="text-sm font-medium truncate">
                                    📋 Applicazione libro matricola
                                    <span className="ml-2 text-slate-700">{a.polizza_numero}</span>
                                    <span className="ml-1 text-slate-500 text-xs">· {a.polizza_ramo}</span>
                                </div>
                                <div className="text-[11px] text-slate-500">
                                    {a.contraente_nome || ""} ·
                                    {a.data_cessazione ? <span className="ml-1 text-rose-700">CESSATA {a.data_cessazione}</span>
                                        : <span className="ml-1 text-emerald-700">ATTIVA</span>}
                                </div>
                            </div>
                            <ExternalLink size={12} className="text-slate-400 group-hover:text-violet-600" />
                        </Link>
                    ))}
                </div>
            )}
        </Card>
    );
}
