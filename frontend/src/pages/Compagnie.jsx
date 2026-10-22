import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { PageHeader, Empty, Loading } from "@/components/Shared";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import {
    Select, SelectTrigger, SelectValue, SelectContent, SelectItem,
} from "@/components/ui/select";
import {
    Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger, DialogFooter,
} from "@/components/ui/dialog";
import { Plus, Building2, Edit, Trash2, Link2, FileText, Paperclip } from "lucide-react";
import { toast } from "sonner";
import AvvisoScadenzaControl from "@/components/AvvisoScadenzaControl";
import DateInputIt from "@/components/DateInputIt";

export default function Compagnie() {
    const [list, setList] = useState(null);
    const [agenzie, setAgenzie] = useState([]);
    const [open, setOpen] = useState(false);
    const [editing, setEditing] = useState(null);

    const load = () => api.get("/compagnie?tutte=true").then((r) => setList(r.data));
    useEffect(() => { load(); api.get("/agenzie").then((r) => setAgenzie(r.data)); }, []);

    const del = async (c) => {
        if (!window.confirm(`Eliminare compagnia ${c.ragione_sociale}?`)) return;
        try { await api.delete(`/compagnie/${c.id}`); toast.success("Eliminata"); load(); }
        catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
    };

    return (
        <div data-testid="compagnie-page">
            <PageHeader
                title="Compagnie assicurative"
                subtitle="Anagrafica compagnie · tipo mandato · agenzia partner"
                actions={
                    <Dialog open={open} onOpenChange={(o) => { if (!o) { setEditing(null); load(); } setOpen(o); }}>
                        <DialogTrigger asChild>
                            <Button onClick={() => setEditing(null)} data-testid="comp-new-button" className="bg-sky-700 hover:bg-sky-800">
                                <Plus size={16} className="mr-1" /> Nuova compagnia
                            </Button>
                        </DialogTrigger>
                        <CompagniaDialog key={open ? (editing?.id || "new") : "closed"} editing={editing} agenzie={agenzie}
                            onClose={() => { setOpen(false); setEditing(null); load(); }} />
                    </Dialog>
                }
            />

            {list === null ? <Loading /> : list.length === 0 ? <Empty /> : (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                    {list.map((c) => {
                        const isColl = c.tipo_mandato === "collaborazione";
                        const partner = agenzie.find((a) => a.id === c.agenzia_partner_id);
                        return (
                            <div key={c.id} className="bg-white border border-slate-200 rounded-md p-5 hover:shadow-md transition-shadow" data-testid={`comp-card-${c.id}`}>
                                <div className="flex items-center gap-3 mb-3">
                                    <div className={`w-10 h-10 rounded-md flex items-center justify-center ${isColl ? "bg-amber-50 text-amber-700" : "bg-sky-50 text-sky-700"}`}>
                                        <Building2 size={18} />
                                    </div>
                                    <div className="flex-1 min-w-0">
                                        <div className="font-medium text-slate-900 truncate">{c.ragione_sociale}</div>
                                        <div className="text-xs text-slate-500 num">Codice: {c.codice}</div>
                                    </div>
                                    <span className={`badge ${c.attiva ? "badge-success" : "badge-neutral"}`}>
                                        {c.attiva ? "attiva" : "inattiva"}
                                    </span>
                                </div>

                                {/* tipo mandato */}
                                <div className="flex items-center gap-2 mb-2">
                                    <span className={`text-[10px] uppercase tracking-wider font-bold px-2 py-0.5 rounded ${isColl ? "bg-amber-100 text-amber-800" : "bg-emerald-100 text-emerald-800"}`}>
                                        {isColl ? "Mandato collaborazione" : "Mandato diretto"}
                                    </span>
                                    {isColl && partner && (
                                        <span className="text-xs text-slate-600 flex items-center gap-1">
                                            <Link2 size={11} className="text-amber-600" /> via <span className="font-semibold">{partner.ragione_sociale}</span>
                                        </span>
                                    )}
                                </div>

                                {c.referente && <div className="text-sm text-slate-700">Referente: <span className="font-medium">{c.referente}</span></div>}
                                {c.email && <div className="text-sm text-slate-600">{c.email}</div>}
                                {c.telefono && <div className="text-sm text-slate-600 num">{c.telefono}</div>}
                                {c.descrizione && <div className="text-xs text-slate-500 mt-2">{c.descrizione}</div>}

                                <div className="flex justify-end gap-1 mt-3 pt-3 border-t border-slate-100">
                                    <button onClick={() => { setEditing(c); setOpen(true); }}
                                        className="text-sky-700 hover:bg-sky-50 p-1.5 rounded" data-testid={`comp-edit-${c.id}`}>
                                        <Edit size={13} />
                                    </button>
                                    <button onClick={() => del(c)}
                                        className="text-rose-600 hover:bg-rose-50 p-1.5 rounded" data-testid={`comp-del-${c.id}`}>
                                        <Trash2 size={13} />
                                    </button>
                                </div>
                            </div>
                        );
                    })}
                </div>
            )}
        </div>
    );
}

