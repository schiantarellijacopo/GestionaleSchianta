/**
 * SinistroDetail — pagina dettaglio singolo sinistro con tab:
 *   Dati Generali · Soggetti coinvolti · Anagrafiche associate · Note ·
 *   Liquidazione · Documenti · Costatazione Amichevole (solo RC Auto)
 *
 * Layout ispirato ai gestionali italiani standard (Schiantarelli / Axicura):
 * header con riepilogo polizza/compagnia/contraente + status badge,
 * azioni Salva/Elimina/Documenti/Stampa, tabs in basso.
 */
import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api, API_BASE, fmtEur } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Checkbox } from "@/components/ui/checkbox";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Card } from "@/components/ui/card";
import { Loading } from "@/components/Shared";
import {
    Save, Trash2, Printer, FileText, ArrowLeft, Plus, X, CheckCircle, Upload, FileDown,
} from "lucide-react";
import { toast } from "sonner";

const RUOLI_SOGGETTO = ["Controparte", "Terzo trasportato", "Pedone", "Conducente", "Proprietario", "Danneggiato", "Testimone"];
const TIPI_ANAGRAFICA = ["Perito", "Carrozzeria", "Legale", "Medico", "CTU", "Liquidatore compagnia", "Studio", "Altro"];
const TIPO_DEFINIZIONE = ["Attivo", "Passivo", "Misto", "Senza seguito"];
const STATI = [
    { v: "aperto", l: "Aperto" },
    { v: "in_istruttoria", l: "In istruttoria" },
    { v: "liquidato", l: "Liquidato" },
    { v: "chiuso", l: "Chiuso" },
    { v: "chiuso_senza_seguito", l: "Chiuso senza seguito" },
    { v: "respinto", l: "Respinto" },
];

const STATO_COLORS = {
    aperto: "text-emerald-600", in_istruttoria: "text-amber-600",
    liquidato: "text-sky-600", chiuso: "text-slate-600",
    chiuso_senza_seguito: "text-slate-500", respinto: "text-rose-600",
};

