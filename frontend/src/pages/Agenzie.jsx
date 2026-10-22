/**
 * Agenzie — libreria delle agenzie partner. Si definisce qui l'agenzia
 * principale dello studio + le agenzie con cui collaboriamo (mandato indiretto).
 */
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { PageHeader, Empty, Loading } from "@/components/Shared";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import {
    Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
    Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogTrigger,
} from "@/components/ui/dialog";
import { Plus, Building2, Edit, Trash2, Crown, Handshake, Link2, Upload, FileText, Paperclip } from "lucide-react";
import { toast } from "sonner";
import AvvisoScadenzaControl from "@/components/AvvisoScadenzaControl";

const RAPPORTO_LABEL = {
    mandato_diretto: "Mandato diretto",
    lettera_incarico: "Lettera di incarico",
    collaborazione_orizzontale: "Collaborazione orizzontale",
    mandato_non_assicurativo: "Mandato non assicurativo",
};

export default function Agenzie() {
    const [list, setList] = useState(null);
    const [open, setOpen] = useState(false);
    const [editing, setEditing] = useState(null);

    const load = () => api.get("/agenzie").then((r) => setList(r.data));
    useEffect(() => { load(); }, []);

    const del = async (a) => {
        if (!window.confirm(`Eliminare agenzia ${a.ragione_sociale}?`)) return;
        try { await api.delete(`/agenzie/${a.id}`); toast.success("Eliminata"); load(); }
        catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
    };

    const principale = (list || []).find((a) => a.tipo === "principale");
    const partner = (list || []).filter((a) => a.tipo === "partner");

    return (
        <div data-testid="agenzie-page" className="space-y-5">
            <PageHeader
                title="Agenzie"
                subtitle="Agenzia principale e agenzie partner (collaborazioni con mandati indiretti)"
                actions={
                    <Dialog open={open} onOpenChange={(o) => { if (!o) { setEditing(null); load(); } setOpen(o); }}>
                        <DialogTrigger asChild>
                            <Button onClick={() => setEditing(null)} className="bg-sky-700 hover:bg-sky-800" data-testid="age-new">
                                <Plus size={14} className="mr-1" /> Nuova agenzia
                            </Button>
                        </DialogTrigger>
                        <AgenziaDialog key={editing?.id || "new"} editing={editing} principaleExists={!!principale}
                            onClose={() => { setOpen(false); setEditing(null); load(); }} />
                    </Dialog>
                }
            />

            {list === null ? <Loading /> : (
                <>
                    {/* AGENZIA PRINCIPALE */}
                    <div>
                        <h2 className="text-sm font-semibold uppercase tracking-wider text-amber-700 mb-2 flex items-center gap-2">
                            <Crown size={16} /> Agenzia principale
                        </h2>
                        {!principale ? (
                            <Card className="p-4 border-dashed border-2 border-amber-200 bg-amber-50/30">
                                <div className="text-sm text-slate-500">
                                    Non hai ancora definito l'agenzia principale.
                                    <Button size="sm" variant="link" className="ml-1 px-0"
                                        onClick={() => { setEditing({ tipo: "principale" }); setOpen(true); }}
                                        data-testid="age-create-principale">
                                        Crea agenzia principale →
                                    </Button>
                                </div>
                            </Card>
                        ) : (
                            <AgenziaCard a={principale} onEdit={() => { setEditing(principale); setOpen(true); }}
                                onDelete={del} testid="age-principale" />
                        )}
                    </div>

                    {/* PARTNER */}
                    <div>
                        <h2 className="text-sm font-semibold uppercase tracking-wider text-slate-700 mb-2 flex items-center gap-2">
                            <Handshake size={16} /> Agenzie partner ({partner.length})
                        </h2>
                        {partner.length === 0 ? <Empty message="Nessuna agenzia partner. Aggiungine una per gestire i mandati di collaborazione." /> : (
                            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                                {partner.map((a) => (
                                    <AgenziaCard key={a.id} a={a}
                                        onEdit={() => { setEditing(a); setOpen(true); }}
                                        onDelete={del} testid={`age-partner-${a.id}`} />
                                ))}
                            </div>
                        )}
                    </div>
                </>
            )}
        </div>
    );
}