function CompagniaDialog({ editing, agenzie, onClose }) {
    const [f, setF] = useState(() => {
        const base = editing || {
            codice: "", ragione_sociale: "", referente: "",
            email: "", telefono: "", sito_web: "", descrizione: "", attiva: true,
            trattiene_provvigioni: true,
        };
        const ids = (editing?.agenzie_partner_ids && editing.agenzie_partner_ids.length)
            ? editing.agenzie_partner_ids
            : (editing?.agenzia_partner_id ? [editing.agenzia_partner_id] : []);
        return { ...base, agenzie_partner_ids: ids };
    });
    const set = (k, v) => setF((p) => ({ ...p, [k]: v }));
    const partnerList = agenzie.filter((a) => a.tipo === "partner");
    const haPartner = (f.agenzie_partner_ids || []).length > 0;
    const togglePartner = (id) => setF((p) => {
        const cur = p.agenzie_partner_ids || [];
        return { ...p, agenzie_partner_ids: cur.includes(id) ? cur.filter((x) => x !== id) : [...cur, id] };
    });
    const save = async () => {
        if (!f.codice || !f.ragione_sociale) { toast.error("Codice e ragione sociale obbligatori"); return; }
        try {
            const ids = f.agenzie_partner_ids || [];
            const payload = {
                ...f,
                agenzie_partner_ids: ids,
                agenzia_partner_id: ids.length === 1 ? ids[0] : null,
                tipo_mandato: ids.length ? "collaborazione" : "diretto",
            };
            if (editing?.id) await api.put(`/compagnie/${editing.id}`, payload);
            else await api.post("/compagnie", payload);
            toast.success(editing?.id ? "Aggiornata" : "Creata"); onClose();
        } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
    };

    return (
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
            <DialogHeader><DialogTitle>{editing?.id ? "Modifica" : "Nuova"} compagnia</DialogTitle></DialogHeader>
            <div className="space-y-3 py-2">
                <div className="grid grid-cols-2 gap-3">
                    <div><Label>Codice *</Label><Input data-testid="comp-codice-input" value={f.codice}
                        onChange={(e) => set("codice", e.target.value.toUpperCase())} /></div>
                    <div><Label>Ragione sociale *</Label><Input data-testid="comp-rs-input" value={f.ragione_sociale}
                        onChange={(e) => set("ragione_sociale", e.target.value)} /></div>
                </div>

                {/* SEZIONE MANDATO — una o più agenzie partner (multi) */}
                <div className="border-t pt-3 mt-3">
                    <h3 className="text-xs font-semibold text-slate-700 uppercase tracking-wider mb-2">
                        🔗 Agenzia partner (anche più di una)
                    </h3>
                    <div className="text-[11px] text-slate-500 mb-2">
                        Spunta le agenzie partner che hanno il mandato di questa compagnia. Se non spunti nulla, la compagnia è a <strong>mandato diretto</strong> dell&apos;agenzia principale.
                    </div>
                    {partnerList.length === 0 ? (
                        <div className="text-xs text-slate-400 italic">Nessuna agenzia partner configurata.</div>
                    ) : (
                        <div className="grid grid-cols-2 gap-2">
                            {partnerList.map((a) => {
                                const checked = (f.agenzie_partner_ids || []).includes(a.id);
                                return (
                                    <label key={a.id} className={`flex items-center gap-2 border rounded p-2 cursor-pointer text-sm ${checked ? "border-violet-400 bg-violet-50" : "border-slate-200"}`}
                                        data-testid={`comp-partner-${a.id}`}>
                                        <Checkbox checked={checked} onCheckedChange={() => togglePartner(a.id)} />
                                        <span>{a.ragione_sociale}</span>
                                    </label>
                                );
                            })}
                        </div>
                    )}
                    <div className="text-[11px] text-slate-500 bg-slate-50 border border-slate-200 rounded p-2 mt-2">
                        {haPartner ? (
                            <>📍 <strong>Collaborazione</strong>: il mandato diretto con la compagnia è dell&apos;agenzia
                                partner. Saldo cassa = <strong>premi interi</strong> (no detrazione provvigioni). Le nostre provvigioni le
                                fatturerà l&apos;agenzia partner.</>
                        ) : (
                            <>📍 <strong>Diretto</strong>: rapporto diretto con la compagnia. Saldo cassa =
                                <strong> premi − provvigioni</strong> (se &quot;tratteniamo le provvigioni&quot;). Le ritenute compagnia sono in
                                negativo sulle provvigioni e vanno versate.</>
                        )}
                    </div>
                </div>

                {!haPartner && (
                    <div className="flex items-center gap-2 mt-1">
                        <Checkbox id="trattiene" checked={!!f.trattiene_provvigioni}
                            onCheckedChange={(v) => set("trattiene_provvigioni", !!v)} />
                        <Label htmlFor="trattiene" className="text-xs cursor-pointer">
                            Tratteniamo le provvigioni dal premio (saldo = premio − provv.)
                        </Label>
                    </div>
                )}

                <div className="border-t pt-3 mt-3">
                    <h3 className="text-xs font-semibold text-slate-700 uppercase tracking-wider mb-2">Contatti</h3>
                    <div className="grid grid-cols-2 gap-3">
                        <div><Label>Referente</Label><Input value={f.referente || ""} onChange={(e) => set("referente", e.target.value)} /></div>
                        <div><Label>Sito web</Label><Input value={f.sito_web || ""} onChange={(e) => set("sito_web", e.target.value)} /></div>
                        <div><Label>Email</Label><Input value={f.email || ""} onChange={(e) => set("email", e.target.value)} /></div>
                        <div><Label>Telefono</Label><Input value={f.telefono || ""} onChange={(e) => set("telefono", e.target.value)} /></div>
                    </div>
                    <div className="mt-2"><Label>Descrizione</Label>
                        <Input value={f.descrizione || ""} onChange={(e) => set("descrizione", e.target.value)} /></div>
                    <div className="flex items-center gap-2 mt-2">
                        <Checkbox id="attiva" checked={!!f.attiva} onCheckedChange={(v) => set("attiva", !!v)} />
                        <Label htmlFor="attiva" className="text-xs cursor-pointer">Compagnia attiva</Label>
                    </div>
                </div>

                {/* DOCUMENTI COMPAGNIA */}
                {editing?.id ? (
                    <div className="border-t pt-3 mt-3" data-testid="comp-documenti-sezione">
                        <h3 className="text-xs font-semibold text-slate-700 uppercase tracking-wider mb-2 flex items-center gap-1.5">
                            <FileText size={13} className="text-slate-500" /> Documenti
                        </h3>
                        <DocumentiCompagnia cid={editing.id} iniziali={editing.documenti || []} />
                    </div>
                ) : (
                    <div className="border-t pt-3 mt-3 text-xs text-slate-400" data-testid="comp-documenti-hint">
                        Salva la compagnia per poter caricare i documenti.
                    </div>
                )}
            </div>
            <DialogFooter>
                <Button data-testid="comp-save-button" onClick={save} className="bg-sky-700 hover:bg-sky-800">
                    {editing?.id ? "Aggiorna" : "Crea compagnia"}
                </Button>
            </DialogFooter>
        </DialogContent>
    );
}