export default function SinistroDetail() {
    const { id } = useParams();
    const navigate = useNavigate();
    const [s, setS] = useState(null);
    const [saving, setSaving] = useState(false);

    const load = () => api.get(`/sinistri/${id}`).then((r) => setS(r.data))
        .catch(() => toast.error("Sinistro non trovato"));
    useEffect(() => { load(); }, [id]);

    if (!s) return <Loading />;
    const isRcAuto = (s.ramo || s.polizza?.ramo || "").toUpperCase().includes("AUTO")
        || (s.polizza?.targa);
    const stato = s.stato || "aperto";

    const setField = (k, v) => setS({ ...s, [k]: v });
    const setNested = (parent, k, v) => setS({ ...s, [parent]: { ...(s[parent] || {}), [k]: v } });

    const save = async () => {
        setSaving(true);
        try {
            const payload = {
                numero_sinistro: s.numero_sinistro, numero_interno: s.numero_interno,
                tipologia_sinistro: s.tipologia_sinistro, anno: s.anno,
                data_avvenimento: s.data_avvenimento, data_denuncia: s.data_denuncia,
                data_apertura: s.data_apertura, luogo: s.luogo,
                descrizione: s.descrizione, stato: s.stato,
                riserva: parseFloat(s.riserva) || 0, liquidazione: parseFloat(s.liquidazione) || 0,
                garanzie_colpite: s.garanzie_colpite || [],
                soggetti_coinvolti: s.soggetti_coinvolti || [],
                anagrafiche_associate: s.anagrafiche_associate || [],
                note: s.note || [],
                liquidazione_dettaglio: s.liquidazione_dettaglio || {},
            };
            await api.put(`/sinistri/${id}`, payload);
            toast.success("Sinistro salvato");
            load();
        } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
        finally { setSaving(false); }
    };

    const remove = async () => {
        if (!window.confirm(`Eliminare definitivamente il sinistro ${s.numero_sinistro}?`)) return;
        try {
            await api.delete(`/sinistri/${id}`);
            toast.success("Sinistro eliminato"); navigate("/sinistri");
        } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
    };

    const stampaSinistro = () => window.open(`${API_BASE}/stampa/sinistro/${id}`, "_blank");
    const stampaCID = () => window.open(`${API_BASE}/stampa/sinistro/${id}/cid`, "_blank");

    return (
        <div data-testid="sinistro-detail-page" className="space-y-3">
            {/* Toolbar superiore */}
            <div className="bg-white border border-slate-200 rounded-md px-4 py-2 flex items-center gap-3">
                <button onClick={() => navigate("/sinistri")} className="text-slate-500 hover:text-slate-900" data-testid="back-button">
                    <ArrowLeft size={18} />
                </button>
                <Button size="sm" onClick={save} disabled={saving} className="bg-sky-700 hover:bg-sky-800" data-testid="sin-save">
                    <Save size={14} className="mr-1" /> {saving ? "Salvataggio…" : "Salva"}
                </Button>
                <Button size="sm" variant="outline" onClick={remove} className="text-rose-600 hover:bg-rose-50" data-testid="sin-delete">
                    <Trash2 size={14} className="mr-1" /> Elimina
                </Button>
                <Button size="sm" variant="outline" onClick={stampaSinistro} data-testid="sin-print">
                    <Printer size={14} className="mr-1" /> Stampa
                </Button>
                {isRcAuto && (
                    <Button size="sm" variant="outline" onClick={stampaCID} className="bg-amber-50" data-testid="sin-cid-print">
                        <FileText size={14} className="mr-1" /> Stampa CID
                    </Button>
                )}
                <span className="ml-auto text-xs text-slate-500">
                    Aggiornato: {(s.updated_at || "").slice(0, 16).replace("T", " ")}
                </span>
            </div>

            {/* Header riepilogativo */}
            <div className="bg-white border border-slate-200 rounded-md p-5">
                <div className="grid grid-cols-12 gap-6">
                    <div className="col-span-3 border-r border-slate-200 pr-5">
                        <h1 className="text-3xl font-bold text-slate-700 tracking-wide">SINISTRO</h1>
                        <div className={`mt-1 text-sm font-semibold ${STATO_COLORS[stato] || ""} flex items-center gap-1`}>
                            {stato.replace("_", " ").toUpperCase()} <CheckCircle size={14} />
                        </div>
                    </div>
                    <div className="col-span-6 text-sm space-y-1">
                        <Riga label="Contratto" value={s.numero_polizza || "—"} />
                        <Riga label="Contraente" value={s.contraente_nome} />
                        <Riga label="Ramo" value={s.polizza?.ramo || s.ramo} />
                        <Riga label="Compagnia" value={s.compagnia_nome} />
                        <Riga label="Targa" value={s.polizza?.targa} />
                        <Riga label="Rischio" value={s.polizza?.prodotto} />
                    </div>
                    <div className="col-span-3">
                        <Label className="text-xs text-sky-600 font-medium">Garanzie Colpite</Label>
                        <Textarea
                            rows={3}
                            placeholder="Clicca per inserire…"
                            value={(s.garanzie_colpite || []).join(", ")}
                            onChange={(e) => setField("garanzie_colpite", e.target.value.split(",").map((t) => t.trim()).filter(Boolean))}
                            data-testid="sin-garanzie"
                        />
                    </div>
                </div>
                <div className="grid grid-cols-4 gap-4 mt-4 pt-4 border-t border-slate-100">
                    <CampoLabel label="Creatore" value={s.collaboratore_nome || "—"} readOnly />
                    <CampoInput label="Numero Interno" value={s.numero_interno || ""} onChange={(v) => setField("numero_interno", v)} testid="sin-numero-interno" />
                    <CampoInput label="Data Apertura" type="date" value={s.data_apertura || s.data_denuncia || ""} onChange={(v) => setField("data_apertura", v)} testid="sin-data-apertura" />
                    <CampoInput label="Anno" type="number" value={s.anno || new Date(s.data_avvenimento || Date.now()).getFullYear()} onChange={(v) => setField("anno", parseInt(v) || null)} testid="sin-anno" />
                    <div className="col-span-2">
                        <Label className="text-xs">Tipologia Sinistro</Label>
                        <Input value={s.tipologia_sinistro || ""} onChange={(e) => setField("tipologia_sinistro", e.target.value)}
                            placeholder="es. SINISTRI FENOMENO ELETTRICO" data-testid="sin-tipologia" />
                    </div>
                    <div>
                        <Label className="text-xs">Stato</Label>
                        <Select value={stato} onValueChange={(v) => setField("stato", v)}>
                            <SelectTrigger data-testid="sin-stato"><SelectValue /></SelectTrigger>
                            <SelectContent>
                                {STATI.map((s) => <SelectItem key={s.v} value={s.v}>{s.l}</SelectItem>)}
                            </SelectContent>
                        </Select>
                    </div>
                </div>
            </div>

            {/* Tabs */}
            <Tabs defaultValue="dati">
                <TabsList className="bg-slate-100">
                    <TabsTrigger value="dati" data-testid="tab-dati">Dati Generali</TabsTrigger>
                    <TabsTrigger value="soggetti" data-testid="tab-soggetti">Soggetti coinvolti</TabsTrigger>
                    <TabsTrigger value="anagrafiche" data-testid="tab-anagrafiche">Anagrafiche Associate</TabsTrigger>
                    <TabsTrigger value="note" data-testid="tab-note">Note</TabsTrigger>
                    <TabsTrigger value="liquidazione" data-testid="tab-liquidazione">Liquidazione</TabsTrigger>
                    <TabsTrigger value="documenti" data-testid="tab-documenti">Documenti</TabsTrigger>
                    {isRcAuto && <TabsTrigger value="cid" data-testid="tab-cid">Costatazione Amichevole</TabsTrigger>}
                </TabsList>

                <TabsContent value="dati">
                    <Card className="p-4 space-y-3">
                        <div className="grid grid-cols-3 gap-3">
                            <CampoInput label="Numero Sinistro" value={s.numero_sinistro || ""} onChange={(v) => setField("numero_sinistro", v)} />
                            <CampoInput label="Data Avvenimento" type="date" value={s.data_avvenimento || ""} onChange={(v) => setField("data_avvenimento", v)} />
                            <CampoInput label="Data Denuncia" type="date" value={s.data_denuncia || ""} onChange={(v) => setField("data_denuncia", v)} />
                            <div className="col-span-2"><Label className="text-xs">Luogo</Label><Input value={s.luogo || ""} onChange={(e) => setField("luogo", e.target.value)} /></div>
                            <CampoInput label="Riserva €" type="number" value={s.riserva || 0} onChange={(v) => setField("riserva", v)} />
                            <CampoInput label="Liquidazione €" type="number" value={s.liquidazione || 0} onChange={(v) => setField("liquidazione", v)} />
                        </div>
                        <div>
                            <Label className="text-xs">Descrizione</Label>
                            <Textarea rows={4} value={s.descrizione || ""} onChange={(e) => setField("descrizione", e.target.value)} data-testid="sin-descrizione" />
                        </div>
                    </Card>
                </TabsContent>

                <TabsContent value="soggetti">
                    <SoggettiTab items={s.soggetti_coinvolti || []} onChange={(v) => setField("soggetti_coinvolti", v)} />
                </TabsContent>

                <TabsContent value="anagrafiche">
                    <AnagraficheTab items={s.anagrafiche_associate || []} onChange={(v) => setField("anagrafiche_associate", v)} />
                </TabsContent>

                <TabsContent value="note">
                    <NoteTab items={s.note || []} onChange={(v) => setField("note", v)} />
                </TabsContent>

                <TabsContent value="liquidazione">
                    <LiquidazioneTab v={s.liquidazione_dettaglio || {}} onChange={(k, val) => setNested("liquidazione_dettaglio", k, val)} />
                </TabsContent>

                <TabsContent value="documenti">
                    <DocumentiTab sinistroId={id} docs={s.documenti || []} onReload={load} />
                </TabsContent>

                {isRcAuto && (
                    <TabsContent value="cid">
                        <CIDForm sinistroId={id} cid={s.costatazione_amichevole || {}} polizza={s.polizza || {}}
                            contraente={s.contraente || {}} onSaved={load} />
                    </TabsContent>
                )}
            </Tabs>
        </div>
    );
}