function AgenziaCard({ a, onEdit, onDelete, testid }) {
    const [collegaOpen, setCollegaOpen] = useState(false);
    return (
        <Card className={`p-4 ${a.tipo === "principale" ? "border-l-4 border-amber-400" : ""}`} data-testid={testid}>
            <div className="flex items-start justify-between gap-2">
                <div className="flex items-center gap-2 flex-1 min-w-0">
                    <div className={`w-10 h-10 rounded-md flex items-center justify-center
                        ${a.tipo === "principale" ? "bg-amber-50 text-amber-700" : "bg-slate-50 text-slate-700"}`}>
                        {a.tipo === "principale" ? <Crown size={18} /> : <Building2 size={18} />}
                    </div>
                    <div className="flex-1 min-w-0">
                        <div className="font-medium text-slate-900 truncate">{a.ragione_sociale}</div>
                        {a.codice && <div className="text-xs text-slate-400 font-mono">{a.codice}</div>}
                    </div>
                </div>
                <div className="flex gap-1">
                    <button onClick={onEdit} data-testid={`age-edit-${a.id}`} className="text-sky-700 hover:bg-sky-50 p-1.5 rounded"><Edit size={13} /></button>
                    <button onClick={() => onDelete(a)} data-testid={`age-del-${a.id}`} className="text-rose-600 hover:bg-rose-50 p-1.5 rounded"><Trash2 size={13} /></button>
                </div>
            </div>
            <div className="mt-2 text-xs text-slate-600 space-y-0.5">
                {a.referente && <div>Referente: <span className="font-medium">{a.referente}</span></div>}
                {a.email && <div>{a.email}</div>}
                {a.telefono && <div className="font-mono">{a.telefono}</div>}
                {a.citta && <div>{a.citta} {a.provincia ? `(${a.provincia})` : ""}</div>}
                {a.partita_iva && <div>P.IVA: <span className="font-mono">{a.partita_iva}</span></div>}
                {a.tipo_rapporto && <div>Rapporto: <span className="font-medium">{RAPPORTO_LABEL[a.tipo_rapporto] || a.tipo_rapporto}</span></div>}
                {a.autorizzato_incasso && <div>Autorizzato incasso: <span className="font-medium">{a.autorizzato_incasso === "si" ? "Sì" : "No"}</span></div>}
                {a.rui_ivass && <div>RUI/IVASS: <span className="font-mono">{a.rui_ivass}</span></div>}
                {(a.documenti || []).length > 0 && (
                    <div className="flex items-center gap-1 text-slate-500"><FileText size={12} /> {a.documenti.length} {a.documenti.length === 1 ? "documento" : "documenti"}</div>
                )}
                {a.perc_ritenuta_acconto > 0 && (
                    <div className="text-rose-700 font-medium">Ritenuta acconto: {a.perc_ritenuta_acconto}%</div>
                )}
            </div>
            {a.tipo === "partner" && (
                <div className="mt-2 pt-2 border-t border-slate-100 text-xs flex items-center justify-between">
                    <div>
                        <span className="text-slate-500">Compagnie collegate: </span>
                        <span className="font-bold text-sky-700">{a.n_compagnie_collegate || 0}</span>
                    </div>
                    <Button size="sm" variant="outline" onClick={() => setCollegaOpen(true)}
                        data-testid={`age-collega-${a.id}`}>
                        <Link2 size={11} className="mr-1" /> Collega compagnie
                    </Button>
                </div>
            )}
            {a.tipo === "principale" && (
                <div className="mt-2 pt-2 border-t border-slate-100 text-xs flex items-center justify-between">
                    <div>
                        <span className="text-slate-500">Compagnie con mandato diretto: </span>
                        <span className="font-bold text-amber-700">{a.n_compagnie_collegate || 0}</span>
                    </div>
                    <Button size="sm" variant="outline" onClick={() => setCollegaOpen(true)}
                        data-testid={`age-collega-${a.id}`}>
                        <Link2 size={11} className="mr-1" /> Collega compagnie
                    </Button>
                </div>
            )}
            {collegaOpen && <CollegaCompagnieDialog agenzia={a} onClose={() => setCollegaOpen(false)} />}
        </Card>
    );
}

