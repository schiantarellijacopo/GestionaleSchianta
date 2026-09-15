import { useEffect, useState, useCallback } from "react";
import { Link } from "react-router-dom";
import { api, fmtEur, fmtDate, API_BASE } from "@/lib/api";
import { PageHeader, Loading } from "@/components/Shared";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
    Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from "@/components/ui/dialog";
import RegolazionePremioDialog from "@/components/RegolazionePremioDialog";
import { Mail, Calculator, Receipt, ExternalLink, AlertCircle, Download, CheckCircle2, Paperclip, Trash2, Upload, Loader2, FileText } from "lucide-react";
import { toast } from "sonner";

const STATI = [
    { key: "", label: "Tutte" },
    { key: "da_richiedere", label: "Da richiedere" },
    { key: "lettera_inviata", label: "Lettera inviata" },
    { key: "dati_ricevuti", label: "Dati ricevuti" },
    { key: "calcolata", label: "Calcolata" },
    { key: "titolo_generato", label: "Titolo generato" },
    { key: "chiusa", label: "Chiuse" },
];

const STATO_BADGE = {
    da_richiedere: "bg-slate-100 text-slate-700 border-slate-200",
    lettera_inviata: "bg-sky-100 text-sky-700 border-sky-200",
    dati_ricevuti: "bg-amber-100 text-amber-700 border-amber-200",
    calcolata: "bg-violet-100 text-violet-700 border-violet-200",
    titolo_generato: "bg-emerald-100 text-emerald-700 border-emerald-200",
    chiusa: "bg-slate-200 text-slate-500 border-slate-300",
};

const STATO_LABEL = Object.fromEntries(STATI.filter((s) => s.key).map((s) => [s.key, s.label]));

function StatCard({ label, value, tone }) {
    return (
        <Card className="p-4 border-slate-200" data-testid={`reg-stat-${label}`}>
            <div className="text-xs uppercase tracking-wide text-slate-500">{label}</div>
            <div className={`text-2xl font-bold mt-1 ${tone || "text-slate-800"}`}>{value}</div>
        </Card>
    );
}