const Riga = ({ label, value }) => (
    <div className="flex gap-2">
        <span className="text-slate-500 w-24">{label}</span>
        <span className="font-medium text-slate-800">{value || "—"}</span>
    </div>
);
const CampoLabel = ({ label, value }) => (
    <div><Label className="text-xs text-slate-500">{label}</Label>
        <div className="text-sm font-medium text-slate-800 mt-1.5">{value || "—"}</div></div>
);
const CampoInput = ({ label, value, onChange, type = "text", testid }) => (
    <div><Label className="text-xs">{label}</Label>
        <Input type={type} value={value || ""} onChange={(e) => onChange(e.target.value)} data-testid={testid} /></div>
);

// ============ Soggetti Coinvolti ============
function SoggettiTab({ items, onChange }) {
    const add = () => onChange([...items, { soggetto: "", ruolo: "", numero_polizza: "", riserva: 0, pagato: 0, recuperato: 0 }]);
    const upd = (i, k, v) => onChange(items.map((x, idx) => idx === i ? { ...x, [k]: v } : x));
    const rm = (i) => onChange(items.filter((_, idx) => idx !== i));
    return (
        <Card className="p-3">
            <table className="w-full text-xs">
                <thead className="border-b border-slate-200">
                    <tr className="text-left text-slate-500">
                        <th className="py-2">Soggetto coinvolto</th><th>Ruolo</th><th>N.Polizza</th>
                        <th className="text-right">Riserva</th><th className="text-right">Pagato</th>
                        <th className="text-right">Recuperato</th><th className="w-10">Azioni</th>
                    </tr>
                </thead>
                <tbody>
                    {items.map((it, i) => (
                        <tr key={i} className="border-b border-slate-100">
                            <td><Input value={it.soggetto || ""} onChange={(e) => upd(i, "soggetto", e.target.value)} className="h-8" data-testid={`sog-${i}-nome`} /></td>
                            <td>
                                <Select value={it.ruolo || ""} onValueChange={(v) => upd(i, "ruolo", v)}>
                                    <SelectTrigger className="h-8"><SelectValue placeholder="—" /></SelectTrigger>
                                    <SelectContent>
                                        {RUOLI_SOGGETTO.map((r) => <SelectItem key={r} value={r}>{r}</SelectItem>)}
                                    </SelectContent>
                                </Select>
                            </td>
                            <td><Input value={it.numero_polizza || ""} onChange={(e) => upd(i, "numero_polizza", e.target.value)} className="h-8" /></td>
                            <td><Input type="number" step="0.01" value={it.riserva || 0} onChange={(e) => upd(i, "riserva", parseFloat(e.target.value) || 0)} className="h-8 text-right" /></td>
                            <td><Input type="number" step="0.01" value={it.pagato || 0} onChange={(e) => upd(i, "pagato", parseFloat(e.target.value) || 0)} className="h-8 text-right" /></td>
                            <td><Input type="number" step="0.01" value={it.recuperato || 0} onChange={(e) => upd(i, "recuperato", parseFloat(e.target.value) || 0)} className="h-8 text-right" /></td>
                            <td><button onClick={() => rm(i)} className="text-rose-500 hover:bg-rose-50 p-1 rounded"><X size={14} /></button></td>
                        </tr>
                    ))}
                </tbody>
            </table>
            <Button onClick={add} variant="outline" size="sm" className="mt-3" data-testid="sog-add">
                <Plus size={12} className="mr-1" /> Aggiungi Soggetto
            </Button>
        </Card>
    );
}

