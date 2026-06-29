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

const TIPO_BADGE = {
    carta_identita: { l: "Carta d'identità", c: "bg-sky-100 text-sky-700" },
    patente: { l: "Patente", c: "bg-violet-100 text-violet-700" },
    codice_fiscale: { l: "Codice fiscale", c: "bg-emerald-100 text-emerald-700" },
    libretto: { l: "Libretto", c: "bg-amber-100 text-amber-700" },
    polizza: { l: "Polizza", c: "bg-indigo-100 text-indigo-700" },
    fattura: { l: "Fattura", c: "bg-rose-100 text-rose-700" },
    tessera_sanitaria: { l: "Tessera sanitaria", c: "bg-cyan-100 text-cyan-700" },
    passaporto: { l: "Passaporto", c: "bg-orange-100 text-orange-700" },
    altro: { l: "Altro", c: "bg-slate-100 text-slate-700" },
};

export default function DocumentiInbox() {
    const [items, setItems] = useState(null);
    const [uploading, setUploading] = useState(false);
    const [reviewing, setReviewing] = useState(null);
    const [dragActive, setDragActive] = useState(false);

    const load = () => api.get("/documenti-inbox").then((r) => setItems(r.data));
    useEffect(() => { load(); }, []);

    const upload = async (files) => {
        if (!files?.length) return;
        setUploading(true);
        let okAuto = 0, okPending = 0;
        try {
            for (const file of files) {
                const fd = new FormData(); fd.append("file", file);
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

            {/* DROPZONE */}
            <Card className={`p-6 border-2 border-dashed transition-colors ${dragActive ? "border-violet-600 bg-violet-100" : "border-violet-300 bg-gradient-to-br from-violet-50/50 to-sky-50/30"}`}
                onDragOver={(e) => { e.preventDefault(); setDragActive(true); }}
                onDragLeave={() => setDragActive(false)}
                onDrop={(e) => {
                    e.preventDefault(); setDragActive(false);
                    const files = Array.from(e.dataTransfer.files || []);
                    if (files.length) upload(files);
                }}
                data-testid="di-dropzone">
                <div className="text-center">
                    <Upload size={32} className="text-violet-600 mx-auto mb-2" />
                    <p className="text-sm text-slate-700 font-medium mb-1">
                        Trascina qui o carica documenti (Carta d&apos;identità, patente, CF, libretto, polizza, fattura…)
                    </p>
                    <p className="text-xs text-slate-500 mb-1">
                        Accetta più file contemporaneamente · PDF, JPG, PNG, WEBP
                    </p>
                    <p className="text-[11px] text-emerald-700 font-medium mb-4 inline-flex items-center gap-1">
                        ⚡ Auto-archiviazione: i documenti con OCR ad alta confidenza vengono spostati AUTOMATICAMENTE nella sezione corretta del cliente
                    </p>
                    <input type="file" id="ifup" multiple accept="image/*,application/pdf" hidden
                        onChange={(e) => upload(Array.from(e.target.files || []))} />
                    <Button asChild className="bg-violet-700 hover:bg-violet-800" disabled={uploading}>
                        <label htmlFor="ifup" className="cursor-pointer" data-testid="di-upload-btn">
                            <Upload size={14} className="mr-1" /> {uploading ? "Analisi in corso…" : "Carica documenti"}
                        </label>
                    </Button>
                </div>
            </Card>

            <div className="flex gap-2 text-sm">
                <span className="text-violet-700 font-medium">⏳ Da rivedere: {pendingCount}</span>
                <span className="text-emerald-700 font-medium ml-3">✓ Salvati: {savedCount}</span>
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
        // Per default seleziona tutti i campi con valore
        const out = [];
        for (const [k, v] of Object.entries(item.dati || {})) {
            if (v !== null && v !== "" && typeof v !== "object") out.push(k);
        }
        return out;
    });
    const [anagId, setAnagId] = useState(item.target_anagrafica?.id || "");
    const [polId, setPolId] = useState(item.target_polizza?.id || "");
    const [salvaAvatar, setSalvaAvatar] = useState(true);
    const [anagSearch, setAnagSearch] = useState("");
    const [anagOptions, setAnagOptions] = useState([]);
    const [polOptions, setPolOptions] = useState([]);

    useEffect(() => {
        if (anagSearch.length >= 2) {
            api.get(`/anagrafiche?q=${encodeURIComponent(anagSearch)}&limit=20`).then((r) => setAnagOptions(r.data));
        }
    }, [anagSearch]);

    useEffect(() => {
        if (anagId) {
            api.get(`/polizze?contraente_id=${anagId}&limit=50`).then((r) => setPolOptions(r.data));
        }
    }, [anagId]);

    const toggle = (k) => setCampi((p) => p.includes(k) ? p.filter((x) => x !== k) : [...p, k]);

    const save = async () => {
        if (!anagId && !polId) { toast.error("Seleziona almeno un'anagrafica o polizza di destinazione"); return; }
        try {
            await api.post(`/documenti-inbox/${item.id}/save`, {
                anagrafica_id: anagId || null,
                polizza_id: polId || null,
                campi_da_applicare: campi,
            });
            toast.success("Documento archiviato e campi applicati"); onClose();
        } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
    };

    const dati = item.dati || {};

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
                    <div className="space-y-2 border-t pt-3">
                        <Label className="text-xs uppercase tracking-wider text-slate-600">Destinazione · dove salvare</Label>

                        <div>
                            <Label>Anagrafica</Label>
                            {item.target_anagrafica ? (
                                <div className="flex items-center gap-2 p-2 bg-emerald-50 border border-emerald-300 rounded">
                                    <CheckCircle2 size={14} className="text-emerald-600" />
                                    <span className="text-sm">{item.target_anagrafica.ragione_sociale || `${item.target_anagrafica.cognome} ${item.target_anagrafica.nome}`}</span>
                                    <button onClick={() => setAnagId("")} className="ml-auto text-rose-600"><X size={12} /></button>
                                </div>
                            ) : (
                                <>
                                    <Input value={anagSearch} onChange={(e) => setAnagSearch(e.target.value)}
                                        placeholder="Cerca anagrafica (min 2 lettere)..." data-testid="di-anag-search" />
                                    {anagOptions.length > 0 && (
                                        <div className="border border-slate-200 rounded mt-1 max-h-32 overflow-y-auto">
                                            {anagOptions.map((a) => (
                                                <button key={a.id} onClick={() => { setAnagId(a.id); setAnagSearch(""); setAnagOptions([]); }}
                                                    className="w-full text-left p-2 hover:bg-slate-50 text-xs border-b border-slate-100">
                                                    {a.ragione_sociale || `${a.cognome || ""} ${a.nome || ""}`}
                                                </button>
                                            ))}
                                        </div>
                                    )}
                                    {anagId && !item.target_anagrafica && <div className="text-[10px] text-emerald-700 mt-1">✓ Selezionata: {anagId.slice(0, 8)}…</div>}
                                </>
                            )}
                        </div>

                        {anagId && polOptions.length > 0 && (
                            <div>
                                <Label>Polizza (opzionale)</Label>
                                <Select value={polId} onValueChange={setPolId}>
                                    <SelectTrigger><SelectValue placeholder="Seleziona polizza" /></SelectTrigger>
                                    <SelectContent>
                                        <SelectItem value="">— Nessuna —</SelectItem>
                                        {polOptions.map((p) => <SelectItem key={p.id} value={p.id}>{p.numero} · {p.ramo}</SelectItem>)}
                                    </SelectContent>
                                </Select>
                            </div>
                        )}

                        {/* AVATAR option per documenti con foto */}
                        {["carta_identita", "patente", "passaporto", "tessera_sanitaria"].includes(item.tipo_documento) && item.foto_volto_bbox && (
                            <div className="bg-violet-50 border border-violet-200 rounded p-2">
                                <label className="flex items-center gap-2 cursor-pointer">
                                    <Checkbox checked={salvaAvatar} onCheckedChange={(v) => setSalvaAvatar(!!v)} data-testid="di-avatar-chk" />
                                    <span className="text-sm">📸 Salva la foto come avatar dell&apos;anagrafica</span>
                                </label>
                                <div className="text-[10px] text-slate-500 mt-1 ml-6">
                                    Verrà ritagliato il volto e impostato come avatar del cliente.
                                </div>
                            </div>
                        )}
                    </div>
                </div>
                <DialogFooter>
                    <Button variant="outline" onClick={onClose}>Annulla</Button>
                    <Button onClick={save} className="bg-violet-700 hover:bg-violet-800" data-testid="di-save">
                        <CheckCircle2 size={14} className="mr-1" /> Archivia + applica dati
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}
