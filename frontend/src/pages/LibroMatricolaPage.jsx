/**
 * LibroMatricolaPage — pagina standalone del libro matricola con tabella
 * filtrabile, intestazione bloccata in alto, sezione documenti per ogni veicolo
 * (apre dropzone allegati per applicazione_matricola_id).
 */
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api, fmtEur, API_BASE } from "@/lib/api";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { PageHeader, Loading, Empty } from "@/components/Shared";
import { ClipboardList, Car, Search, FileText, Paperclip, X } from "lucide-react";
import { toast } from "sonner";

export default function LibroMatricolaPage() {
    const [items, setItems] = useState(null);
    const [q, setQ] = useState("");
    const [stato, setStato] = useState("all");
    const [polFilter, setPolFilter] = useState("");
    const [docsApp, setDocsApp] = useState(null);

    const load = () => {
        const params = {};
        if (stato !== "all") params.stato = stato;
        if (polFilter) params.polizza_id = polFilter;
        api.get("/libro-matricola", { params }).then((r) => setItems(r.data || []));
    };
    useEffect(() => { load(); /* eslint-disable-next-line */ }, [stato, polFilter]);

    const filtered = useMemo(() => {
        if (!items) return [];
        const term = q.trim().toLowerCase();
        if (!term) return items;
        return items.filter((a) => {
            const blob = `${a.targa || ""} ${a.descrizione_veicolo || ""} ${a.matricola || ""} ${a.telaio || ""} ${a.polizza_numero || ""} ${a.contraente_nome || ""}`.toLowerCase();
            return blob.includes(term);
        });
    }, [items, q]);

    const totali = useMemo(() => {
        if (!items) return { tot: 0, attivi: 0, cessati: 0, premio: 0 };
        return items.reduce((acc, a) => {
            acc.tot++;
            if (a.data_cessazione) acc.cessati++; else acc.attivi++;
            acc.premio += a.premio_lordo || 0;
            return acc;
        }, { tot: 0, attivi: 0, cessati: 0, premio: 0 });
    }, [items]);

    return (
        <div className="space-y-4" data-testid="libro-matricola-page">
            <PageHeader
                title={<span className="flex items-center gap-2"><ClipboardList className="text-violet-600" /> Libro Matricola</span>}
                subtitle="Applicazioni matricola — veicoli/macchinari/dipendenti coperti da polizze a libro"
            />

            {/* KPI */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <Kpi label="Applicazioni totali" value={totali.tot} icon={ClipboardList} color="violet" />
                <Kpi label="Attive" value={totali.attivi} icon={Car} color="emerald" />
                <Kpi label="Cessate" value={totali.cessati} icon={Car} color="rose" />
                <Kpi label="Premio lordo tot." value={fmtEur(totali.premio)} icon={FileText} color="sky" mono />
            </div>

            {/* Filtri */}
            <Card className="p-3 flex flex-wrap items-center gap-2">
                <div className="relative flex-1 min-w-[240px]">
                    <Search size={14} className="absolute left-2 top-2.5 text-slate-400" />
                    <Input value={q} onChange={(e) => setQ(e.target.value)}
                        placeholder="Cerca per targa, telaio, matricola, polizza, cliente…"
                        className="pl-8 text-sm" data-testid="lm-search" />
                </div>
                <Select value={stato} onValueChange={setStato}>
                    <SelectTrigger className="w-40" data-testid="lm-stato"><SelectValue /></SelectTrigger>
                    <SelectContent>
                        <SelectItem value="all">Tutti gli stati</SelectItem>
                        <SelectItem value="attivo">Solo attivi</SelectItem>
                        <SelectItem value="cessato">Solo cessati</SelectItem>
                    </SelectContent>
                </Select>
                <div className="text-xs text-slate-500 ml-auto font-mono">{filtered.length} / {items?.length || 0}</div>
            </Card>

            {/* Tabella con HEADER STICKY */}
            {items === null ? <Loading /> : filtered.length === 0 ? <Empty message="Nessuna applicazione registrata" /> : (
                <Card className="overflow-hidden">
                    <div className="max-h-[70vh] overflow-y-auto relative">
                        <table className="w-full text-xs border-collapse">
                            <thead className="sticky top-0 z-10 bg-slate-100 shadow-sm">
                                <tr>
                                    <th className="px-2 py-2 text-left border-b border-slate-300">Inserim.</th>
                                    <th className="px-2 py-2 text-left border-b border-slate-300">Polizza</th>
                                    <th className="px-2 py-2 text-left border-b border-slate-300">Contraente</th>
                                    <th className="px-2 py-2 text-left border-b border-slate-300">Targa/Matr.</th>
                                    <th className="px-2 py-2 text-left border-b border-slate-300">Descrizione</th>
                                    <th className="px-2 py-2 text-left border-b border-slate-300">Telaio</th>
                                    <th className="px-2 py-2 text-right border-b border-slate-300">Premio</th>
                                    <th className="px-2 py-2 text-left border-b border-slate-300">Stato</th>
                                    <th className="px-2 py-2 text-left border-b border-slate-300">Cessazione</th>
                                    <th className="px-2 py-2 text-center border-b border-slate-300">Documenti</th>
                                </tr>
                            </thead>
                            <tbody>
                                {filtered.map((a) => {
                                    const isCessato = !!a.data_cessazione;
                                    return (
                                        <tr key={a.id} data-testid={`lm-row-${a.id}`}
                                            className={`border-b border-slate-100 hover:bg-sky-50/40 ${isCessato ? "bg-rose-50/30 text-slate-500" : ""}`}>
                                            <td className="px-2 py-1.5 font-mono">{a.data_inserimento || "—"}</td>
                                            <td className="px-2 py-1.5">
                                                <Link to={`/polizze/${a.polizza_id}`} className="text-sky-700 hover:underline font-medium">
                                                    {a.polizza_numero || a.polizza_id?.slice(0, 8)}
                                                </Link>
                                                <div className="text-[10px] text-slate-500">{a.polizza_ramo}</div>
                                            </td>
                                            <td className="px-2 py-1.5">{a.contraente_nome || "—"}</td>
                                            <td className="px-2 py-1.5 font-mono font-semibold text-sky-700">
                                                {a.targa || a.matricola || "—"}
                                            </td>
                                            <td className="px-2 py-1.5">{a.descrizione_veicolo || a.descrizione || "—"}</td>
                                            <td className="px-2 py-1.5 font-mono text-[10px] text-slate-500">{a.telaio || "—"}</td>
                                            <td className="px-2 py-1.5 num text-right font-mono">{fmtEur(a.premio_lordo || 0)}</td>
                                            <td className="px-2 py-1.5">
                                                <span className={`text-[10px] px-1.5 py-0.5 rounded ${isCessato ? "bg-rose-100 text-rose-700" : "bg-emerald-100 text-emerald-700"}`}>
                                                    {isCessato ? "CESSATO" : "ATTIVO"}
                                                </span>
                                            </td>
                                            <td className="px-2 py-1.5 font-mono">{a.data_cessazione || "—"}</td>
                                            <td className="px-2 py-1.5 text-center">
                                                <button onClick={() => setDocsApp(a)}
                                                    className="inline-flex items-center gap-1 text-[10px] px-2 py-1 rounded border border-violet-300 text-violet-700 hover:bg-violet-50"
                                                    data-testid={`lm-docs-${a.id}`}>
                                                    <Paperclip size={11} /> {a.n_allegati || 0}
                                                </button>
                                            </td>
                                        </tr>
                                    );
                                })}
                            </tbody>
                        </table>
                    </div>
                </Card>
            )}

            {/* Dialog documenti per applicazione */}
            {docsApp && (
                <DocsApplicazioneDialog app={docsApp} onClose={() => { setDocsApp(null); load(); }} />
            )}
        </div>
    );
}

const KPI_COLORS = {
    violet: "border-l-violet-500",
    emerald: "border-l-emerald-500",
    rose: "border-l-rose-500",
    sky: "border-l-sky-500",
};

function Kpi({ label, value, icon: Icon, color, mono }) {
    return (
        <Card className={`p-3 border-l-4 ${KPI_COLORS[color]} bg-white`}>
            <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-wider text-slate-500">
                <Icon size={11} /> {label}
            </div>
            <div className={`text-xl font-bold mt-0.5 ${mono ? "font-mono" : ""}`}>{value}</div>
        </Card>
    );
}

function DocsApplicazioneDialog({ app, onClose }) {
    const [items, setItems] = useState(null);
    const [uploading, setUploading] = useState(false);

    const load = () => api.get("/allegati", {
        params: { entita_tipo: "polizza", entita_id: app.polizza_id, applicazione_matricola_id: app.id },
    }).then((r) => setItems(r.data.filter((a) => a.applicazione_matricola_id === app.id || !a.applicazione_matricola_id)));
    useEffect(() => { load(); /* eslint-disable-next-line */ }, [app.id]);

    const upload = async (e) => {
        const file = e.target.files?.[0]; if (!file) return;
        setUploading(true);
        try {
            const fd = new FormData(); fd.append("file", file);
            await api.post(
                `/allegati?entita_tipo=polizza&entita_id=${app.polizza_id}&applicazione_matricola_id=${app.id}`,
                fd, { headers: { "Content-Type": "multipart/form-data" } }
            );
            toast.success("Documento allegato");
            await load();
        } catch (err) { toast.error(err.response?.data?.detail || "Errore"); }
        finally { setUploading(false); e.target.value = ""; }
    };

    const del = async (aid) => {
        if (!window.confirm("Eliminare?")) return;
        try { await api.delete(`/allegati/${aid}`); toast.success("Eliminato"); await load(); }
        catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
    };

    const myDocs = (items || []).filter((a) => a.applicazione_matricola_id === app.id);

    return (
        <Dialog open onOpenChange={(o) => !o && onClose()}>
            <DialogContent className="max-w-2xl" data-testid="lm-docs-dialog">
                <DialogHeader>
                    <DialogTitle className="flex items-center justify-between">
                        <span>
                            <Car className="inline mr-1 text-sky-600" size={16} />
                            Documenti · {app.targa || app.matricola || "—"}
                            <span className="ml-2 text-xs text-slate-500 font-normal">
                                Pol. {app.polizza_numero} · {app.contraente_nome}
                            </span>
                        </span>
                        <button onClick={onClose}><X size={16} /></button>
                    </DialogTitle>
                </DialogHeader>
                <div className="text-xs text-slate-600 bg-amber-50 border border-amber-200 rounded p-2 mb-2">
                    💡 Allega qui libretto di circolazione, fotografie, autorizzazioni e ogni documento specifico del veicolo.
                </div>
                <div className="space-y-2">
                    {myDocs.length === 0 ? (
                        <div className="text-center py-4 text-sm text-slate-400 italic">Nessun documento allegato</div>
                    ) : (
                        myDocs.map((a) => (
                            <div key={a.id} className="flex items-center gap-2 border border-slate-200 rounded p-2 hover:bg-sky-50">
                                <FileText size={14} className="text-sky-600" />
                                <div className="flex-1 min-w-0">
                                    <a href={`${API_BASE}/allegati/${a.id}/download`} target="_blank" rel="noreferrer"
                                        className="text-sm font-medium text-sky-700 hover:underline truncate block">
                                        {a.nome_file}
                                    </a>
                                    <div className="text-[10px] text-slate-500">
                                        {a.categoria && <span className="bg-slate-100 px-1 rounded mr-1">{a.categoria}</span>}
                                        {a.descrizione || ""} · {(a.size / 1024).toFixed(0)} KB
                                    </div>
                                </div>
                                <button onClick={() => del(a.id)} className="text-rose-600 hover:bg-rose-50 p-1 rounded">
                                    <X size={12} />
                                </button>
                            </div>
                        ))
                    )}
                    <label className="block w-full p-3 text-center border-2 border-dashed border-violet-300 rounded cursor-pointer hover:bg-violet-50 text-violet-700 text-sm" data-testid="lm-upload-btn">
                        <Paperclip size={14} className="inline mr-1" />
                        {uploading ? "Caricamento…" : "Allega documento (PDF/JPG)"}
                        <input type="file" hidden onChange={upload} />
                    </label>
                </div>
            </DialogContent>
        </Dialog>
    );
}