// =================== DOCUMENTI COMPAGNIA (card) ===================
const COMP_DOC_TIPI_FALLBACK = [
    "Convenzione / Mandato", "Accordo provvigionale", "Circolari",
    "Condizioni di assicurazione", "Listini / Tariffe", "Documento IBAN", "Altro",
];

function compDocScadenza(dataScadenza) {
    if (!dataScadenza) return null;
    const d = new Date(dataScadenza + "T00:00:00");
    if (isNaN(d)) return null;
    const oggi = new Date(); oggi.setHours(0, 0, 0, 0);
    const giorni = Math.round((d - oggi) / 86400000);
    const dmt = d.toLocaleDateString("it-IT");
    if (giorni < 0) return { label: `Scaduto il ${dmt}`, cls: "bg-red-100 text-red-700" };
    if (giorni <= 30) return { label: `In scadenza (${dmt})`, cls: "bg-amber-100 text-amber-700" };
    return { label: `Scade il ${dmt}`, cls: "bg-slate-100 text-slate-600" };
}

function DocumentiCompagnia({ cid, iniziali }) {
    const [list, setList] = useState(iniziali || []);
    const [tipi, setTipi] = useState(COMP_DOC_TIPI_FALLBACK);
    const [tipologia, setTipologia] = useState("");
    const [descrizione, setDescrizione] = useState("");
    const [dataRilascio, setDataRilascio] = useState("");
    const [dataScadenza, setDataScadenza] = useState("");
    const [file, setFile] = useState(null);
    const [fileKey, setFileKey] = useState(0);

    useEffect(() => {
        api.get("/config/card-visibilita")
            .then((r) => {
                const lst = (r.data?.compagnia || []).map((c) => c.label).filter(Boolean);
                if (lst.length) setTipi(lst);
            }).catch(() => {});
    }, []);

    const aggiungi = async () => {
        if (!file) { toast.error("Seleziona un file"); return; }
        try {
            const fd = new FormData();
            fd.append("file", file);
            fd.append("tipologia", tipologia || "Altro");
            fd.append("descrizione", descrizione || "");
            fd.append("data_rilascio", dataRilascio || "");
            fd.append("data_scadenza", dataScadenza || "");
            const r = await api.post(`/compagnie/${cid}/documenti`, fd,
                { headers: { "Content-Type": "multipart/form-data" } });
            setList((p) => [...p, r.data]);
            setTipologia(""); setDescrizione(""); setDataRilascio(""); setDataScadenza(""); setFile(null); setFileKey((k) => k + 1);
            toast.success("Documento aggiunto");
        } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
    };
    const rimuovi = async (id) => {
        if (!window.confirm("Eliminare il documento?")) return;
        try {
            await api.delete(`/compagnie/${cid}/documenti/${id}`);
            setList((p) => p.filter((x) => x.id !== id));
            toast.success("Eliminato");
        } catch { toast.error("Errore"); }
    };
    const aggiornaAvviso = (itemId, patch) =>
        setList((p) => p.map((x) => x.id === itemId ? { ...x, ...patch } : x));

    const gruppi = {};
    (list || []).forEach((it) => { const k = it.tipologia || "Altro"; (gruppi[k] = gruppi[k] || []).push(it); });
    const ordine = [...tipi, ...Object.keys(gruppi).filter((k) => !tipi.includes(k))];

    return (
        <div className="space-y-3" data-testid="documenti-compagnia">
            <div className="border border-slate-200 rounded-md p-3 bg-slate-50">
                <div className="text-xs font-semibold text-slate-600 mb-2 flex items-center gap-1"><Plus size={13} /> Aggiungi documento</div>
                <div className="grid grid-cols-2 gap-2">
                    <div>
                        <Label className="text-xs">Tipologia</Label>
                        <select value={tipologia} onChange={(e) => setTipologia(e.target.value)}
                            className="w-full h-9 px-2 text-sm border border-slate-200 rounded-md bg-white" data-testid="comp-doc-tipologia">
                            <option value="">— Seleziona —</option>
                            {tipi.map((t) => <option key={t} value={t}>{t}</option>)}
                        </select>
                    </div>
                    <div>
                        <Label className="text-xs">Descrizione (facoltativa)</Label>
                        <Input value={descrizione} onChange={(e) => setDescrizione(e.target.value)} data-testid="comp-doc-descrizione" />
                    </div>
                    <div>
                        <Label className="text-xs">Data rilascio</Label>
                        <DateInputIt value={dataRilascio} onChange={setDataRilascio} data-testid="comp-doc-data-rilascio" />
                    </div>
                    <div>
                        <Label className="text-xs">Data scadenza</Label>
                        <DateInputIt value={dataScadenza} onChange={setDataScadenza} data-testid="comp-doc-data-scadenza" />
                    </div>
                    <div className="col-span-2">
                        <Label className="text-xs">File (PDF/IMG)</Label>
                        <Input type="file" accept=".pdf,image/*" key={fileKey} onChange={(e) => setFile(e.target.files?.[0] || null)} data-testid="comp-doc-file" />
                    </div>
                </div>
                <Button size="sm" className="mt-2 bg-sky-700 hover:bg-sky-800" onClick={aggiungi} data-testid="comp-doc-add-btn">
                    <Plus size={12} className="mr-1" /> Aggiungi
                </Button>
            </div>

            {(list || []).length === 0 ? (
                <div className="text-center text-xs text-slate-400 py-3">Nessun documento caricato</div>
            ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3" data-testid="comp-doc-cards">
                    {ordine.filter((t) => (gruppi[t] || []).length > 0).map((t) => (
                        <CompDocFolderCard key={t} tipologia={t} files={gruppi[t]} cid={cid}
                            onDelete={rimuovi} onAvviso={aggiornaAvviso} />
                    ))}
                </div>
            )}
        </div>
    );
}