export default function RegolazionePremio() {
    const [rows, setRows] = useState(null);
    const [stats, setStats] = useState(null);
    const [filtro, setFiltro] = useState("");
    const [calcolaRow, setCalcolaRow] = useState(null);
    const [letteraRow, setLetteraRow] = useState(null);
    const [titoloRow, setTitoloRow] = useState(null);
    const [docRow, setDocRow] = useState(null);

    const load = useCallback(() => {
        const params = filtro ? { stato: filtro } : {};
        Promise.all([
            api.get("/regolazione-premio", { params }),
            api.get("/regolazione-premio/stats"),
        ]).then(([r, s]) => { setRows(r.data || []); setStats(s.data); });
    }, [filtro]);

    useEffect(() => { load(); }, [load]);

    if (rows === null) return <Loading />;

    return (
        <div data-testid="regolazione-premio-page">
            <PageHeader
                title="Regolazione Premio"
                subtitle="Polizze con premio variabile a consuntivo · scadenze e invio richieste dati"
            />

            {stats && (
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-5">
                    <StatCard label="Polizze totali" value={stats.totale} />
                    <StatCard label="Da inviare oggi" value={stats.da_inviare} tone={stats.da_inviare > 0 ? "text-rose-600" : "text-slate-800"} />
                    <StatCard label="Titoli generati" value={stats.per_stato?.titolo_generato || 0} tone="text-emerald-600" />
                    <StatCard label="Dovuto totale" value={fmtEur(stats.dovuto_totale)} tone="text-violet-700" />
                </div>
            )}

            <div className="flex flex-wrap gap-2 mb-4">
                {STATI.map((s) => (
                    <button
                        key={s.key || "all"}
                        onClick={() => setFiltro(s.key)}
                        className={`px-3 py-1.5 rounded-full text-xs font-medium border transition-colors ${filtro === s.key ? "bg-violet-700 text-white border-violet-700" : "bg-white text-slate-600 border-slate-200 hover:bg-slate-50"}`}
                        data-testid={`reg-filter-${s.key || "all"}`}
                    >
                        {s.label}
                    </button>
                ))}
            </div>

            <Card className="border-slate-200 overflow-hidden">
                <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                        <thead className="bg-slate-50 border-b border-slate-200 text-left text-xs text-slate-500 uppercase tracking-wide">
                            <tr>
                                <th className="px-3 py-2.5">Cliente</th>
                                <th className="px-3 py-2.5">Polizza</th>
                                <th className="px-3 py-2.5">Compagnia</th>
                                <th className="px-3 py-2.5">Scadenza</th>
                                <th className="px-3 py-2.5">Invio previsto</th>
                                <th className="px-3 py-2.5">Stato</th>
                                <th className="px-3 py-2.5 text-right">Dovuto</th>
                                <th className="px-3 py-2.5 text-right">Azioni</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-100">
                            {rows.length === 0 && (
                                <tr><td colSpan={8} className="px-3 py-10 text-center text-slate-400 italic">Nessuna polizza soggetta a regolazione premio</td></tr>
                            )}
                            {rows.map((r) => (
                                <tr key={r.polizza_id} className={r.da_inviare ? "bg-rose-50/40" : ""} data-testid={`reg-row-${r.polizza_id}`}>
                                    <td className="px-3 py-2.5">
                                        <Link to={`/anagrafiche/${r.contraente_id}`} className="font-medium text-slate-800 hover:text-violet-700">
                                            {r.contraente_nome}
                                        </Link>
                                        {!r.contraente_email && <div className="text-[10px] text-amber-600 flex items-center gap-0.5"><AlertCircle size={10} /> no email</div>}
                                    </td>
                                    <td className="px-3 py-2.5">
                                        <Link to={`/polizze/${r.polizza_id}`} className="text-sky-700 hover:underline font-mono text-xs">{r.numero_polizza}</Link>
                                        <div className="text-[10px] text-slate-500">{r.ramo} {r.tasso ? `· ${r.tasso}%` : ""}</div>
                                    </td>
                                    <td className="px-3 py-2.5 text-slate-600">{r.compagnia}</td>
                                    <td className="px-3 py-2.5 text-slate-600">{fmtDate(r.scadenza)}</td>
                                    <td className="px-3 py-2.5">
                                        <span className={r.da_inviare ? "text-rose-600 font-semibold" : "text-slate-600"}>{fmtDate(r.data_invio_prevista)}</span>
                                        {r.da_inviare && <div className="text-[10px] text-rose-500">da inviare</div>}
                                    </td>
                                    <td className="px-3 py-2.5">
                                        <span className={`inline-block px-2 py-0.5 rounded-full text-[11px] font-medium border ${STATO_BADGE[r.stato] || STATO_BADGE.da_richiedere}`}>
                                            {STATO_LABEL[r.stato] || r.stato}
                                        </span>
                                    </td>
                                    <td className="px-3 py-2.5 text-right font-mono font-semibold text-violet-700">{r.dovuto ? fmtEur(r.dovuto) : "—"}</td>
                                    <td className="px-3 py-2.5">
                                        <div className="flex items-center justify-end gap-1">
                                            <Button size="sm" variant="ghost" className="h-7 px-2 text-sky-700 hover:bg-sky-50" title="Invia lettera richiesta dati"
                                                onClick={() => setLetteraRow(r)} data-testid={`reg-lettera-${r.polizza_id}`}>
                                                <Mail size={14} />
                                            </Button>
                                            <Button size="sm" variant="ghost" className="h-7 px-2 text-violet-700 hover:bg-violet-50" title="Calcola regolazione"
                                                onClick={() => setCalcolaRow(r)} data-testid={`reg-calcola-${r.polizza_id}`}>
                                                <Calculator size={14} />
                                            </Button>
                                            <Button size="sm" variant="ghost" className="h-7 px-2 text-emerald-700 hover:bg-emerald-50" title="Genera titolo di regolazione"
                                                onClick={() => setTitoloRow(r)} data-testid={`reg-titolo-${r.polizza_id}`}>
                                                <Receipt size={14} />
                                            </Button>
                                            <Button size="sm" variant="ghost" className="h-7 px-2 text-amber-700 hover:bg-amber-50" title="Allega documenti regolazione"
                                                onClick={() => setDocRow(r)} data-testid={`reg-doc-${r.polizza_id}`}>
                                                <Paperclip size={14} />
                                            </Button>
                                            <Link to={`/polizze/${r.polizza_id}`} className="h-7 px-2 flex items-center text-slate-400 hover:text-slate-700" title="Apri polizza">
                                                <ExternalLink size={14} />
                                            </Link>
                                        </div>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            </Card>

            {calcolaRow && (
                <RegolazionePremioDialog
                    polizza={{
                        id: calcolaRow.polizza_id,
                        numero_polizza: calcolaRow.numero_polizza,
                        regolazione_base: calcolaRow.base_tipo,
                        regolazione_base_preventivo: calcolaRow.base_preventivo,
                        regolazione_tasso: calcolaRow.tasso,
                        regolazione_minima: calcolaRow.minima,
                    }}
                    onClose={() => setCalcolaRow(null)}
                    onSaved={() => { load(); }}
                />
            )}

            {letteraRow && (
                <LetteraDialog row={letteraRow} onClose={() => setLetteraRow(null)} onSent={() => { setLetteraRow(null); load(); }} />
            )}

            {titoloRow && (
                <TitoloDialog row={titoloRow} onClose={() => setTitoloRow(null)} onDone={() => { setTitoloRow(null); load(); }} />
            )}

            {docRow && (
                <DocumentiRegolazioneDialog row={docRow} onClose={() => setDocRow(null)} />
            )}
        </div>
    );
}

function DocumentiRegolazioneDialog({ row, onClose }) {
    const [items, setItems] = useState(null);
    const [uploading, setUploading] = useState(false);
    const [visibile, setVisibile] = useState(false);

    const load = useCallback(async () => {
        try {
            const r = await api.get("/allegati", { params: { entita_tipo: "polizza", entita_id: row.polizza_id } });
            setItems((r.data || []).filter((a) => a.categoria === "regolazione"));
        } catch { setItems([]); }
    }, [row.polizza_id]);

    useEffect(() => { load(); }, [load]);

    const upload = async (files) => {
        const list = files ? Array.from(files) : [];
        if (!list.length) return;
        setUploading(true);
        try {
            for (const file of list) {
                const fd = new FormData();
                fd.append("file", file);
                const params = new URLSearchParams({
                    entita_tipo: "polizza", entita_id: row.polizza_id,
                    categoria: "regolazione", visibile_cliente: visibile ? "true" : "false",
                });
                await api.post(`/allegati?${params.toString()}`, fd, { headers: { "Content-Type": "multipart/form-data" } });
            }
            toast.success(list.length > 1 ? `${list.length} documenti caricati` : "Documento caricato");
            await load();
        } catch (e) { toast.error(e.response?.data?.detail || "Errore upload"); }
        finally { setUploading(false); }
    };

    const rimuovi = async (aid) => {
        if (!window.confirm("Eliminare il documento?")) return;
        try { await api.delete(`/allegati/${aid}`); toast.success("Eliminato"); await load(); }
        catch { toast.error("Errore"); }
    };

    return (
        <Dialog open onOpenChange={(o) => !o && onClose()}>
            <DialogContent className="max-w-lg" data-testid="reg-doc-dialog">
                <DialogHeader>
                    <DialogTitle className="flex items-center gap-2"><Paperclip className="text-amber-600" size={18} /> Documenti regolazione · {row.numero_polizza}</DialogTitle>
                </DialogHeader>
                <div className="space-y-3 py-2">
                    <div className="text-[11px] text-slate-500 bg-slate-50 border border-slate-200 rounded p-2">
                        I documenti vengono salvati sulla polizza nella categoria <b>Regolazione</b> e sono
                        consultabili nel quadrotto "Regolazione" della scheda Documenti.
                    </div>
                    <label className="flex items-center gap-2 text-xs text-slate-600 cursor-pointer">
                        <input type="checkbox" checked={visibile} onChange={(e) => setVisibile(e.target.checked)} data-testid="reg-doc-visibile" />
                        Rendi visibile al cliente nel portale
                    </label>
                    <label className="block w-full p-4 text-center border-2 border-dashed border-amber-300 bg-amber-50 rounded cursor-pointer hover:bg-amber-100 text-xs text-amber-800"
                        data-testid="reg-doc-upload">
                        {uploading ? <><Loader2 size={14} className="inline animate-spin mr-1" /> Caricamento…</> : <><Upload size={14} className="inline mr-1" /> Carica documento (PDF, immagini)</>}
                        <input type="file" multiple hidden accept=".pdf,.jpg,.jpeg,.png,.heic,.webp,.doc,.docx,.xls,.xlsx"
                            onChange={(e) => upload(e.target.files)} />
                    </label>
                    <div className="space-y-1.5 max-h-64 overflow-y-auto">
                        {items === null ? (
                            <div className="text-center text-xs text-slate-400 py-4"><Loader2 size={14} className="inline animate-spin mr-1" /> Caricamento…</div>
                        ) : items.length === 0 ? (
                            <div className="text-center text-xs text-slate-400 italic py-4">Nessun documento di regolazione caricato</div>
                        ) : items.map((a) => (
                            <div key={a.id} className="flex items-center gap-2 p-2 bg-white rounded border border-slate-200" data-testid={`reg-doc-row-${a.id}`}>
                                <FileText size={14} className="text-sky-600 shrink-0" />
                                <a href={`${API_BASE}/allegati/${a.id}/download`} target="_blank" rel="noreferrer"
                                    className="flex-1 min-w-0 text-sm text-sky-700 hover:underline truncate">{a.nome_file}</a>
                                {a.visibile_cliente && <span className="text-[10px] bg-emerald-100 text-emerald-700 px-1 rounded">cliente</span>}
                                <button onClick={() => rimuovi(a.id)} className="text-rose-500 hover:text-rose-700" data-testid={`reg-doc-del-${a.id}`}>
                                    <Trash2 size={14} />
                                </button>
                            </div>
                        ))}
                    </div>
                </div>
                <DialogFooter>
                    <Button variant="outline" onClick={onClose}>Chiudi</Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}

function LetteraDialog({ row, onClose, onSent }) {
    const [testoExtra, setTestoExtra] = useState("");
    const [busy, setBusy] = useState(false);

    const scarica = async () => {
        setBusy(true);
        try {
            const r = await api.post(`/regolazione-premio/${row.polizza_id}/lettera-pdf`,
                { testo_extra: testoExtra }, { responseType: "blob" });
            const url = URL.createObjectURL(new Blob([r.data], { type: "application/pdf" }));
            window.open(url, "_blank");
        } catch { toast.error("Errore generazione PDF"); }
        finally { setBusy(false); }
    };

    const segna = async (inviaEmail) => {
        setBusy(true);
        try {
            const r = await api.post(`/regolazione-premio/${row.polizza_id}/invia-lettera`,
                { invia_email: inviaEmail, testo_extra: testoExtra });
            toast.success(inviaEmail ? `Email ${r.data.email}` : "Lettera segnata come inviata");
            onSent();
        } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
        finally { setBusy(false); }
    };

    return (
        <Dialog open onOpenChange={(o) => !o && onClose()}>
            <DialogContent className="max-w-lg" data-testid="reg-lettera-dialog">
                <DialogHeader>
                    <DialogTitle className="flex items-center gap-2"><Mail className="text-sky-600" size={18} /> Lettera richiesta dati · {row.numero_polizza}</DialogTitle>
                </DialogHeader>
                <div className="space-y-3 py-2">
                    <div className="text-sm text-slate-600">
                        Destinatario: <b>{row.contraente_nome}</b>
                        {row.contraente_email ? <span className="text-slate-500"> · {row.contraente_email}</span> : <span className="text-amber-600"> · nessuna email registrata</span>}
                    </div>
                    <div>
                        <Label className="text-xs">Testo aggiuntivo (opzionale)</Label>
                        <Textarea rows={3} value={testoExtra} onChange={(e) => setTestoExtra(e.target.value)}
                            placeholder="Es. dettagli specifici della richiesta…" data-testid="reg-lettera-extra" />
                    </div>
                </div>
                <DialogFooter className="flex-wrap gap-2">
                    <Button variant="outline" onClick={scarica} disabled={busy} data-testid="reg-lettera-pdf">
                        <Download size={14} className="mr-1" /> Anteprima PDF
                    </Button>
                    <Button variant="outline" onClick={() => segna(false)} disabled={busy} data-testid="reg-lettera-manuale">
                        <CheckCircle2 size={14} className="mr-1" /> Segna inviata (manuale)
                    </Button>
                    <Button onClick={() => segna(true)} disabled={busy || !row.contraente_email}
                        className="bg-sky-700 hover:bg-sky-800" data-testid="reg-lettera-email">
                        <Mail size={14} className="mr-1" /> Invia email
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}

function TitoloDialog({ row, onClose, onDone }) {
    const ratio = row.imposte_ratio || 0;
    const [importo, setImporto] = useState(row.dovuto || 0);
    const [imposte, setImposte] = useState(() => Math.round(((row.dovuto || 0) * ratio) * 100) / 100);
    const [impTouched, setImpTouched] = useState(false);
    const [busy, setBusy] = useState(false);

    // Riporta in automatico le imposte in proporzione all'aliquota della polizza,
    // finché l'utente non le modifica manualmente.
    useEffect(() => {
        if (!impTouched) setImposte(Math.round(((parseFloat(importo) || 0) * ratio) * 100) / 100);
    }, [importo, ratio, impTouched]);

    const genera = async () => {
        if (!importo || importo <= 0) { toast.error("Importo dovuto mancante: calcola prima la regolazione"); return; }
        setBusy(true);
        try {
            await api.post(`/regolazione-premio/${row.polizza_id}/genera-titolo`, {
                importo: parseFloat(importo), imposte: parseFloat(imposte) || 0,
            });
            toast.success("Titolo di regolazione creato");
            onDone();
        } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
        finally { setBusy(false); }
    };

    return (
        <Dialog open onOpenChange={(o) => !o && onClose()}>
            <DialogContent className="max-w-md" data-testid="reg-titolo-dialog">
                <DialogHeader>
                    <DialogTitle className="flex items-center gap-2"><Receipt className="text-emerald-600" size={18} /> Genera titolo · {row.numero_polizza}</DialogTitle>
                </DialogHeader>
                <div className="space-y-3 py-2">
                    <div><Label className="text-xs">Importo lordo €</Label><Input type="number" step="0.01" value={importo} onChange={(e) => setImporto(e.target.value)} data-testid="reg-titolo-importo" /></div>
                    <div><Label className="text-xs">di cui imposte €</Label><Input type="number" step="0.01" value={imposte} onChange={(e) => { setImpTouched(true); setImposte(e.target.value); }} data-testid="reg-titolo-imposte" /></div>
                    <div className="text-[11px] text-slate-500 bg-slate-50 border border-slate-200 rounded p-2">
                        Verrà creato un titolo di tipo <b>regolazione</b> in stato "da incassare" collegato alla polizza.
                    </div>
                </div>
                <DialogFooter>
                    <Button variant="outline" onClick={onClose}>Annulla</Button>
                    <Button onClick={genera} disabled={busy} className="bg-emerald-700 hover:bg-emerald-800" data-testid="reg-titolo-conferma">Genera titolo</Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}
