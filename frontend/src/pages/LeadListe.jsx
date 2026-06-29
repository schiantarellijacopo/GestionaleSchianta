/**
 * Liste Lead — import Excel/CSV di prospect forniti dalle compagnie + dispatch
 * WhatsApp/Email diretto. Matching automatico con anagrafiche esistenti.
 */
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { PageHeader, Loading, Empty } from "@/components/Shared";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Checkbox } from "@/components/ui/checkbox";
import {
    Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
    Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogTrigger,
} from "@/components/ui/dialog";
import { Upload, ListChecks, Send, Trash2, MessageCircle, Mail, Users, FileSpreadsheet } from "lucide-react";
import { toast } from "sonner";

export default function LeadListe() {
    const [liste, setListe] = useState(null);
    const [openImport, setOpenImport] = useState(false);
    const [active, setActive] = useState(null);  // lista selezionata per dispatch
    const [openDispatch, setOpenDispatch] = useState(false);
    const [leadView, setLeadView] = useState(null); // lista selezionata per visualizza leads

    const load = () => api.get("/lead-liste").then((r) => setListe(r.data));
    useEffect(() => { load(); }, []);

    const del = async (l) => {
        if (!window.confirm(`Eliminare la lista "${l.nome}" e tutti i suoi ${l.totale} lead?`)) return;
        try { await api.delete(`/lead-liste/${l.id}`); toast.success("Eliminata"); load(); }
        catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
    };

    return (
        <div data-testid="lead-liste-page" className="space-y-5">
            <PageHeader
                title={<span className="flex items-center gap-2"><ListChecks className="text-indigo-600" /> Liste Lead</span>}
                subtitle="Importa liste Excel/CSV fornite dalle compagnie · dispatch WhatsApp/Email diretto"
                actions={
                    <Dialog open={openImport} onOpenChange={setOpenImport}>
                        <DialogTrigger asChild>
                            <Button className="bg-indigo-700 hover:bg-indigo-800" data-testid="ll-import">
                                <Upload size={14} className="mr-1" /> Importa lista
                            </Button>
                        </DialogTrigger>
                        <ImportDialog onClose={() => { setOpenImport(false); load(); }} />
                    </Dialog>
                }
            />

            {liste === null ? <Loading /> : liste.length === 0 ? <Empty message="Nessuna lista importata. Premi 'Importa lista' per iniziare." /> : (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                    {liste.map((l) => (
                        <Card key={l.id} className="p-4 hover:shadow-md transition" data-testid={`ll-card-${l.id}`}>
                            <div className="flex items-start justify-between">
                                <div className="flex-1 min-w-0">
                                    <h3 className="font-semibold text-slate-900 truncate">{l.nome}</h3>
                                    {l.fonte && <div className="text-[10px] text-slate-400">Fonte: {l.fonte}</div>}
                                    <div className="text-xs text-slate-500 mt-1">{new Date(l.created_at).toLocaleDateString("it-IT")}</div>
                                </div>
                                <FileSpreadsheet size={20} className="text-indigo-400" />
                            </div>
                            <div className="grid grid-cols-3 gap-2 mt-3">
                                <Stat label="Totale" value={l.totale} color="indigo" />
                                <Stat label="Matched" value={l.matched_clienti} color="emerald" />
                                <Stat label="Nuovi" value={l.lead_creati} color="amber" />
                            </div>
                            {l.ultimo_dispatch && (
                                <div className="mt-2 text-[10px] text-slate-500">
                                    Ultimo invio {l.ultimo_canale}: {l.ultimo_inviati} il {new Date(l.ultimo_dispatch).toLocaleDateString("it-IT")}
                                </div>
                            )}
                            <div className="flex justify-between gap-1 mt-3 pt-3 border-t border-slate-100">
                                <Button size="sm" variant="outline" onClick={() => setLeadView(l)} data-testid={`ll-view-${l.id}`}>
                                    <Users size={12} className="mr-1" /> Vedi lead
                                </Button>
                                <div className="flex gap-1">
                                    <Button size="sm" onClick={() => { setActive(l); setOpenDispatch(true); }}
                                        className="bg-emerald-700 hover:bg-emerald-800" data-testid={`ll-dispatch-${l.id}`}>
                                        <Send size={12} className="mr-1" /> Invia
                                    </Button>
                                    <button onClick={() => del(l)} className="text-rose-600 hover:bg-rose-50 p-1.5 rounded">
                                        <Trash2 size={13} />
                                    </button>
                                </div>
                            </div>
                        </Card>
                    ))}
                </div>
            )}

            {openDispatch && active && (
                <DispatchDialog lista={active}
                    onClose={() => { setOpenDispatch(false); setActive(null); load(); }} />
            )}
            {leadView && (
                <LeadViewerDialog lista={leadView} onClose={() => setLeadView(null)} />
            )}
        </div>
    );
}

