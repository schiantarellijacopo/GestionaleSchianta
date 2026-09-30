/**
 * Documenti Inbox — upload qualsiasi documento (CI, patente, CF, libretto,
 * polizza, fattura) e OCR auto-classifica + estrae dati + salva nella
 * sezione corretta.
 */
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { PageHeader, Loading, Empty } from "@/components/Shared";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import {
    Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
    Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from "@/components/ui/dialog";
import { Upload, FileText, Sparkles, CheckCircle2, X, Trash2, FileType2 } from "lucide-react";
import { toast } from "sonner";
import OcrScanWidget from "@/components/OcrScanWidget";

const TIPO_BADGE = {
    carta_identita: { l: "Carta d'identità", c: "bg-sky-100 text-sky-700" },
    patente: { l: "Patente", c: "bg-violet-100 text-violet-700" },
    codice_fiscale: { l: "Codice fiscale", c: "bg-emerald-100 text-emerald-700" },
    tessera_sanitaria: { l: "Tessera sanitaria", c: "bg-cyan-100 text-cyan-700" },
    passaporto: { l: "Passaporto", c: "bg-orange-100 text-orange-700" },
    visura_camerale: { l: "Visura camerale", c: "bg-teal-100 text-teal-700" },
    mandato_sdd: { l: "Mandato SDD", c: "bg-lime-100 text-lime-700" },
    libretto: { l: "Libretto", c: "bg-amber-100 text-amber-700" },
    polizza: { l: "Polizza", c: "bg-indigo-100 text-indigo-700" },
    condizioni: { l: "Condizioni", c: "bg-indigo-100 text-indigo-700" },
    appendice: { l: "Appendice", c: "bg-indigo-100 text-indigo-700" },
    atto_vendita: { l: "Atto di vendita", c: "bg-indigo-100 text-indigo-700" },
    quietanza: { l: "Quietanza", c: "bg-indigo-100 text-indigo-700" },
    mup: { l: "MUP", c: "bg-indigo-100 text-indigo-700" },
    questionario: { l: "Questionario", c: "bg-indigo-100 text-indigo-700" },
    preventivo: { l: "Preventivo", c: "bg-indigo-100 text-indigo-700" },
    fattura: { l: "Fattura", c: "bg-rose-100 text-rose-700" },
    cid: { l: "CID sinistro", c: "bg-red-100 text-red-700" },
    perizia: { l: "Perizia", c: "bg-red-100 text-red-700" },
    denuncia: { l: "Denuncia", c: "bg-red-100 text-red-700" },
    altro: { l: "Altro", c: "bg-slate-100 text-slate-700" },
};

// Card di destinazione per ciascuna entità (allineate ai detail)
const CARD_ANAG = [
    { k: "carta_identita", l: "Carta d'identità" }, { k: "patente", l: "Patente di guida" },
    { k: "passaporto", l: "Passaporto" }, { k: "codice_fiscale_doc", l: "Tessera codice fiscale" },
    { k: "tessera_sanitaria", l: "Tessera sanitaria" }, { k: "visura_camerale", l: "Visura camerale" },
    { k: "mandato_sdd", l: "Mandato SDD" }, { k: "autocertificazione_stato_famiglia", l: "Autocertificazione stato famiglia" },
    { k: "altro", l: "Altri documenti" },
];
const CARD_POL = [
    { k: "polizza", l: "Polizza" }, { k: "condizioni", l: "Condizioni" }, { k: "appendici", l: "Appendici" },
    { k: "libretto_veicolo", l: "Libretto veicolo" }, { k: "atto_vendita", l: "Atto di vendita" },
    { k: "quietanza", l: "Quietanze" }, { k: "mup", l: "MUP" }, { k: "questionario", l: "Questionario" },
    { k: "regolazione", l: "Regolazione" }, { k: "preventivo", l: "Preventivi" }, { k: "appunti", l: "Appunti" },
    { k: "altri", l: "Documenti altri (foto)" },
];
const CARD_SIN = [
    { k: "cid", l: "CID" }, { k: "perizia", l: "Perizia" }, { k: "foto", l: "Foto" },
    { k: "fattura", l: "Fattura" }, { k: "denuncia", l: "Denuncia" }, { k: "altri", l: "Documenti altri" },
];
const ROUTING = {
    carta_identita: ["anagrafica", "carta_identita"], patente: ["anagrafica", "patente"],
    passaporto: ["anagrafica", "passaporto"], codice_fiscale: ["anagrafica", "codice_fiscale_doc"],
    tessera_sanitaria: ["anagrafica", "tessera_sanitaria"], visura_camerale: ["anagrafica", "visura_camerale"],
    mandato_sdd: ["anagrafica", "mandato_sdd"], polizza: ["polizza", "polizza"], condizioni: ["polizza", "condizioni"],
    appendice: ["polizza", "appendici"], libretto: ["polizza", "libretto_veicolo"], atto_vendita: ["polizza", "atto_vendita"],
    quietanza: ["polizza", "quietanza"], mup: ["polizza", "mup"], questionario: ["polizza", "questionario"],
    preventivo: ["polizza", "preventivo"], fattura: ["polizza", "altri"], cid: ["sinistro", "cid"],
    perizia: ["sinistro", "perizia"], denuncia: ["sinistro", "denuncia"], altro: ["anagrafica", "altro"],
};
const CARDS_BY_ENTITA = { anagrafica: CARD_ANAG, polizza: CARD_POL, sinistro: CARD_SIN };

export default function DocumentiInbox() {
    const [items, setItems] = useState(null);
    const [uploading, setUploading] = useState(false);
    const [reviewing, setReviewing] = useState(null);
    const [dragActive, setDragActive] = useState(false);

    const load = () => api.get("/documenti-inbox").then((r) => setItems(r.data));
    useEffect(() => { load(); }, []);

    const upload = async (files, scope = null) => {
        if (!files?.length) return;
        setUploading(true);
        let okAuto = 0, okPending = 0;
        try {
            for (const file of files) {
                const fd = new FormData(); fd.append("file", file);
                if (scope) fd.append("scope", scope);
                try {
                    const r = await api.post("/documenti-inbox/analyze", fd, { headers: { "Content-Type": "multipart/form-data" } });
                    const tipoLabel = TIPO_BADGE[r.data.tipo_documento]?.l || r.data.tipo_documento || "documento";
                    if (r.data.auto_archiviato || r.data.stato === "salvato") {
                        okAuto++;
                        const tgt = r.data.salvato_in?.entita_tipo === "polizza"
                            ? `polizza ${r.data.target_polizza?.numero_polizza || ""}`
                            : `cliente ${r.data.target_anagrafica?.ragione_sociale || `${r.data.target_anagrafica?.cognome || ""} ${r.data.target_anagrafica?.nome || ""}`}`;
                        toast.success(`✓ ${file.name} → ${tipoLabel} archiviato in ${tgt}`);
                    } else {
                        okPending++;
                        toast.info(`${file.name} → ${tipoLabel} · da rivedere`);
                    }
                } catch (e) { toast.error(`${file.name}: ${e.response?.data?.detail || "Errore"}`); }
            }
            if (okAuto > 0 && okPending === 0) toast.success(`🚀 Tutti i ${okAuto} documenti archiviati automaticamente!`);
            else if (okAuto > 0 && okPending > 0) toast.info(`${okAuto} archiviati · ${okPending} da rivedere`);
            load();
        } finally { setUploading(false); }
    };

    const del = async (it) => {
        if (!window.confirm("Eliminare il documento dall'inbox?")) return;
        try { await api.delete(`/documenti-inbox/${it.id}`); toast.success("Eliminato"); load(); }
        catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
    };

    const pendingCount = (items || []).filter((i) => i.stato === "pending").length;
    const savedCount = (items || []).filter((i) => i.stato === "salvato").length;

    return (
        <div data-testid="documenti-inbox-page" className="space-y-5">
            <PageHeader
                title={<span className="flex items-center gap-2"><Sparkles className="text-violet-600" /> Documenti Inbox · OCR</span>}
                subtitle="Carica foto/PDF di documenti → OCR classifica + auto-compila i dati nella sezione corretta"
            />

            {/* Widget OCR scan Drive/OneDrive */}
            <OcrScanWidget variant="full" onClickPending={() => { window.location.hash = "#pending"; load(); }} />

            {/* 3 CARTELLE per entità: trascina qui i documenti e l'OCR li archivia nella card corretta */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4" data-testid="di-cartelle">
                {[
                    { scope: "anagrafica", label: "Anagrafiche", icon: "👤", hint: "CI, patente, CF, tessera, visura, mandato…", color: "sky" },
                    { scope: "polizza", label: "Polizze", icon: "📄", hint: "Polizza, condizioni, quietanze, libretto, MUP…", color: "indigo" },
                    { scope: "sinistro", label: "Sinistri", icon: "⚠️", hint: "CID, perizia, foto, fattura, denuncia…", color: "amber" },
                ].map((f) => (
                    <Card key={f.scope}
                        className={`p-4 border-2 border-dashed transition-colors ${dragActive === f.scope ? "border-violet-600 bg-violet-100" : "border-slate-300 bg-slate-50/50 hover:border-violet-300"}`}
                        onDragOver={(e) => { e.preventDefault(); setDragActive(f.scope); }}
                        onDragLeave={() => setDragActive(null)}
                        onDrop={(e) => {
                            e.preventDefault(); setDragActive(null);
                            const files = Array.from(e.dataTransfer.files || []);
                            if (files.length) upload(files, f.scope);
                        }}
                        data-testid={`di-cartella-${f.scope}`}>
                        <div className="text-center">
                            <div className="text-2xl mb-1">{f.icon}</div>
                            <div className="font-semibold text-sm text-slate-800">{f.label}</div>
                            <div className="text-[11px] text-slate-500 mb-3">{f.hint}</div>
                            <input type="file" id={`ifup-${f.scope}`} multiple accept="image/*,application/pdf" hidden
                                onChange={(e) => { upload(Array.from(e.target.files || []), f.scope); e.target.value = ""; }} />
                            <Button asChild size="sm" variant="outline" className="border-violet-300 text-violet-700 hover:bg-violet-50" disabled={uploading}>
                                <label htmlFor={`ifup-${f.scope}`} className="cursor-pointer" data-testid={`di-upload-${f.scope}`}>
                                    <Upload size={13} className="mr-1" /> Carica in {f.label}
                                </label>
                            </Button>
                        </div>
                    </Card>
                ))}
            </div>

            {/* DROPZONE generica (classificazione automatica su tutte le entità) */}
            <Card className={`p-6 border-2 border-dashed transition-colors ${dragActive === "any" ? "border-violet-600 bg-violet-100" : "border-violet-300 bg-gradient-to-br from-violet-50/50 to-sky-50/30"}`}
                onDragOver={(e) => { e.preventDefault(); setDragActive("any"); }}
                onDragLeave={() => setDragActive(null)}
                onDrop={(e) => {
                    e.preventDefault(); setDragActive(null);
                    const files = Array.from(e.dataTransfer.files || []);
                    if (files.length) upload(files);
                }}
                data-testid="di-dropzone">
                <div className="text-center">
                    <Upload size={32} className="text-violet-600 mx-auto mb-2" />
                    <p className="text-sm text-slate-700 font-medium mb-1">
                        Oppure trascina qui documenti misti (classificazione automatica su tutte le entità)
                    </p>
                    <p className="text-xs text-slate-500 mb-1">
                        Accetta più file contemporaneamente · PDF, JPG, PNG, WEBP
                    </p>
                    <p className="text-[11px] text-emerald-700 font-medium mb-4 inline-flex items-center gap-1">
                        ⚡ Auto-archiviazione: i documenti con OCR ad alta confidenza vengono spostati AUTOMATICAMENTE nella card corretta
                    </p>
                    <input type="file" id="ifup" multiple accept="image/*,application/pdf" hidden
                        onChange={(e) => { upload(Array.from(e.target.files || [])); e.target.value = ""; }} />
                    <Button asChild className="bg-violet-700 hover:bg-violet-800" disabled={uploading}>
                        <label htmlFor="ifup" className="cursor-pointer" data-testid="di-upload-btn">
                            <Upload size={14} className="mr-1" /> {uploading ? "Analisi in corso…" : "Carica documenti"}
                        </label>
                    </Button>
                </div>
            </Card>

            <div className="flex gap-2 text-sm items-center flex-wrap">
                <span className="text-violet-700 font-medium">⏳ Da rivedere: {pendingCount}</span>
                <span className="text-emerald-700 font-medium ml-3">✓ Salvati: {savedCount}</span>
                {pendingCount > 0 && (
                    <Button size="sm" variant="outline" className="ml-auto h-7 text-xs border-emerald-300 text-emerald-700 hover:bg-emerald-50"
                        onClick={async () => {
                            try {
                                const r = await api.post("/documenti-inbox/retry-auto-archive");
                                toast.success(`Auto-archiviati ${r.data.archived} · falliti ${r.data.failed}`);
                                load();
                            } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
                        }} data-testid="di-retry-auto">
                        ⚡ Riprova auto-archivio sui pending
                    </Button>
                )}
            </div>

            {items === null ? <Loading /> : items.length === 0 ? <Empty message="Nessun documento. Carica il primo!" /> : (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                    {items.map((it) => {
                        const b = TIPO_BADGE[it.tipo_documento] || TIPO_BADGE.altro;
                        return (
                            <Card key={it.id} className={`p-4 ${it.stato === "salvato" ? "opacity-60" : "hover:shadow-md transition"}`}
                                data-testid={`di-card-${it.id}`}>
                                <div className="flex items-start justify-between gap-2 mb-2">
                                    <div className="flex items-start gap-2 flex-1 min-w-0">
                                        <FileType2 size={20} className="text-violet-500 mt-0.5" />
                                        <div className="min-w-0">
                                            <div className="font-medium text-sm truncate">{it.filename}</div>
                                            <div className="text-[10px] text-slate-400">
                                                {(it.size / 1024).toFixed(0)} kB · {new Date(it.created_at).toLocaleString("it-IT")}
                                            </div>
                                        </div>
                                    </div>
                                    {it.stato === "salvato" ? <CheckCircle2 size={16} className="text-emerald-600" /> : null}
                                </div>
                                <div className="flex items-center gap-2 mb-2">
                                    <span className={`text-[10px] uppercase font-bold px-2 py-0.5 rounded ${b.c}`}>{b.l}</span>
                                    <span className={`text-[10px] ${it.confidenza === "alta" ? "text-emerald-600" : it.confidenza === "media" ? "text-amber-600" : "text-rose-600"}`}>
                                        conf. {it.confidenza || "?"}
                                    </span>
                                </div>
                                {it.target_anagrafica && (
                                    <div className="text-[11px] text-emerald-700 bg-emerald-50 p-1.5 rounded mb-1">
                                        ✓ Anagrafica trovata: <strong>{it.target_anagrafica.ragione_sociale || `${it.target_anagrafica.cognome} ${it.target_anagrafica.nome}`}</strong>
                                    </div>
                                )}
                                {it.target_polizza && (
                                    <div className="text-[11px] text-indigo-700 bg-indigo-50 p-1.5 rounded mb-1">
                                        ✓ Polizza trovata: <strong>{it.target_polizza.numero}</strong>
                                    </div>
                                )}
                                <div className="flex justify-between gap-1 mt-3 pt-3 border-t border-slate-100">
                                    {it.stato === "salvato" ? (
                                        <span className="text-xs text-emerald-700 font-medium">Archiviato in {it.salvato_in?.entita_tipo}</span>
                                    ) : (
                                        <Button size="sm" onClick={() => setReviewing(it)} className="bg-violet-700 hover:bg-violet-800"
                                            data-testid={`di-review-${it.id}`}>
                                            <FileText size={12} className="mr-1" /> Rivedi e archivia
                                        </Button>
                                    )}
                                    <button onClick={() => del(it)} className="text-rose-600 hover:bg-rose-50 p-1.5 rounded">
                                        <Trash2 size={13} />
                                    </button>
                                </div>
                            </Card>
                        );
                    })}
                </div>
            )}

            {reviewing && (
                <ReviewDialog item={reviewing} onClose={() => { setReviewing(null); load(); }} />
            )}
        </div>
    );
}

function ReviewDialog({ item, onClose }) {
    const [campi, setCampi] = useState(() => {
        const out = [];
        for (const [k, v] of Object.entries(item.dati || {})) {
            if (v !== null && v !== "" && typeof v !== "object") out.push(k);
        }
        return out;
    });
    const [route0Ent, route0Card] = ROUTING[item.tipo_documento] || ["anagrafica", "altro"];
    const [entitaTipo, setEntitaTipo] = useState(item.scope || route0Ent);
    const [categoria, setCategoria] = useState(
        (item.scope && item.scope !== route0Ent) ? ((CARDS_BY_ENTITA[item.scope] || [])[0] || {}).k : route0Card
    );
    const [anagId, setAnagId] = useState(item.target_anagrafica?.id || "");
    const [polId, setPolId] = useState(item.target_polizza?.id || "");
    const [sinId, setSinId] = useState("");
    const [salvaAvatar, setSalvaAvatar] = useState(true);
    const [anagSearch, setAnagSearch] = useState("");
    const [anagOptions, setAnagOptions] = useState([]);
    const [anagLabel, setAnagLabel] = useState(item.target_anagrafica ? (item.target_anagrafica.ragione_sociale || `${item.target_anagrafica.cognome || ""} ${item.target_anagrafica.nome || ""}`) : "");
    const [polOptions, setPolOptions] = useState([]);
    const [sinOptions, setSinOptions] = useState([]);

    useEffect(() => {
        if (anagSearch.length >= 2) {
            api.get(`/anagrafiche?q=${encodeURIComponent(anagSearch)}&limit=20`).then((r) => setAnagOptions(r.data));
        }
    }, [anagSearch]);

    useEffect(() => {
        if (anagId) {
            api.get(`/polizze?contraente_id=${anagId}&limit=50`).then((r) => setPolOptions(r.data)).catch(() => {});
            api.get(`/sinistri?contraente_id=${anagId}&limit=50`).then((r) => setSinOptions(r.data)).catch(() => {});
        }
    }, [anagId]);

    const toggle = (k) => setCampi((p) => p.includes(k) ? p.filter((x) => x !== k) : [...p, k]);

    const save = async () => {
        if (entitaTipo === "anagrafica" && !anagId) { toast.error("Seleziona un'anagrafica"); return; }
        if (entitaTipo === "polizza" && !polId) { toast.error("Seleziona una polizza"); return; }
        if (entitaTipo === "sinistro" && !sinId) { toast.error("Seleziona un sinistro"); return; }
        if (!categoria) { toast.error("Seleziona la card di destinazione"); return; }
        try {
            await api.post(`/documenti-inbox/${item.id}/save`, {
                entita_tipo: entitaTipo,
                categoria,
                anagrafica_id: anagId || null,
                polizza_id: entitaTipo === "polizza" ? polId : null,
                sinistro_id: entitaTipo === "sinistro" ? sinId : null,
                campi_da_applicare: campi,
                salva_avatar: salvaAvatar,
            });
            toast.success(`Archiviato in ${entitaTipo} · ${categoria}`); onClose();
        } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
    };

    const dati = item.dati || {};
    const cards = CARDS_BY_ENTITA[entitaTipo] || [];

    return (
        <Dialog open onOpenChange={(o) => !o && onClose()}>
            <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
                <DialogHeader>
                    <DialogTitle>Rivedi e archivia · {item.filename}</DialogTitle>
                </DialogHeader>
                <div className="space-y-4 py-2">
                    {/* DATI ESTRATTI */}
                    <div>
                        <Label className="text-xs uppercase tracking-wider text-slate-600">Dati estratti dall&apos;OCR</Label>
                        <div className="grid grid-cols-2 gap-1 mt-1">
                            {Object.entries(dati).filter(([_, v]) => v !== null && v !== "" && typeof v !== "object").map(([k, v]) => (
                                <label key={k} className={`flex items-center gap-2 p-2 border rounded text-xs cursor-pointer
                                    ${campi.includes(k) ? "bg-violet-50 border-violet-300" : "border-slate-200"}`}>
                                    <Checkbox checked={campi.includes(k)} onCheckedChange={() => toggle(k)} />
                                    <div className="flex-1 min-w-0">
                                        <div className="font-semibold text-slate-700 text-[10px] uppercase">{k.replace(/_/g, " ")}</div>
                                        <div className="font-mono truncate">{String(v)}</div>
                                    </div>
                                </label>
                            ))}
                        </div>
                    </div>

                    {/* DESTINAZIONE */}
                    <div className="space-y-3 border-t pt-3">
                        <Label className="text-xs uppercase tracking-wider text-slate-600">Destinazione · entità e card</Label>

                        {/* Tipo entità */}
                        <div className="flex gap-2">
                            {["anagrafica", "polizza", "sinistro"].map((et) => (
                                <button key={et} type="button" onClick={() => { setEntitaTipo(et); setCategoria((CARDS_BY_ENTITA[et][0] || {}).k); }}
                                    className={`flex-1 text-xs py-1.5 rounded border capitalize ${entitaTipo === et ? "bg-violet-700 text-white border-violet-700" : "bg-white border-slate-200 text-slate-600"}`}
                                    data-testid={`di-entita-${et}`}>{et}</button>
                            ))}
                        </div>

                        {/* Card di destinazione */}
                        <div>
                            <Label>Card di destinazione</Label>
                            <Select value={categoria} onValueChange={setCategoria}>
                                <SelectTrigger data-testid="di-card-select"><SelectValue placeholder="Seleziona card" /></SelectTrigger>
                                <SelectContent>
                                    {cards.map((c) => <SelectItem key={c.k} value={c.k}>{c.l}</SelectItem>)}
                                </SelectContent>
                            </Select>
                        </div>

                        {/* Anagrafica (sempre richiesta come riferimento cliente) */}
                        <div>
                            <Label>Cliente / Anagrafica</Label>
                            {anagId ? (
                                <div className="flex items-center gap-2 p-2 bg-emerald-50 border border-emerald-300 rounded">
                                    <CheckCircle2 size={14} className="text-emerald-600" />
                                    <span className="text-sm">{anagLabel || `${anagId.slice(0, 8)}…`}</span>
                                    <button onClick={() => { setAnagId(""); setPolId(""); setSinId(""); }} className="ml-auto text-rose-600"><X size={12} /></button>
                                </div>
                            ) : (
                                <>
                                    <Input value={anagSearch} onChange={(e) => setAnagSearch(e.target.value)}
                                        placeholder="Cerca anagrafica (min 2 lettere)..." data-testid="di-anag-search" />
                                    {anagOptions.length > 0 && (
                                        <div className="border border-slate-200 rounded mt-1 max-h-32 overflow-y-auto">
                                            {anagOptions.map((a) => (
                                                <button key={a.id} onClick={() => { setAnagId(a.id); setAnagLabel(a.ragione_sociale || `${a.cognome || ""} ${a.nome || ""}`); setAnagSearch(""); setAnagOptions([]); }}
                                                    className="w-full text-left p-2 hover:bg-slate-50 text-xs border-b border-slate-100">
                                                    {a.ragione_sociale || `${a.cognome || ""} ${a.nome || ""}`}
                                                </button>
                                            ))}
                                        </div>
                                    )}
                                </>
                            )}
                        </div>

                        {/* Polizza — richiesta se entità = polizza */}
                        {entitaTipo === "polizza" && anagId && (
                            <div>
                                <Label>Polizza</Label>
                                <Select value={polId} onValueChange={setPolId}>
                                    <SelectTrigger data-testid="di-pol-select"><SelectValue placeholder="Seleziona polizza" /></SelectTrigger>
                                    <SelectContent>
                                        {polOptions.map((p) => <SelectItem key={p.id} value={p.id}>{p.numero || p.numero_polizza} · {p.ramo}</SelectItem>)}
                                    </SelectContent>
                                </Select>
                            </div>
                        )}

                        {/* Sinistro — richiesto se entità = sinistro */}
                        {entitaTipo === "sinistro" && anagId && (
                            <div>
                                <Label>Sinistro</Label>
                                <Select value={sinId} onValueChange={setSinId}>
                                    <SelectTrigger data-testid="di-sin-select"><SelectValue placeholder="Seleziona sinistro" /></SelectTrigger>
                                    <SelectContent>
                                        {sinOptions.map((s) => <SelectItem key={s.id} value={s.id}>{s.numero_sinistro || s.id.slice(0, 8)} · {s.tipologia_sinistro || s.ramo || ""}</SelectItem>)}
                                    </SelectContent>
                                </Select>
                                {sinOptions.length === 0 && <div className="text-[10px] text-amber-600 mt-1">Nessun sinistro per questo cliente</div>}
                            </div>
                        )}

                        {/* AVATAR option per documenti con foto */}
                        {["carta_identita", "patente", "passaporto", "tessera_sanitaria"].includes(item.tipo_documento) && item.foto_volto_bbox && (
                            <div className="bg-violet-50 border border-violet-200 rounded p-2">
                                <label className="flex items-center gap-2 cursor-pointer">
                                    <Checkbox checked={salvaAvatar} onCheckedChange={(v) => setSalvaAvatar(!!v)} data-testid="di-avatar-chk" />
                                    <span className="text-sm">📸 Salva la foto come avatar dell&apos;anagrafica</span>
                                </label>
                            </div>
                        )}
                    </div>
                </div>
                <DialogFooter>
                    <Button variant="outline" onClick={onClose}>Annulla</Button>
                    <Button onClick={save} className="bg-violet-700 hover:bg-violet-800" data-testid="di-save">
                        <CheckCircle2 size={14} className="mr-1" /> Archivia nella card
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}