// ============ Anagrafiche Associate ============
function AnagraficheTab({ items, onChange }) {
    const add = () => onChange([...items, { nome: "", tipo: "", indirizzo: "", telefono: "", fax: "", email: "", data_attribuzione: new Date().toISOString().slice(0, 10) }]);
    const upd = (i, k, v) => onChange(items.map((x, idx) => idx === i ? { ...x, [k]: v } : x));
    const rm = (i) => onChange(items.filter((_, idx) => idx !== i));
    return (
        <Card className="p-3">
            <table className="w-full text-xs">
                <thead className="border-b border-slate-200">
                    <tr className="text-left text-slate-500">
                        <th className="py-2">Anagrafica</th><th>Tipo</th><th>Indirizzo</th>
                        <th>Telefono</th><th>Fax</th><th>Mail</th><th>Data Attribuzione</th><th className="w-10"></th>
                    </tr>
                </thead>
                <tbody>
                    {items.map((it, i) => (
                        <tr key={i} className="border-b border-slate-100">
                            <td><Input value={it.nome || ""} onChange={(e) => upd(i, "nome", e.target.value)} className="h-8" /></td>
                            <td>
                                <Select value={it.tipo || ""} onValueChange={(v) => upd(i, "tipo", v)}>
                                    <SelectTrigger className="h-8"><SelectValue placeholder="—" /></SelectTrigger>
                                    <SelectContent>
                                        {TIPI_ANAGRAFICA.map((t) => <SelectItem key={t} value={t}>{t}</SelectItem>)}
                                    </SelectContent>
                                </Select>
                            </td>
                            <td><Input value={it.indirizzo || ""} onChange={(e) => upd(i, "indirizzo", e.target.value)} className="h-8" /></td>
                            <td><Input value={it.telefono || ""} onChange={(e) => upd(i, "telefono", e.target.value)} className="h-8" /></td>
                            <td><Input value={it.fax || ""} onChange={(e) => upd(i, "fax", e.target.value)} className="h-8" /></td>
                            <td><Input value={it.email || ""} onChange={(e) => upd(i, "email", e.target.value)} className="h-8" /></td>
                            <td><Input type="date" value={it.data_attribuzione || ""} onChange={(e) => upd(i, "data_attribuzione", e.target.value)} className="h-8" /></td>
                            <td><button onClick={() => rm(i)} className="text-rose-500 hover:bg-rose-50 p-1 rounded"><X size={14} /></button></td>
                        </tr>
                    ))}
                </tbody>
            </table>
            <Button onClick={add} variant="outline" size="sm" className="mt-3" data-testid="anag-add">
                <Plus size={12} className="mr-1" /> Aggiungi Anagrafica
            </Button>
        </Card>
    );
}

