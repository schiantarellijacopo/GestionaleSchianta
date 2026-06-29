/**
 * DocumentiMancantiWidget — widget cliccabile che mostra polizze senza PDF,
 * veicoli senza libretto, anagrafiche senza carta d'identità.
 * Cliccando ogni card si apre un dialog con la lista navigabile.
 */
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "@/lib/api";
import { Card } from "@/components/ui/card";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { FileWarning, FileText, IdCard, Car, X, ChevronRight, AlertTriangle } from "lucide-react";

export default function DocumentiMancantiWidget() {
    const [data, setData] = useState(null);
    const [open, setOpen] = useState(null); // 'polizze' | 'veicoli' | 'anagrafiche'

    useEffect(() => {
        api.get("/insights/documenti-mancanti").then((r) => setData(r.data)).catch(() => setData({}));
    }, []);

    if (!data || !data.totali) return null;
    const { polizze, veicoli, anagrafiche } = data.totali;
    const totale = polizze + veicoli + anagrafiche;

    return (
        <Card className="p-4 bg-gradient-to-br from-amber-50 via-white to-rose-50 border-amber-300" data-testid="docs-missing-widget">
            <div className="flex items-center gap-2 mb-3">
                <AlertTriangle className="text-amber-600" size={18} />
                <h3 className="font-semibold text-amber-900 text-sm flex-1">
                    Documenti mancanti
                    {totale > 0 && <span className="ml-2 text-[11px] bg-amber-200 text-amber-900 px-2 py-0.5 rounded-full font-mono">{totale}</span>}
                </h3>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
                <CardMissing label="Polizze senza PDF" count={polizze} icon={FileText} color="rose"
                    onClick={() => polizze > 0 && setOpen("polizze")} testid="missing-polizze-card" />
                <CardMissing label="Veicoli senza libretto" count={veicoli} icon={Car} color="amber"
                    onClick={() => veicoli > 0 && setOpen("veicoli")} testid="missing-veicoli-card" />
                <CardMissing label="Anagrafiche senza C.I." count={anagrafiche} icon={IdCard} color="orange"
                    onClick={() => anagrafiche > 0 && setOpen("anagrafiche")} testid="missing-anagrafiche-card" />
            </div>
            {open && (
                <ListaMancantiDialog tipo={open} data={data} onClose={() => setOpen(null)} />
            )}
        </Card>
    );
}

const COLORS = {
    rose: { bd: "border-rose-300", bg: "bg-rose-50", tx: "text-rose-700", ic: "text-rose-500" },
    amber: { bd: "border-amber-300", bg: "bg-amber-50", tx: "text-amber-700", ic: "text-amber-500" },
    orange: { bd: "border-orange-300", bg: "bg-orange-50", tx: "text-orange-700", ic: "text-orange-500" },
};

function CardMissing({ label, count, icon: Icon, color, onClick, testid }) {
    const c = COLORS[color];
    const dis = count === 0;
    return (
        <button onClick={onClick} disabled={dis} data-testid={testid}
            className={`text-left p-3 rounded border-2 transition-all w-full ${
                dis ? "border-emerald-200 bg-emerald-50 cursor-default opacity-80"
                    : `${c.bd} ${c.bg} hover:shadow-md cursor-pointer hover:scale-[1.02]`
            }`}>
            <div className="flex items-center justify-between">
                <div>
                    <div className={`text-[10px] uppercase tracking-wider ${dis ? "text-emerald-700" : c.tx}`}>{label}</div>
                    <div className={`text-3xl font-bold font-mono ${dis ? "text-emerald-600" : c.tx}`}>
                        {dis ? "✓" : count}
                    </div>
                    <div className="text-[10px] text-slate-500 mt-0.5">
                        {dis ? "Tutto in regola" : "Clicca per vedere"}
                    </div>
                </div>
                <Icon size={28} className={dis ? "text-emerald-500" : c.ic} />
            </div>
        </button>
    );
}