const Stat = ({ label, value, color }) => (
    <div className={`bg-${color}-50 border border-${color}-100 rounded p-2 text-center`}>
        <div className={`text-lg font-bold text-${color}-700 font-mono`}>{value || 0}</div>
        <div className="text-[9px] uppercase text-slate-500">{label}</div>
    </div>
);

function ImportDialog({ onClose }) {
    const [f, setF] = useState({ nome: "", note: "", fonte: "import", file: null, compagnia_id: "" });
    const [busy, setBusy] = useState(false);
    const [compagnie, setCompagnie] = useState([]);
    useEffect(() => { api.get("/compagnie").then((r) => setCompagnie(r.data || [])); }, []);
    const set = (k, v) => setF((p) => ({ ...p, [k]: v }));

    const submit = async () => {
        if (!f.nome.trim()) { toast.error("Inserisci un nome per la lista"); return; }
        if (!f.file) { toast.error("Seleziona un file .xlsx o .csv"); return; }
        setBusy(true);
        try {
            const fd = new FormData();
            fd.append("nome", f.nome);
            fd.append("note", f.note || "");
            fd.append("fonte", f.fonte || "import");
            if (f.compagnia_id) fd.append("compagnia_id", f.compagnia_id);
            fd.append("file", f.file);
            const r = await api.post("/lead-liste/import", fd, {
                headers: { "Content-Type": "multipart/form-data" },
            });
            toast.success(`Importati ${r.data.totale} lead (${r.data.matched_clienti} già clienti, ${r.data.lead_creati} nuovi)`);
            onClose();
        } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
        finally { setBusy(false); }
    };

    return (
        <DialogContent className="max-w-lg">
            <DialogHeader><DialogTitle>Importa lista lead</DialogTitle></DialogHeader>
            <div className="space-y-3 py-2">
                <div><Label>Nome lista *</Label>
                    <Input value={f.nome} onChange={(e) => set("nome", e.target.value)}
                        placeholder="es. Liste Unipol Q1 2026" data-testid="ll-imp-nome" /></div>
                <div className="grid grid-cols-2 gap-3">
                    <div><Label>Fonte</Label>
                        <Input value={f.fonte} onChange={(e) => set("fonte", e.target.value)}
                            placeholder="es. Unipol, fiera, sito web..." /></div>
                    <div><Label>Compagnia (opzionale)</Label>
                        <Select value={f.compagnia_id} onValueChange={(v) => set("compagnia_id", v)}>
                            <SelectTrigger><SelectValue placeholder="—" /></SelectTrigger>
                            <SelectContent>
                                {compagnie.map((c) => <SelectItem key={c.id} value={c.id}>{c.ragione_sociale}</SelectItem>)}
                            </SelectContent>
                        </Select>
                    </div>
                </div>
                <div><Label>File Excel (.xlsx) o CSV *</Label>
                    <Input type="file" accept=".xlsx,.csv,.txt"
                        onChange={(e) => set("file", e.target.files?.[0])} data-testid="ll-imp-file" /></div>
                <div className="text-[11px] text-slate-500 bg-indigo-50 border border-indigo-200 rounded p-2">
                    <strong>Schema accettato (colonne con header):</strong> Nome, Cognome, Codice Fiscale,
                    Email, Telefono, Cellulare, Città, Note, Ragione Sociale, Indirizzo, Data Nascita.<br />
                    <strong>✓ Formato RHX/Cattolica/Generali supportato:</strong> "Contatto" (NOME COGNOME), Telefono, Cellulare, Email,
                    Indirizzo (es. "VIA X 12-23030-CITTA-SO"), Età, Professione/Attività, Privacy Commerciale/Posta/Email (S/N),
                    Segmento Lista, Cross Selling, Esito. Funziona anche su file multi-foglio (es. AutoConvenienTe + Vita-DNA senza RCA).<br />
                    Il matching avviene su CF → Email → Telefono/Cellulare.
                </div>
                <div><Label>Note</Label>
                    <Textarea rows={2} value={f.note} onChange={(e) => set("note", e.target.value)} /></div>
            </div>
            <DialogFooter>
                <Button onClick={submit} disabled={busy} className="bg-indigo-700 hover:bg-indigo-800" data-testid="ll-imp-save">
                    {busy ? "Import in corso…" : "Importa lista"}
                </Button>
            </DialogFooter>
        </DialogContent>
    );
}