// ============ Note ============
function NoteTab({ items, onChange }) {
    const add = () => onChange([...items, {
        id: crypto.randomUUID(), data: new Date().toISOString().slice(0, 10),
        scadenza: "", operatore: "", descrizione: "", avvisa: false,
    }]);
    const upd = (i, k, v) => onChange(items.map((x, idx) => idx === i ? { ...x, [k]: v } : x));
    const rm = (i) => onChange(items.filter((_, idx) => idx !== i));
    return (
        <Card className="p-3">
            <table className="w-full text-xs">
                <thead className="border-b border-slate-200">
                    <tr className="text-left text-slate-500">
                        <th className="py-2 w-28">Data</th><th className="w-28">Scadenza</th>
                        <th className="w-32">Operatore</th><th>Descrizione</th><th className="w-16">Avvisa</th><th className="w-10"></th>
                    </tr>
                </thead>
                <tbody>
                    {items.map((it, i) => (
                        <tr key={it.id || i} className="border-b border-slate-100">
                            <td><Input type="date" value={it.data || ""} onChange={(e) => upd(i, "data", e.target.value)} className="h-8" /></td>
                            <td><Input type="date" value={it.scadenza || ""} onChange={(e) => upd(i, "scadenza", e.target.value)} className="h-8" /></td>
                            <td><Input value={it.operatore || ""} onChange={(e) => upd(i, "operatore", e.target.value)} className="h-8" /></td>
                            <td><Textarea rows={2} value={it.descrizione || ""} onChange={(e) => upd(i, "descrizione", e.target.value)} className="text-xs" /></td>
                            <td className="text-center"><Checkbox checked={!!it.avvisa} onCheckedChange={(v) => upd(i, "avvisa", !!v)} /></td>
                            <td><button onClick={() => rm(i)} className="text-rose-500 hover:bg-rose-50 p-1 rounded"><X size={14} /></button></td>
                        </tr>
                    ))}
                </tbody>
            </table>
            <Button onClick={add} variant="outline" size="sm" className="mt-3" data-testid="note-add">
                <Plus size={12} className="mr-1" /> Aggiungi Nota
            </Button>
        </Card>
    );
}