function ListaMancantiDialog({ tipo, data, onClose }) {
    const [q, setQ] = useState("");
    let items = [], title = "", linkBase = "", renderItem = null;

    if (tipo === "polizze") {
        items = data.polizze_senza_allegato || [];
        title = "Polizze senza PDF/contratto allegato";
        renderItem = (p) => (
            <Link to={`/polizze/${p.id}`} key={p.id}
                className="flex items-center gap-2 p-2 hover:bg-rose-50 border-b border-slate-100 group">
                <FileWarning size={14} className="text-rose-500 shrink-0" />
                <div className="flex-1 min-w-0">
                    <div className="font-medium text-sm">N. {p.numero_polizza} · {p.ramo} {p.prodotto && `· ${p.prodotto}`}</div>
                    <div className="text-[11px] text-slate-500 truncate">
                        {p.contraente_nome} {p.targa && <span className="ml-2 text-sky-700 font-mono">[{p.targa}]</span>}
                    </div>
                </div>
                <ChevronRight size={14} className="text-slate-300 group-hover:text-slate-600" />
            </Link>
        );
    } else if (tipo === "veicoli") {
        items = data.veicoli_senza_libretto || [];
        title = "Polizze veicolo senza libretto di circolazione";
        renderItem = (v) => (
            <Link to={`/polizze/${v.id}`} key={v.id}
                className="flex items-center gap-2 p-2 hover:bg-amber-50 border-b border-slate-100 group">
                <Car size={14} className="text-amber-500 shrink-0" />
                <div className="flex-1 min-w-0">
                    <div className="font-medium text-sm">
                        <span className="font-mono text-sky-700">[{v.targa}]</span>
                        {(v.veicolo_marca || v.veicolo_modello) && <span className="ml-1 text-slate-600">{v.veicolo_marca} {v.veicolo_modello}</span>}
                        <span className="ml-2 text-slate-500 text-xs">N. {v.numero_polizza}</span>
                    </div>
                    <div className="text-[11px] text-slate-500 truncate">{v.contraente_nome}</div>
                </div>
                <ChevronRight size={14} className="text-slate-300 group-hover:text-slate-600" />
            </Link>
        );
    } else {
        items = data.anagrafiche_senza_ci || [];
        title = "Anagrafiche senza carta d'identità/patente";
        renderItem = (a) => (
            <Link to={`/anagrafiche/${a.id}`} key={a.id}
                className="flex items-center gap-2 p-2 hover:bg-orange-50 border-b border-slate-100 group">
                <IdCard size={14} className="text-orange-500 shrink-0" />
                <div className="flex-1 min-w-0">
                    <div className="font-medium text-sm">{a.ragione_sociale || `${a.cognome || ""} ${a.nome || ""}`}</div>
                    <div className="text-[11px] text-slate-500 truncate">
                        {a.cellulare && <>📱 {a.cellulare}</>}
                        {a.email && <span className="ml-2">✉ {a.email}</span>}
                    </div>
                </div>
                <ChevronRight size={14} className="text-slate-300 group-hover:text-slate-600" />
            </Link>
        );
    }

    const filtered = q.trim()
        ? items.filter((x) => JSON.stringify(x).toLowerCase().includes(q.toLowerCase()))
        : items;

    return (
        <Dialog open onOpenChange={(o) => !o && onClose()}>
            <DialogContent className="max-w-2xl" data-testid={`missing-dialog-${tipo}`}>
                <DialogHeader>
                    <DialogTitle className="flex items-center justify-between">
                        <span>{title} <span className="text-sm text-slate-500 font-normal">({items.length})</span></span>
                        <button onClick={onClose}><X size={16} /></button>
                    </DialogTitle>
                </DialogHeader>
                <Input value={q} onChange={(e) => setQ(e.target.value)}
                    placeholder="Cerca…" className="mb-2" data-testid="missing-search" />
                <div className="border border-slate-200 rounded max-h-[60vh] overflow-y-auto">
                    {filtered.length === 0 ? (
                        <div className="p-8 text-center text-slate-400 text-sm">Nessun risultato</div>
                    ) : filtered.map(renderItem)}
                </div>
                <div className="text-[11px] text-slate-500 mt-2">
                    💡 Suggerimento: trascina i documenti in <Link to="/documenti-inbox" className="text-sky-700 underline">Documenti Inbox</Link> per archiviarli automaticamente.
                </div>
            </DialogContent>
        </Dialog>
    );
}
