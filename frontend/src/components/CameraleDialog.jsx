/**
 * CameraleDialog — Dati Azienda & Bilancio (OpenAPI.it Visure Camerali + company.openapi.com).
 * Ricerca GRATUITA (denominazione, comune, natura giuridica, documenti richiedibili),
 * bilancio sintetico + completo (a pagamento) e generazione documenti ufficiali (PDF, a pagamento).
 */
import { useEffect, useState } from "react";
import { api, fmtEur } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Building2, Loader2, FileText, TrendingUp, CheckCircle2, Clock, RefreshCw, Download } from "lucide-react";
import { toast } from "sonner";

const API = process.env.REACT_APP_BACKEND_URL;

export default function CameraleDialog({ ana, aid, onClose, onReload }) {
    const [search, setSearch] = useState(null);
    const [loadingSearch, setLoadingSearch] = useState(true);
    const [bilancio, setBilancio] = useState(null);
    const [loadingBil, setLoadingBil] = useState(false);
    const [full, setFull] = useState(false);
    const [genBusy, setGenBusy] = useState(null); // doc_type in corso
    const [anno, setAnno] = useState("");

    const richieste = (ana.openapi_data?.camerale_richieste || []).slice().reverse();

    useEffect(() => {
        api.get(`/openapi-it/camerale/${aid}/search`)
            .then((r) => setSearch(r.data))
            .catch((e) => toast.error(e.response?.data?.detail || "Azienda non trovata"))
            .finally(() => setLoadingSearch(false));
    }, [aid]);

    const caricaBilancio = async (isFull) => {
        setLoadingBil(true);
        try {
            const r = await api.get(`/openapi-it/camerale/${aid}/bilancio`, { params: { full: isFull } });
            setBilancio(r.data);
            setFull(isFull);
            onReload?.();
        } catch (e) {
            toast.error(e.response?.data?.detail || "Bilancio non disponibile");
        } finally { setLoadingBil(false); }
    };

    const generaDoc = async (doc) => {
        if (!window.confirm(`Generare "${doc.label}"?\nCosto ${fmtEur(doc.prezzo)} (se già presente per questa azienda, viene riscaricato GRATIS).`)) return;
        setGenBusy(doc.doc_type);
        try {
            const body = { doc_type: doc.doc_type };
            if (doc.doc_type === "bilancio-ottico" && anno) body.anno = anno;
            const r = await api.post(`/openapi-it/camerale/${aid}/documento`, body);
            if (r.data.riusato) toast.success(`${doc.label}: già disponibile → riscaricato GRATIS`);
            else if (r.data.allegato_id) toast.success(`${doc.label}: PDF salvato negli Allegati`);
            else toast.info(`${doc.label}: richiesta inviata (${r.data.stato})`);
            onReload?.();
        } catch (e) {
            toast.error(e.response?.data?.detail || "Errore generazione");
        } finally { setGenBusy(null); }
    };

    const refresh = async (rid) => {
        try {
            const r = await api.post(`/openapi-it/camerale/${aid}/refresh/${rid}`);
            if (r.data.allegato_id) toast.success("PDF pronto e salvato negli Allegati");
            else toast.info(`Stato: ${r.data.stato}`);
            onReload?.();
        } catch { toast.error("Errore aggiornamento"); }
    };

    const Riga = ({ label, value }) => value ? (
        <div className="flex justify-between gap-3 text-xs py-0.5 border-b border-slate-100">
            <span className="text-slate-500">{label}</span>
            <span className="font-medium text-slate-800 text-right">{value}</span>
        </div>
    ) : null;

    return (
        <Dialog open onOpenChange={(o) => !o && onClose()}>
            <DialogContent className="max-w-3xl max-h-[88vh] overflow-y-auto" data-testid="camerale-dialog">
                <DialogHeader>
                    <DialogTitle className="flex items-center gap-2">
                        <Building2 size={18} className="text-sky-700" /> Dati Azienda & Bilancio
                    </DialogTitle>
                    <DialogDescription>
                        Ricerca camerale gratuita, bilanci e documenti ufficiali dell'azienda.
                    </DialogDescription>
                </DialogHeader>

                {loadingSearch ? (
                    <div className="py-10 text-center text-slate-400"><Loader2 className="animate-spin inline" /> Ricerca in corso…</div>
                ) : !search ? (
                    <div className="text-sm text-slate-500 bg-slate-50 border border-dashed rounded p-6 text-center">
                        Azienda non trovata nel registro imprese.
                    </div>
                ) : (
                    <div className="space-y-4">
                        {/* Dati azienda (gratis) */}
                        <div className="border border-slate-200 rounded p-3">
                            <div className="flex items-center justify-between mb-1">
                                <div className="font-semibold text-sm">{search.denominazione}</div>
                                <span className="text-[10px] bg-emerald-100 text-emerald-700 px-2 py-0.5 rounded-full">Ricerca gratuita</span>
                            </div>
                            <Riga label="Comune" value={search.comune} />
                            <Riga label="Natura giuridica" value={search.natura_giuridica} />
                            <Riga label="P.IVA / CF" value={search.cf_piva} />
                        </div>

                        {/* Bilancio */}
                        <div className="border border-slate-200 rounded p-3">
                            <div className="flex items-center justify-between mb-2">
                                <div className="font-medium text-sm flex items-center gap-1"><TrendingUp size={14} className="text-violet-600" /> Dati di bilancio</div>
                                {!bilancio && (
                                    <Button size="sm" onClick={() => caricaBilancio(false)} disabled={loadingBil}
                                        className="bg-violet-600 hover:bg-violet-700 h-7 text-xs" data-testid="camerale-load-bilancio">
                                        {loadingBil ? <Loader2 size={12} className="animate-spin mr-1" /> : null}
                                        Carica bilancio (a pagamento)
                                    </Button>
                                )}
                            </div>
                            {bilancio && (
                                <>
                                    <div className="grid grid-cols-2 gap-x-4 mb-2">
                                        <Riga label="Ragione sociale" value={bilancio.ragione_sociale} />
                                        <Riga label="Forma giuridica" value={bilancio.forma_giuridica} />
                                        <Riga label="ATECO" value={bilancio.ateco ? `${bilancio.ateco} — ${bilancio.ateco_descrizione || ""}` : null} />
                                        <Riga label="REA / CCIAA" value={[bilancio.rea, bilancio.cciaa].filter(Boolean).join(" / ")} />
                                        <Riga label="PEC" value={bilancio.pec} />
                                        <Riga label="Indirizzo" value={bilancio.indirizzo} />
                                    </div>
                                    {bilancio.bilanci?.length > 0 && (
                                        <table className="w-full text-xs mt-1">
                                            <thead className="text-[10px] uppercase text-slate-500 border-b">
                                                <tr><th className="text-left py-1">Anno</th><th className="text-right">Fatturato</th><th className="text-right">Patr. Netto</th><th className="text-right">Dip.</th></tr>
                                            </thead>
                                            <tbody>
                                                {bilancio.bilanci.slice(0, 6).map((b) => (
                                                    <tr key={b.anno} className="border-b border-slate-100">
                                                        <td className="py-1 font-medium">{b.anno}</td>
                                                        <td className="text-right num">{b.fatturato != null ? fmtEur(b.fatturato) : "—"}</td>
                                                        <td className={`text-right num ${b.patrimonio_netto < 0 ? "text-rose-600" : ""}`}>{b.patrimonio_netto != null ? fmtEur(b.patrimonio_netto) : "—"}</td>
                                                        <td className="text-right num">{b.dipendenti ?? "—"}</td>
                                                    </tr>
                                                ))}
                                            </tbody>
                                        </table>
                                    )}
                                    {!full ? (
                                        <Button size="sm" variant="outline" className="mt-2 h-7 text-xs" onClick={() => caricaBilancio(true)} disabled={loadingBil} data-testid="camerale-load-full">
                                            {loadingBil ? <Loader2 size={12} className="animate-spin mr-1" /> : null}
                                            Bilancio completo + indici (a pagamento)
                                        </Button>
                                    ) : (
                                        <div className="mt-3 space-y-2">
                                            {bilancio.indici?.redditivita && (
                                                <div className="text-xs">
                                                    <div className="font-medium text-slate-700 mb-1">Indici di redditività</div>
                                                    <div className="grid grid-cols-3 gap-2">
                                                        {Object.entries(bilancio.indici.redditivita).map(([k, v]) => (
                                                            <div key={k} className="bg-slate-50 rounded p-1.5"><div className="text-[10px] text-slate-500 uppercase">{k}</div><div className="font-semibold num">{v}</div></div>
                                                        ))}
                                                    </div>
                                                </div>
                                            )}
                                            {bilancio.amministratori?.length > 0 && (
                                                <div className="text-xs">
                                                    <div className="font-medium text-slate-700 mb-1">Amministratori</div>
                                                    {bilancio.amministratori.map((m, i) => (
                                                        <div key={i} className="flex justify-between border-b border-slate-100 py-0.5">
                                                            <span>{m.nome} {m.legale_rappresentante && <span className="text-[10px] bg-sky-100 text-sky-700 px-1 rounded">LR</span>}</span>
                                                            <span className="text-slate-500">{m.ruoli}</span>
                                                        </div>
                                                    ))}
                                                </div>
                                            )}
                                            {bilancio.soci?.length > 0 && (
                                                <div className="text-xs">
                                                    <div className="font-medium text-slate-700 mb-1">Soci</div>
                                                    {bilancio.soci.map((s, i) => (
                                                        <div key={i} className="flex justify-between border-b border-slate-100 py-0.5">
                                                            <span>{s.nome}</span><span className="text-slate-500">{s.quota != null ? `${s.quota}%` : ""} {s.tipo || ""}</span>
                                                        </div>
                                                    ))}
                                                </div>
                                            )}
                                        </div>
                                    )}
                                </>
                            )}
                        </div>

                        {/* Documenti ufficiali (a pagamento) */}
                        <div className="border border-slate-200 rounded p-3">
                            <div className="font-medium text-sm flex items-center gap-1 mb-2"><FileText size={14} className="text-amber-600" /> Documenti ufficiali (PDF, a pagamento)</div>
                            {search.documenti_disponibili?.some((d) => d.doc_type === "bilancio-ottico") && (
                                <div className="flex items-center gap-2 mb-2 text-xs">
                                    <span className="text-slate-500">Bilancio ottico anno:</span>
                                    <Input value={anno} onChange={(e) => setAnno(e.target.value)} placeholder="ultimo" className="h-7 w-24 text-xs" data-testid="camerale-anno" />
                                </div>
                            )}
                            <div className="grid grid-cols-1 sm:grid-cols-2 gap-1.5">
                                {(search.documenti_disponibili || []).map((doc) => (
                                    <div key={doc.doc_type} className="flex items-center justify-between border border-slate-200 rounded px-2.5 py-2 text-sm">
                                        <div>
                                            <div>{doc.label}</div>
                                            <div className="text-[11px] text-emerald-700 font-medium">{fmtEur(doc.prezzo)}</div>
                                        </div>
                                        <Button size="sm" variant="outline" className="h-7 text-xs" onClick={() => generaDoc(doc)} disabled={genBusy === doc.doc_type}
                                            data-testid={`camerale-gen-${doc.doc_type}`}>
                                            {genBusy === doc.doc_type ? <Loader2 size={12} className="animate-spin" /> : "Genera"}
                                        </Button>
                                    </div>
                                ))}
                            </div>
                        </div>

                        {/* Storico documenti richiesti */}
                        {richieste.length > 0 && (
                            <div className="border-t pt-2">
                                <div className="text-[10px] uppercase tracking-wider text-slate-500 font-semibold mb-1">Documenti richiesti</div>
                                <div className="space-y-1 max-h-40 overflow-y-auto">
                                    {richieste.map((r) => (
                                        <div key={r.id} className="flex items-center gap-2 text-xs border border-slate-200 rounded px-2 py-1.5">
                                            {r.allegato_id ? <CheckCircle2 size={13} className="text-emerald-600" /> : <Clock size={13} className="text-amber-600" />}
                                            <span className="font-medium truncate flex-1">{r.nome}</span>
                                            <span className="text-slate-500">{r.allegato_id ? (r.riusato ? "PDF (riuso gratis)" : "PDF salvato") : r.stato}</span>
                                            {r.allegato_id ? (
                                                <a href={`${API}/api/allegati/${r.allegato_id}/download`} target="_blank" rel="noreferrer" className="text-sky-600" title="Scarica">
                                                    <Download size={12} />
                                                </a>
                                            ) : (
                                                <Button size="sm" variant="ghost" className="h-6 px-1.5" onClick={() => refresh(r.id)} data-testid={`camerale-refresh-${r.id}`}>
                                                    <RefreshCw size={11} />
                                                </Button>
                                            )}
                                        </div>
                                    ))}
                                </div>
                            </div>
                        )}
                    </div>
                )}

                <DialogFooter>
                    <Button variant="outline" onClick={onClose}>Chiudi</Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}