// ============ Liquidazione ============
function LiquidazioneTab({ v, onChange }) {
    return (
        <Card className="p-4">
            <div className="grid grid-cols-3 gap-4">
                <div>
                    <Label className="text-xs">Tipo definizione</Label>
                    <Select value={v.tipo_definizione || ""} onValueChange={(val) => onChange("tipo_definizione", val)}>
                        <SelectTrigger><SelectValue placeholder="—" /></SelectTrigger>
                        <SelectContent>
                            {TIPO_DEFINIZIONE.map((t) => <SelectItem key={t} value={t}>{t}</SelectItem>)}
                        </SelectContent>
                    </Select>
                </div>
                <CampoInput label="Data definizione" type="date" value={v.data_definizione} onChange={(val) => onChange("data_definizione", val)} />
                <CampoInput label="Data prescrizione" type="date" value={v.data_prescrizione} onChange={(val) => onChange("data_prescrizione", val)} />
                <CampoInput label="Franchigia €" type="number" value={v.franchigia} onChange={(val) => onChange("franchigia", parseFloat(val) || 0)} />
                <CampoInput label="Scoperto €" type="number" value={v.scoperto} onChange={(val) => onChange("scoperto", parseFloat(val) || 0)} />
                <CampoInput label="Importo denunciato €" type="number" value={v.importo_denunciato} onChange={(val) => onChange("importo_denunciato", parseFloat(val) || 0)} />
                <CampoInput label="Riserva Corrente €" type="number" value={v.riserva_corrente} onChange={(val) => onChange("riserva_corrente", parseFloat(val) || 0)} />
                <CampoInput label="Data Riserva" type="date" value={v.data_riserva} onChange={(val) => onChange("data_riserva", val)} />
            </div>
        </Card>
    );
}