function CollegaCompagnieDialog({ agenzia, onClose }) {
    const isPrincipale = agenzia.tipo === "principale";
    const [comps, setComps] = useState(null);
    const [collegate, setCollegate] = useState(new Set());
    useEffect(() => {
        api.get("/compagnie").then((r) => {
            setComps(r.data);
            const partnersOf = (c) => (c.agenzie_partner_ids && c.agenzie_partner_ids.length)
                ? c.agenzie_partner_ids
                : (c.agenzia_partner_id ? [c.agenzia_partner_id] : []);
            const iniz = (r.data || []).filter((c) =>
                isPrincipale ? partnersOf(c).length === 0 : partnersOf(c).includes(agenzia.id),
            ).map((c) => c.id);
            setCollegate(new Set(iniz));
        });
    }, [agenzia.id]);

    const partnersOf = (c) => (c.agenzie_partner_ids && c.agenzie_partner_ids.length)
        ? c.agenzie_partner_ids
        : (c.agenzia_partner_id ? [c.agenzia_partner_id] : []);

    const toggle = (id) => {
        setCollegate((p) => {
            const n = new Set(p);
            if (n.has(id)) n.delete(id);
            else n.add(id);
            return n;
        });
    };

    const save = async () => {
        try {
            for (const c of comps) {
                const wantLinked = collegate.has(c.id);
                const partners = partnersOf(c);
                if (isPrincipale) {
                    // "Mandato diretto" = nessuna agenzia partner. Se selezioni una
                    // compagnia che ha partner, la riporti a diretto (pulisci i partner).
                    if (wantLinked && partners.length) {
                        await api.put(`/compagnie/${c.id}`, { ...c, tipo_mandato: "diretto", agenzia_partner_id: null, agenzie_partner_ids: [] });
                    }
                } else {
                    const linked = partners.includes(agenzia.id);
                    if (wantLinked && !linked) {
                        const next = [...partners, agenzia.id];
                        await api.put(`/compagnie/${c.id}`, { ...c, tipo_mandato: "collaborazione", agenzia_partner_id: null, agenzie_partner_ids: next });
                    } else if (!wantLinked && linked) {
                        const next = partners.filter((id) => id !== agenzia.id);
                        await api.put(`/compagnie/${c.id}`, { ...c, agenzia_partner_id: null, agenzie_partner_ids: next, tipo_mandato: next.length ? "collaborazione" : "diretto" });
                    }
                }
            }
            toast.success("Collegamenti aggiornati"); onClose();
        } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
    };

    return (
        <Dialog open onOpenChange={(o) => !o && onClose()}>
            <DialogContent className="max-w-xl max-h-[80vh] overflow-y-auto">
                <DialogHeader><DialogTitle>
                    {isPrincipale
                        ? `Compagnie con mandato diretto — ${agenzia.ragione_sociale}`
                        : `Collega compagnie a ${agenzia.ragione_sociale}`}
                </DialogTitle></DialogHeader>
                <div className="space-y-2 py-2">
                    <div className="text-xs text-slate-600 bg-amber-50 border border-amber-200 p-2 rounded">
                        {isPrincipale ? (
                            <>Le compagnie selezionate diventano <strong>mandato diretto</strong> con l&apos;agenzia principale.
                            Selezionandone una collegata a un&apos;agenzia partner, la si riporta a mandato diretto.
                            Per spostare una compagnia su un&apos;agenzia partner usa il pulsante &quot;Collega compagnie&quot; della partner.</>
                        ) : (
                            <>Le compagnie selezionate diventano <strong>mandato di collaborazione</strong> via questa agenzia.
                            Le compagnie deselezionate tornano a mandato diretto.</>
                        )}
                    </div>
                    {comps === null ? <Loading /> : (
                        <div className="grid grid-cols-1 gap-1 max-h-96 overflow-y-auto">
                            {comps.map((c) => (
                                <label key={c.id} className={`flex items-center gap-2 p-2 border rounded cursor-pointer text-sm
                                    ${collegate.has(c.id) ? "bg-sky-50 border-sky-400" : "border-slate-200"}`}>
                                    <Checkbox checked={collegate.has(c.id)} onCheckedChange={() => toggle(c.id)} />
                                    <div className="flex-1">
                                        <div className="font-medium">{c.ragione_sociale}</div>
                                        <div className="text-[10px] text-slate-400 font-mono">{c.codice}</div>
                                    </div>
                                    {isPrincipale
                                        ? (partnersOf(c).length > 0 && (
                                            <span className="text-[10px] text-amber-700">⚠ collegata a un&apos;agenzia partner</span>
                                        ))
                                        : (partnersOf(c).some((id) => id !== agenzia.id) && !partnersOf(c).includes(agenzia.id) && (
                                            <span className="text-[10px] text-amber-700">⚠ già collegata ad altra agenzia</span>
                                        ))}
                                </label>
                            ))}
                        </div>
                    )}
                </div>
                <DialogFooter>
                    <Button variant="outline" onClick={onClose}>Annulla</Button>
                    <Button onClick={save} className="bg-sky-700 hover:bg-sky-800" data-testid="age-collega-save">
                        Salva collegamenti ({collegate.size})
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}

function AgenziaDialog({ editing, principaleExists, onClose }) {
    const [f, setF] = useState(editing || {
        ragione_sociale: "", codice: "", tipo: "partner",
        referente: "", email: "", telefono: "", indirizzo: "", citta: "", provincia: "", cap: "",
        partita_iva: "", codice_fiscale: "", iban: "", note: "", attiva: true,
        perc_ritenuta_acconto: 0, compagnie_ids: [],
    });
    const [compagnie, setCompagnie] = useState([]);
    useEffect(() => {
        api.get("/compagnie").then((r) => setCompagnie((r.data || []).filter((c) => c.attiva !== false))).catch(() => {});
    }, []);
    const set = (k, v) => setF((p) => ({ ...p, [k]: v }));
    const toggleComp = (id) => {
        const cur = f.compagnie_ids || [];
        set("compagnie_ids", cur.includes(id) ? cur.filter((x) => x !== id) : [...cur, id]);
    };
    const save = async () => {
        if (!f.ragione_sociale.trim()) { toast.error("Ragione sociale obbligatoria"); return; }
        try {
            const payload = { ...f, compagnie_ids: f.compagnie_ids || [] };
            if (editing?.id) await api.put(`/agenzie/${editing.id}`, payload);
            else await api.post("/agenzie", payload);
            toast.success(editing?.id ? "Aggiornata" : "Creata"); onClose();
        } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
    };
    const canBePrincipale = !principaleExists || editing?.tipo === "principale";
    return (
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
            <DialogHeader><DialogTitle>{editing?.id ? "Modifica" : "Nuova"} agenzia</DialogTitle></DialogHeader>
            <div className="grid grid-cols-2 gap-3 py-2">
                <div className="col-span-2">
                    <Label>Tipo *</Label>
                    <Select value={f.tipo} onValueChange={(v) => set("tipo", v)}>
                        <SelectTrigger data-testid="age-tipo"><SelectValue /></SelectTrigger>
                        <SelectContent>
                            {canBePrincipale && <SelectItem value="principale">Agenzia principale (la mia)</SelectItem>}
                            <SelectItem value="partner">Agenzia partner (collaborazione)</SelectItem>
                        </SelectContent>
                    </Select>
                </div>
                <div className="col-span-2"><Label>Ragione sociale *</Label>
                    <Input value={f.ragione_sociale} onChange={(e) => set("ragione_sociale", e.target.value)} data-testid="age-rs" /></div>
                <div><Label>Codice</Label>
                    <Input value={f.codice || ""} onChange={(e) => set("codice", e.target.value.toUpperCase())} /></div>
                <div><Label>Referente</Label>
                    <Input value={f.referente || ""} onChange={(e) => set("referente", e.target.value)} /></div>
                <div><Label>Email</Label>
                    <Input value={f.email || ""} onChange={(e) => set("email", e.target.value)} /></div>
                <div><Label>Telefono</Label>
                    <Input value={f.telefono || ""} onChange={(e) => set("telefono", e.target.value)} /></div>
                <div><Label>Indirizzo</Label>
                    <Input value={f.indirizzo || ""} onChange={(e) => set("indirizzo", e.target.value)} /></div>
                <div><Label>CAP</Label>
                    <Input value={f.cap || ""} onChange={(e) => set("cap", e.target.value)} /></div>
                <div><Label>Città</Label>
                    <Input value={f.citta || ""} onChange={(e) => set("citta", e.target.value)} /></div>
                <div><Label>Provincia</Label>
                    <Input value={f.provincia || ""} onChange={(e) => set("provincia", e.target.value.toUpperCase())} maxLength={2} /></div>
                <div><Label>Partita IVA</Label>
                    <Input value={f.partita_iva || ""} onChange={(e) => set("partita_iva", e.target.value)} /></div>
                <div><Label>Codice fiscale</Label>
                    <Input value={f.codice_fiscale || ""} onChange={(e) => set("codice_fiscale", e.target.value.toUpperCase())} /></div>
                <div className="col-span-2"><Label>IBAN</Label>
                    <Input value={f.iban || ""} onChange={(e) => set("iban", e.target.value.toUpperCase())} /></div>
                <div className="col-span-2"><Label>Note</Label>
                    <Input value={f.note || ""} onChange={(e) => set("note", e.target.value)} /></div>

                {/* Dati del mandato */}
                {f.tipo === "partner" && (<>
                <div className="col-span-2 pt-1 mt-1 border-t border-slate-100">
                    <div className="text-xs font-semibold uppercase tracking-wider text-slate-500 mb-1">Dati del mandato</div>
                </div>
                <div>
                    <Label>Tipo di rapporto</Label>
                    <Select value={f.tipo_rapporto || ""} onValueChange={(v) => set("tipo_rapporto", v)}>
                        <SelectTrigger data-testid="age-tipo-rapporto"><SelectValue placeholder="— Seleziona —" /></SelectTrigger>
                        <SelectContent>
                            <SelectItem value="mandato_diretto">Mandato diretto</SelectItem>
                            <SelectItem value="lettera_incarico">Lettera di incarico</SelectItem>
                            <SelectItem value="collaborazione_orizzontale">Collaborazione orizzontale</SelectItem>
                            <SelectItem value="mandato_non_assicurativo">Mandato non assicurativo</SelectItem>
                        </SelectContent>
                    </Select>
                </div>
                <div>
                    <Label>Autorizzato all'incasso?</Label>
                    <Select value={f.autorizzato_incasso || ""} onValueChange={(v) => set("autorizzato_incasso", v)}>
                        <SelectTrigger data-testid="age-autorizzato-incasso"><SelectValue placeholder="— Seleziona —" /></SelectTrigger>
                        <SelectContent>
                            <SelectItem value="si">Sì</SelectItem>
                            <SelectItem value="no">No</SelectItem>
                        </SelectContent>
                    </Select>
                </div>
                <div><Label>Denominazione sociale</Label>
                    <Input value={f.denominazione_sociale || ""} onChange={(e) => set("denominazione_sociale", e.target.value)} data-testid="age-denominazione" /></div>
                <div><Label>Numero iscrizione RUI / IVASS</Label>
                    <Input value={f.rui_ivass || ""} onChange={(e) => set("rui_ivass", e.target.value)} data-testid="age-rui-ivass" /></div>
                </>)}

                <div>
                    <Label className="text-rose-700">Ritenuta d'acconto % (auto su fatture)</Label>
                    <Input type="number" step="0.01" min="0" max="100"
                        value={f.perc_ritenuta_acconto || 0}
                        onChange={(e) => set("perc_ritenuta_acconto", parseFloat(e.target.value) || 0)}
                        data-testid="age-perc-ritenuta"
                        placeholder="es. 23" />
                    <div className="text-[10px] text-slate-500 mt-1">
                        Verrà applicata automaticamente alle fatture provvigioni emesse dall'agenzia.
                    </div>
                </div>
                <div className="flex items-center gap-2 pt-6">
                    <Checkbox id="att" checked={!!f.attiva} onCheckedChange={(v) => set("attiva", !!v)} />
                    <Label htmlFor="att" className="text-xs">Attiva</Label>
                </div>
                {f.tipo === "partner" && (
                    <div className="col-span-2">
                        <Label>Compagnie partner collegate <span className="text-[10px] text-slate-400 font-normal">(sincronizzate col campo "Agenzia partner" della compagnia)</span></Label>
                        <div className="max-h-40 overflow-auto border border-slate-200 rounded-md p-1.5 space-y-1 bg-white mt-1" data-testid="age-compagnie-collegate">
                            {compagnie.length === 0
                                ? <div className="text-xs text-slate-400 p-2">Nessuna compagnia disponibile</div>
                                : compagnie.map((c) => {
                                    const sel = (f.compagnie_ids || []).includes(c.id);
                                    return (
                                        <label key={c.id} className={`flex items-center gap-2 p-1.5 rounded cursor-pointer text-sm ${sel ? "bg-sky-50" : "hover:bg-slate-50"}`}>
                                            <Checkbox checked={sel} onCheckedChange={() => toggleComp(c.id)} data-testid={`age-comp-${c.id}`} />
                                            <span className="flex-1">{c.ragione_sociale}</span>
                                            {c.codice && <span className="text-[10px] text-slate-400 font-mono">{c.codice}</span>}
                                        </label>
                                    );
                                })}
                        </div>
                        <div className="text-[10px] text-slate-500 mt-1">
                            Selezionando qui una compagnia, questa agenzia viene aggiunta al suo campo "Agenzia partner" (e viceversa).
                        </div>
                    </div>
                )}
            </div>
            {editing?.id ? (
                <div className="border-t border-slate-100 pt-3 mt-1" data-testid="age-documenti-sezione">
                    <div className="text-sm font-semibold text-slate-800 mb-2 flex items-center gap-1.5">
                        <FileText size={14} className="text-slate-500" /> Documenti
                    </div>
                    <DocumentiAgenzia aid={editing.id} iniziali={editing.documenti || []} />
                </div>
            ) : (
                <div className="border-t border-slate-100 pt-3 mt-1 text-xs text-slate-400" data-testid="age-documenti-hint">
                    Salva l'agenzia per poter caricare i documenti.
                </div>
            )}
            <DialogFooter>
                <Button onClick={save} className="bg-sky-700 hover:bg-sky-800" data-testid="age-save">
                    {editing?.id ? "Aggiorna" : "Crea"}
                </Button>
            </DialogFooter>
        </DialogContent>
    );
}

// =================== DOCUMENTI AGENZIA (card) ===================
const AGE_DOC_TIPI_FALLBACK = [
    "Contratto di mandato", "Lettera di incarico", "Visura camerale",
    "Iscrizione RUI/IVASS", "Documento IBAN", "Altro",
];

function ageDocScadenza(dataScadenza) {
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

function DocumentiAgenzia({ aid, iniziali }) {
    const [list, setList] = useState(iniziali || []);
    const [tipi, setTipi] = useState(AGE_DOC_TIPI_FALLBACK);
    const [tipologia, setTipologia] = useState("");
    const [descrizione, setDescrizione] = useState("");
    const [dataRilascio, setDataRilascio] = useState("");
    const [dataScadenza, setDataScadenza] = useState("");
    const [file, setFile] = useState(null);
    const [fileKey, setFileKey] = useState(0);

    useEffect(() => {
        api.get("/config/card-visibilita")
            .then((r) => {
                const lst = (r.data?.agenzia_partner || []).map((c) => c.label).filter(Boolean);
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
            const r = await api.post(`/agenzie/${aid}/documenti`, fd,
                { headers: { "Content-Type": "multipart/form-data" } });
            setList((p) => [...p, r.data]);
            setTipologia(""); setDescrizione(""); setDataRilascio(""); setDataScadenza(""); setFile(null); setFileKey((k) => k + 1);
            toast.success("Documento aggiunto");
        } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
    };
    const rimuovi = async (id) => {
        if (!window.confirm("Eliminare il documento?")) return;
        try {
            await api.delete(`/agenzie/${aid}/documenti/${id}`);
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
        <div className="space-y-3" data-testid="documenti-agenzia">
            <div className="border border-slate-200 rounded-md p-3 bg-slate-50">
                <div className="text-xs font-semibold text-slate-600 mb-2 flex items-center gap-1"><Plus size={13} /> Aggiungi documento</div>
                <div className="grid grid-cols-2 gap-2">
                    <div>
                        <Label className="text-xs">Tipologia</Label>
                        <select value={tipologia} onChange={(e) => setTipologia(e.target.value)}
                            className="w-full h-9 px-2 text-sm border border-slate-200 rounded-md bg-white" data-testid="age-doc-tipologia">
                            <option value="">— Seleziona —</option>
                            {tipi.map((t) => <option key={t} value={t}>{t}</option>)}
                        </select>
                    </div>
                    <div>
                        <Label className="text-xs">Descrizione (facoltativa)</Label>
                        <Input value={descrizione} onChange={(e) => setDescrizione(e.target.value)} data-testid="age-doc-descrizione" />
                    </div>
                    <div>
                        <Label className="text-xs">Data rilascio</Label>
                        <Input type="date" value={dataRilascio} onChange={(e) => setDataRilascio(e.target.value)} data-testid="age-doc-data-rilascio" />
                    </div>
                    <div>
                        <Label className="text-xs">Data scadenza</Label>
                        <Input type="date" value={dataScadenza} onChange={(e) => setDataScadenza(e.target.value)} data-testid="age-doc-data-scadenza" />
                    </div>
                    <div className="col-span-2">
                        <Label className="text-xs">File (PDF/IMG)</Label>
                        <Input type="file" accept=".pdf,image/*" key={fileKey} onChange={(e) => setFile(e.target.files?.[0] || null)} data-testid="age-doc-file" />
                    </div>
                </div>
                <Button size="sm" className="mt-2 bg-sky-700 hover:bg-sky-800" onClick={aggiungi} data-testid="age-doc-add-btn">
                    <Plus size={12} className="mr-1" /> Aggiungi
                </Button>
            </div>

            {(list || []).length === 0 ? (
                <div className="text-center text-xs text-slate-400 py-3">Nessun documento caricato</div>
            ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3" data-testid="age-doc-cards">
                    {ordine.filter((t) => (gruppi[t] || []).length > 0).map((t) => (
                        <AgeDocFolderCard key={t} tipologia={t} files={gruppi[t]} aid={aid} onDelete={rimuovi} onAvviso={aggiornaAvviso} />
                    ))}
                </div>
            )}
        </div>
    );
}

function AgeDocFolderCard({ tipologia, files, aid, onDelete, onAvviso }) {
    const [open, setOpen] = useState(true);
    return (
        <div className="border border-slate-200 rounded-lg overflow-hidden" data-testid={`age-doc-folder-${tipologia}`}>
            <button onClick={() => setOpen((o) => !o)}
                className="w-full flex items-center gap-2 px-3 py-2.5 bg-slate-50 hover:bg-slate-100 transition-colors text-left"
                data-testid={`age-doc-folder-toggle-${tipologia}`}>
                <FileText size={16} className="text-slate-500" />
                <span className="font-medium text-sm text-slate-800 flex-1">{tipologia}</span>
                <span className="text-[11px] px-2 py-0.5 rounded-full bg-slate-200 text-slate-600">{files.length}</span>
                <span className={`text-slate-400 transition-transform ${open ? "rotate-180" : ""}`}>▾</span>
            </button>
            {open && (
                <ul className="divide-y divide-slate-100 px-3">
                    {files.map((a) => {
                        const sc = ageDocScadenza(a.data_scadenza);
                        return (
                            <li key={a.id} className="py-2.5 flex items-center gap-3" data-testid={`age-doc-item-${a.id}`}>
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
                                        {sc && <span className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${sc.cls}`} data-testid={`age-doc-scadenza-${a.id}`}>{sc.label}</span>}
                                        <AvvisoScadenzaControl entita="agenzia_partner" entitaId={aid} item={a} onChange={onAvviso} />
                                    </div>
                                </div>
                                <button onClick={() => onDelete(a.id)} className="text-red-600 hover:bg-red-50 p-1.5 rounded shrink-0" data-testid={`age-doc-del-${a.id}`}>
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