function DispatchDialog({ lista, onClose }) {
    const [f, setF] = useState({
        canale: "email", oggetto: "", messaggio: "", solo_matched: false,
    });
    const [busy, setBusy] = useState(false);
    const set = (k, v) => setF((p) => ({ ...p, [k]: v }));

    const submit = async () => {
        if (!f.messaggio.trim()) { toast.error("Inserisci il messaggio"); return; }
        if (f.canale === "email" && !f.oggetto.trim()) { toast.error("Oggetto obbligatorio per email"); return; }
        setBusy(true);
        try {
            const r = await api.post("/lead-liste/dispatch", {
                lista_id: lista.id, ...f,
            });
            toast.success(`Inviati ${r.data.inviati} messaggi (${r.data.falliti} falliti)`);
            onClose();
        } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
        finally { setBusy(false); }
    };

    return (
        <Dialog open onOpenChange={(o) => !o && onClose()}>
            <DialogContent className="max-w-xl">
                <DialogHeader>
                    <DialogTitle>Invia messaggio · lista "{lista.nome}"</DialogTitle>
                </DialogHeader>
                <div className="space-y-3 py-2">
                    <div>
                        <Label>Canale *</Label>
                        <div className="grid grid-cols-2 gap-2 mt-1">
                            <button type="button" onClick={() => set("canale", "email")}
                                className={`p-2 border rounded text-sm flex items-center justify-center gap-2
                                    ${f.canale === "email" ? "bg-sky-600 text-white border-sky-700" : "border-slate-300 bg-white"}`}
                                data-testid="ll-disp-email">
                                <Mail size={14} /> Email
                            </button>
                            <button type="button" onClick={() => set("canale", "whatsapp")}
                                className={`p-2 border rounded text-sm flex items-center justify-center gap-2
                                    ${f.canale === "whatsapp" ? "bg-emerald-600 text-white border-emerald-700" : "border-slate-300 bg-white"}`}
                                data-testid="ll-disp-wa">
                                <MessageCircle size={14} /> WhatsApp
                            </button>
                        </div>
                    </div>
                    {f.canale === "email" && (
                        <div><Label>Oggetto *</Label>
                            <Input value={f.oggetto} onChange={(e) => set("oggetto", e.target.value)} /></div>
                    )}
                    <div><Label>Messaggio *</Label>
                        <Textarea rows={6} value={f.messaggio} onChange={(e) => set("messaggio", e.target.value)}
                            placeholder="Ciao {nome}, abbiamo una proposta..." data-testid="ll-disp-msg" />
                        <div className="text-[10px] text-slate-500 mt-1">Variabili supportate: {`{nome} {cognome} {citta}`}</div>
                    </div>
                    <div className="flex items-center gap-2">
                        <Checkbox id="onlym" checked={f.solo_matched} onCheckedChange={(v) => set("solo_matched", !!v)} />
                        <Label htmlFor="onlym" className="text-xs">Invia solo a chi è già in anagrafica (matched)</Label>
                    </div>
                    <div className="text-[11px] text-amber-700 bg-amber-50 border border-amber-200 rounded p-2">
                        ⚠️ Dispatch in modalità simulata (loggato). Le credenziali Twilio/Spoki/SMTP non
                        sono ancora configurate. Ogni invio reale verrà attivato collegando il provider
                        in Impostazioni.
                    </div>
                </div>
                <DialogFooter>
                    <Button variant="outline" onClick={onClose}>Annulla</Button>
                    <Button onClick={submit} disabled={busy} className="bg-emerald-700 hover:bg-emerald-800" data-testid="ll-disp-send">
                        {busy ? "Invio…" : "Invia ora"}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}

function LeadViewerDialog({ lista, onClose }) {
    const [leads, setLeads] = useState(null);
    useEffect(() => {
        api.get(`/lead-liste/${lista.id}/lead`).then((r) => setLeads(r.data));
    }, [lista.id]);
    return (
        <Dialog open onOpenChange={(o) => !o && onClose()}>
            <DialogContent className="max-w-4xl max-h-[80vh]">
                <DialogHeader><DialogTitle>Lead della lista "{lista.nome}" ({lista.totale})</DialogTitle></DialogHeader>
                <div className="overflow-auto max-h-[60vh]">
                    {leads === null ? <Loading /> : (
                        <table className="tbl-compact w-full text-xs">
                            <thead><tr>
                                <th>Nome</th><th>CF</th><th>Email</th><th>Telefono</th><th>Città</th><th>Match</th>
                            </tr></thead>
                            <tbody>
                                {leads.map((l) => (
                                    <tr key={l.id}>
                                        <td className="font-medium">{l.nome_completo}</td>
                                        <td className="font-mono">{l.codice_fiscale || "—"}</td>
                                        <td>{l.email || "—"}</td>
                                        <td className="font-mono">{l.cellulare || l.telefono || "—"}</td>
                                        <td>{l.citta || "—"}</td>
                                        <td>{l.anagrafica_id ? <span className="text-emerald-700 text-[10px]">✓ {l.matched_nome}</span> : <span className="text-amber-700 text-[10px]">nuovo</span>}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    )}
                </div>
            </DialogContent>
        </Dialog>
    );
}