// ============ Documenti ============
function DocumentiTab({ sinistroId, docs, onReload }) {
    const upload = async (e) => {
        const f = e.target.files?.[0]; if (!f) return;
        const fd = new FormData();
        fd.append("file", f);
        fd.append("entity_type", "sinistro");
        fd.append("entity_id", sinistroId);
        fd.append("sinistro_id", sinistroId);
        try {
            await api.post("/storage/upload", fd, { headers: { "Content-Type": "multipart/form-data" } });
            toast.success("Documento caricato"); onReload();
        } catch (err) { toast.error("Errore upload"); }
        e.target.value = "";
    };
    const del = async (fid) => {
        if (!window.confirm("Eliminare il documento?")) return;
        try {
            await api.delete(`/storage/${fid}`);
            toast.success("Documento eliminato"); onReload();
        } catch { toast.error("Errore"); }
    };
    return (
        <Card className="p-4">
            <div className="flex items-center justify-between mb-3">
                <h3 className="text-sm font-semibold">Documenti collegati ({docs.length})</h3>
                <label className="inline-flex items-center gap-1 px-3 py-1.5 rounded border border-sky-200 bg-sky-50 text-sky-700 text-xs font-medium cursor-pointer hover:bg-sky-100" data-testid="doc-upload-btn">
                    <Upload size={12} /> Carica documento
                    <input type="file" hidden onChange={upload} data-testid="doc-upload-input" />
                </label>
            </div>
            {docs.length === 0 ? (
                <div className="text-sm text-slate-500 py-6 text-center">Nessun documento allegato</div>
            ) : (
                <table className="w-full text-xs">
                    <thead className="border-b border-slate-200 text-slate-500 text-left">
                        <tr><th className="py-2">Nome file</th><th>Tipo</th><th>Caricato</th><th className="w-32"></th></tr>
                    </thead>
                    <tbody>
                        {docs.map((d) => (
                            <tr key={d.id} className="border-b border-slate-100">
                                <td className="py-2">{d.original_name || d.filename}</td>
                                <td>{d.content_type || "—"}</td>
                                <td>{(d.uploaded_at || "").slice(0, 16).replace("T", " ")}</td>
                                <td className="text-right space-x-1">
                                    <a href={`${API_BASE}/storage/${d.id}/download`} target="_blank" rel="noreferrer"
                                       className="inline-flex items-center text-sky-700 hover:underline text-xs">
                                        <FileDown size={11} className="mr-0.5" /> Scarica
                                    </a>
                                    <button onClick={() => del(d.id)} className="text-rose-500 hover:bg-rose-50 px-1.5 py-0.5 rounded">
                                        <Trash2 size={11} />
                                    </button>
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            )}
        </Card>
    );
}

// ============ Costatazione Amichevole ============
const CIRC = [
    "in sosta / fermato", "ripartiva dopo sosta / aprendo portiera",
    "stava parcheggiando", "usciva da parcheggio/luogo privato",
    "entrava in parcheggio/luogo privato", "si immetteva in piazza/rotatoria",
    "circolava in piazza/rotatoria", "tamponava nella stessa fila",
    "procedeva stessa direzione su fila diversa", "cambiava fila",
    "sorpassava", "girava a destra", "girava a sinistra",
    "retrocedeva", "invadeva sede stradale opposta",
    "proveniva da destra", "non osservava precedenza/semaforo rosso",
];

function CIDForm({ sinistroId, cid, polizza, contraente, onSaved }) {
    const [data, setData] = useState({
        data_incidente: cid.data_incidente || "", ora: cid.ora || "",
        luogo: cid.luogo || "", feriti: !!cid.feriti, testimoni: cid.testimoni || "",
        danni_altri_veicoli: !!cid.danni_altri_veicoli,
        danni_oggetti_diversi: !!cid.danni_oggetti_diversi,
        veicolo_a: {
            contraente_cognome: contraente.cognome || contraente.ragione_sociale || "",
            contraente_nome: contraente.nome || "",
            codice_fiscale: contraente.codice_fiscale || contraente.partita_iva || "",
            indirizzo: contraente.indirizzo || "",
            contatto: contraente.telefono || contraente.email || "",
            marca_tipo: polizza.marca && polizza.modello ? `${polizza.marca} ${polizza.modello}` : "",
            targa: polizza.targa || "",
            compagnia: "", numero_polizza: polizza.numero_polizza || "",
            conducente_nome: "", patente: "", punto_urto: "", danni_visibili: "", osservazioni: "",
            ...(cid.veicolo_a || {}),
        },
        veicolo_b: cid.veicolo_b || {
            contraente_cognome: "", contraente_nome: "", codice_fiscale: "", indirizzo: "",
            contatto: "", marca_tipo: "", targa: "", compagnia: "", numero_polizza: "",
            conducente_nome: "", patente: "", punto_urto: "", danni_visibili: "", osservazioni: "",
        },
        circostanze_a: cid.circostanze_a || [],
        circostanze_b: cid.circostanze_b || [],
    });
    const upd = (k, v) => setData({ ...data, [k]: v });
    const updV = (side, k, v) => setData({ ...data, [side]: { ...data[side], [k]: v } });
    const toggleCirc = (side, idx) => {
        const arr = data[side] || [];
        setData({ ...data, [side]: arr.includes(idx) ? arr.filter((x) => x !== idx) : [...arr, idx] });
    };
    const save = async () => {
        try {
            await api.put(`/sinistri/${sinistroId}/cid`, data);
            toast.success("Costatazione Amichevole salvata");
            onSaved();
        } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
    };
    return (
        <Card className="p-4 space-y-4">
            <div className="bg-sky-700 text-white p-3 rounded -mx-4 -mt-4">
                <h2 className="text-base font-bold">Costatazione Amichevole di Incidente · Denuncia di Sinistro</h2>
                <div className="text-[10px]">(art. 143 D.Lgs. 209/2005 — Codice delle assicurazioni private)</div>
            </div>

            <div className="grid grid-cols-4 gap-3">
                <CampoInput label="1. Data incidente" type="date" value={data.data_incidente} onChange={(v) => upd("data_incidente", v)} testid="cid-data" />
                <CampoInput label="Ora" type="time" value={data.ora} onChange={(v) => upd("ora", v)} />
                <div className="col-span-2"><Label className="text-xs">2. Luogo (Comune, via)</Label>
                    <Input value={data.luogo} onChange={(e) => upd("luogo", e.target.value)} data-testid="cid-luogo" /></div>
                <div className="flex items-center gap-2 col-span-1">
                    <Checkbox checked={data.feriti} onCheckedChange={(v) => upd("feriti", !!v)} id="cid-feriti" />
                    <Label htmlFor="cid-feriti" className="text-xs">3. Feriti anche se lievi</Label>
                </div>
                <div className="flex items-center gap-2 col-span-1">
                    <Checkbox checked={data.danni_altri_veicoli} onCheckedChange={(v) => upd("danni_altri_veicoli", !!v)} id="cid-d1" />
                    <Label htmlFor="cid-d1" className="text-xs">4. Danni altri veicoli</Label>
                </div>
                <div className="flex items-center gap-2 col-span-2">
                    <Checkbox checked={data.danni_oggetti_diversi} onCheckedChange={(v) => upd("danni_oggetti_diversi", !!v)} id="cid-d2" />
                    <Label htmlFor="cid-d2" className="text-xs">Oggetti diversi dai veicoli</Label>
                </div>
                <div className="col-span-4"><Label className="text-xs">5. Testimoni</Label>
                    <Textarea rows={2} value={data.testimoni} onChange={(e) => upd("testimoni", e.target.value)} /></div>
            </div>

            <div className="grid grid-cols-2 gap-4">
                <BloccoVeicolo titolo="VEICOLO A" colore="sky" v={data.veicolo_a} circ={data.circostanze_a}
                    upd={(k, v) => updV("veicolo_a", k, v)} toggle={(i) => toggleCirc("circostanze_a", i)} />
                <BloccoVeicolo titolo="VEICOLO B" colore="amber" v={data.veicolo_b} circ={data.circostanze_b}
                    upd={(k, v) => updV("veicolo_b", k, v)} toggle={(i) => toggleCirc("circostanze_b", i)} />
            </div>

            <div className="flex justify-end gap-2 pt-3 border-t">
                <Button onClick={save} className="bg-sky-700 hover:bg-sky-800" data-testid="cid-save">
                    <Save size={14} className="mr-1" /> Salva Costatazione
                </Button>
            </div>
        </Card>
    );
}

function BloccoVeicolo({ titolo, colore, v, circ, upd, toggle }) {
    const bg = colore === "sky" ? "bg-sky-100" : "bg-amber-100";
    const border = colore === "sky" ? "border-sky-300" : "border-amber-300";
    return (
        <div className={`border ${border} rounded p-3 ${bg}/30`}>
            <div className={`${bg} -m-3 mb-2 p-2 rounded-t font-bold text-sm`}>{titolo}</div>
            <div className="space-y-2 text-xs">
                <CampoMini label="6. Cognome" v={v.contraente_cognome} onChange={(x) => upd("contraente_cognome", x)} />
                <CampoMini label="Nome" v={v.contraente_nome} onChange={(x) => upd("contraente_nome", x)} />
                <CampoMini label="CF / P.IVA" v={v.codice_fiscale} onChange={(x) => upd("codice_fiscale", x)} />
                <CampoMini label="Indirizzo" v={v.indirizzo} onChange={(x) => upd("indirizzo", x)} />
                <CampoMini label="Tel / Email" v={v.contatto} onChange={(x) => upd("contatto", x)} />
                <CampoMini label="7. Marca/Tipo" v={v.marca_tipo} onChange={(x) => upd("marca_tipo", x)} />
                <CampoMini label="Targa" v={v.targa} onChange={(x) => upd("targa", x)} />
                <CampoMini label="8. Compagnia" v={v.compagnia} onChange={(x) => upd("compagnia", x)} />
                <CampoMini label="N. Polizza" v={v.numero_polizza} onChange={(x) => upd("numero_polizza", x)} />
                <CampoMini label="9. Conducente" v={v.conducente_nome} onChange={(x) => upd("conducente_nome", x)} />
                <CampoMini label="Patente N." v={v.patente} onChange={(x) => upd("patente", x)} />
                <CampoMini label="10. Punto urto" v={v.punto_urto} onChange={(x) => upd("punto_urto", x)} />
                <CampoMini label="11. Danni visibili" v={v.danni_visibili} onChange={(x) => upd("danni_visibili", x)} />
                <CampoMini label="14. Osservazioni" v={v.osservazioni} onChange={(x) => upd("osservazioni", x)} />
            </div>
            <div className="mt-3 pt-2 border-t">
                <Label className="text-xs font-bold">12. Circostanze (croci utili)</Label>
                <div className="grid grid-cols-1 gap-1 mt-1">
                    {CIRC.map((c, i) => (
                        <label key={i} className="flex items-center gap-1 text-[10px] cursor-pointer">
                            <input type="checkbox" checked={circ.includes(i + 1)} onChange={() => toggle(i + 1)} />
                            <span>{i + 1}. {c}</span>
                        </label>
                    ))}
                </div>
            </div>
        </div>
    );
}

const CampoMini = ({ label, v, onChange }) => (
    <div className="flex items-baseline gap-2">
        <span className="text-[10px] text-slate-600 w-24 shrink-0">{label}:</span>
        <Input value={v || ""} onChange={(e) => onChange(e.target.value)} className="h-7 text-xs" />
    </div>
);