function CompDocFolderCard({ tipologia, files, cid, onDelete, onAvviso }) {
    const [open, setOpen] = useState(true);
    return (
        <div className="border border-slate-200 rounded-lg overflow-hidden" data-testid={`comp-doc-folder-${tipologia}`}>
            <button onClick={() => setOpen((o) => !o)}
                className="w-full flex items-center gap-2 px-3 py-2.5 bg-slate-50 hover:bg-slate-100 transition-colors text-left"
                data-testid={`comp-doc-folder-toggle-${tipologia}`}>
                <FileText size={16} className="text-slate-500" />
                <span className="font-medium text-sm text-slate-800 flex-1">{tipologia}</span>
                <span className="text-[11px] px-2 py-0.5 rounded-full bg-slate-200 text-slate-600">{files.length}</span>
                <span className={`text-slate-400 transition-transform ${open ? "rotate-180" : ""}`}>▾</span>
            </button>
            {open && (
                <ul className="divide-y divide-slate-100 px-3">
                    {files.map((a) => {
                        const sc = compDocScadenza(a.data_scadenza);
                        return (
                            <li key={a.id} className="py-2.5 flex items-center gap-3" data-testid={`comp-doc-item-${a.id}`}>
                                <Paperclip size={15} className="text-slate-400 shrink-0" />
                                <div className="flex-1 min-w-0">
                                    {a.url ? (
                                        <a href={a.url} target="_blank" rel="noreferrer" className="text-sm text-sky-700 hover:underline truncate block">{a.nome_file || "Apri"}</a>
                                    ) : (
                                        <span className="text-sm text-slate-700 truncate block">{a.nome_file || "—"}</span>
                                    )}
                                    {a.descrizione && <div className="text-[11px] text-slate-500 truncate">{a.descrizione}</div>}
                                    <div className="flex flex-wrap items-center gap-1.5 mt-1">
                                        {a.data_rilascio && <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-100 text-slate-600">Rilascio: {new Date(a.data_rilascio + "T00:00:00").toLocaleDateString("it-IT")}</span>}
                                        {sc && <span className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${sc.cls}`} data-testid={`comp-doc-scadenza-${a.id}`}>{sc.label}</span>}
                                        <AvvisoScadenzaControl entita="compagnia" entitaId={cid} item={a} onChange={onAvviso} />
                                    </div>
                                </div>
                                <button onClick={() => onDelete(a.id)} className="text-red-600 hover:bg-red-50 p-1.5 rounded shrink-0" data-testid={`comp-doc-del-${a.id}`}>
                                    <Trash2 size={13} />
                                </button>
                            </li>
                        );
                    })}
                </ul>
            )}
        </div>
    );
}
