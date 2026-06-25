import { useEffect, useState, useRef } from "react";
import { useParams, Link } from "react-router-dom";
import { api, fmtDate, fmtEur } from "@/lib/api";
import { openPdf } from "@/lib/pdf";
import { PageHeader, Loading, StatusBadge } from "@/components/Shared";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
    Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger, DialogFooter,
} from "@/components/ui/dialog";
import {
    Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import RowActions, { PrintButton } from "@/components/RowActions";
import {
    ArrowLeft, GitBranch, UserPlus, ClipboardList, Calculator, BookText,
    Paperclip, MapPin, Plus, Upload, Phone, Mail, Calendar, FileText, Users,
} from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { toast } from "sonner";
import AnalisiClienteTab from "@/components/AnalisiClienteTab";
import PrivacyConsensiDialog from "@/components/PrivacyConsensiDialog";
import AddressAutocomplete from "@/components/AddressAutocomplete";
import useMezziPagamento from "@/hooks/useMezziPagamento";

export default function AnagraficaDetail() {
    const { id } = useParams();
    const { user } = useAuth();
    const [ana, setAna] = useState(null);
    const [polizze, setPolizze] = useState([]);
    const [privacyOpenHdr, setPrivacyOpenHdr] = useState(false);
    const canEdit = ["admin", "collaboratore", "dipendente"].includes(user?.role);

    const load = async () => {
        const [a, p] = await Promise.all([
            api.get(`/anagrafiche/${id}`),
            api.get("/polizze", { params: { contraente_id: id } }),
        ]);
        setAna(a.data); setPolizze(p.data);
    };
    useEffect(() => { load(); /* eslint-disable-next-line */ }, [id]);

    if (!ana) return <Loading />;

    // Stato compliance: privacy & documento riconoscimento
    const computePrivacyStato = () => {
        if (!ana) return "rosso";
        if (ana.privacy_firmata_url || ana.documenti?.privacy_firmata?.url) return "verde";
        if (ana.consenso_privacy || ana.consenso_dati_particolari || ana.consenso_commerciale) return "giallo";
        return "rosso";
    };
    const computeDocIdStato = () => {
        const d = ana?.documenti || {};
        const has = d.carta_identita?.url || d.carta_identita ||
                    d.patente?.url || d.patente ||
                    d.passaporto?.url || d.passaporto;
        return has ? "verde" : "rosso";
    };
    const statoPrivacy = computePrivacyStato();
    const statoDocId = computeDocIdStato();
    const dotColor = (s) => s === "verde" ? "bg-emerald-500" : s === "giallo" ? "bg-amber-400" : "bg-rose-500";
    const dotLabelPrivacy = {
        verde: "Privacy firmata ✓",
        giallo: "Consenso dato, PDF non firmato",
        rosso: "Nessun consenso privacy",
    }[statoPrivacy];
    const dotLabelDoc = statoDocId === "verde"
        ? "Documento di riconoscimento presente"
        : "Documento di riconoscimento MANCANTE";

    return (
        <div data-testid="anagrafica-detail-page">
            <Link to="/anagrafiche" className="text-sm text-slate-500 hover:text-sky-700 inline-flex items-center gap-1 mb-3">
                <ArrowLeft size={14} /> Torna alle anagrafiche
            </Link>
            <PageHeader
                title={
                    <span className="flex items-center gap-3 flex-wrap">
                        {ana.ragione_sociale}
                        <span className="inline-flex items-center gap-1.5 text-xs bg-slate-50 border border-slate-200 px-2 py-1 rounded-full" title={dotLabelPrivacy}>
                            <span className={`w-2.5 h-2.5 rounded-full ${dotColor(statoPrivacy)}`} data-testid="dot-privacy" />
                            <span className="text-slate-600">Privacy</span>
                        </span>
                        <span className="inline-flex items-center gap-1.5 text-xs bg-slate-50 border border-slate-200 px-2 py-1 rounded-full" title={dotLabelDoc}>
                            <span className={`w-2.5 h-2.5 rounded-full ${dotColor(statoDocId)}`} data-testid="dot-docid" />
                            <span className="text-slate-600">Doc. Riconoscimento</span>
                        </span>
                    </span>
                }
                subtitle={`${ana.tipo === "persona_giuridica" ? "Persona giuridica" : "Persona fisica"} · ${ana.codice_fiscale || ana.partita_iva || "—"}`}
                actions={
                    <div className="flex gap-2">
                        <Button
                            size="sm" variant="outline"
                            onClick={() => setPrivacyOpenHdr(true)}
                            className="border-sky-300 text-sky-700 hover:bg-sky-50"
                            data-testid="hdr-privacy-btn"
                        >
                            <FileText size={13} className="mr-1" /> Privacy & Consensi
                        </Button>
                        <PrintButton
                            onClick={() => openPdf(`/stampa/estratto-conto/${id}`)}
                            label="Estratto conto"
                            testid="print-estratto-button"
                        />
                    </div>
                }
            />

            <Tabs defaultValue="dati" className="w-full">
                <TabsList className="bg-slate-100 flex-wrap h-auto">
                    <TabsTrigger value="dati" data-testid="tab-dati">Anagrafica</TabsTrigger>
                    <TabsTrigger value="albero" data-testid="tab-albero">Albero genealogico</TabsTrigger>
                    <TabsTrigger value="polizze" data-testid="tab-polizze">Polizze ({polizze.length})</TabsTrigger>
                    <TabsTrigger value="intervista" data-testid="tab-intervista">Intervista</TabsTrigger>
                    <TabsTrigger value="diario" data-testid="tab-diario"><BookText size={13} className="mr-1" />Diario</TabsTrigger>
                    <TabsTrigger value="documenti" data-testid="tab-documenti"><Paperclip size={13} className="mr-1" />Documenti</TabsTrigger>
                    <TabsTrigger value="allegati" data-testid="tab-allegati"><Paperclip size={13} className="mr-1" />Altri allegati</TabsTrigger>
                    <TabsTrigger value="analisi" data-testid="tab-analisi"><Calculator size={13} className="mr-1" />Analisi Cliente</TabsTrigger>
                    <TabsTrigger value="pensione" data-testid="tab-pensione"><Calculator size={13} className="mr-1" />Pensione INPS</TabsTrigger>
                </TabsList>

                <TabsContent value="dati">
                    <DatiTab ana={ana} canEdit={canEdit} onReload={load} />
                </TabsContent>
                <TabsContent value="albero"><AlberoGenealogico ana={ana} canEdit={canEdit} onReload={load} /></TabsContent>
                <TabsContent value="polizze"><PolizzeTab polizze={polizze} /></TabsContent>
                <TabsContent value="intervista"><InterviewTab anagrafica_id={id} canEdit={canEdit} /></TabsContent>
                <TabsContent value="diario"><DiarioTab anagrafica_id={id} canEdit={canEdit} /></TabsContent>
                <TabsContent value="documenti"><DocumentiTab anagrafica_id={id} ana={ana} canEdit={canEdit} onReload={load} /></TabsContent>
                <TabsContent value="allegati"><AllegatiTab entita_tipo="anagrafica" entita_id={id} canEdit={canEdit} /></TabsContent>
                <TabsContent value="analisi"><AnalisiClienteTab anagrafica_id={id} ana={ana} canEdit={canEdit} onReload={load} /></TabsContent>
                <TabsContent value="pensione"><PensioneTab anagrafica_id={id} ana={ana} canEdit={canEdit} onReload={load} /></TabsContent>
            </Tabs>

            <PrivacyConsensiDialog
                open={privacyOpenHdr}
                onOpenChange={setPrivacyOpenHdr}
                anagrafica_id={id}
                ana={ana}
                canEdit={canEdit}
                onReload={load}
            />
        </div>
    );
}

function DatiTab({ ana, canEdit, onReload }) {
    const { mezzi } = useMezziPagamento();
    const [editing, setEditing] = useState(false);
    const [f, setF] = useState({ ...ana });
    const set = (k, v) => setF((p) => ({ ...p, [k]: v }));

    const save = async () => {
        try {
            await api.put(`/anagrafiche/${ana.id}`, f);
            toast.success("Anagrafica aggiornata"); setEditing(false); onReload();
        } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
    };

    const geocode = async () => {
        try {
            const r = await api.post(`/geo/anagrafiche/${ana.id}/geocode`);
            if (r.data.found) {
                toast.success(`Localizzato: ${r.data.address}`);
                onReload();
            } else {
                toast.error("Indirizzo non trovato");
            }
        } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
    };

    if (!editing) {
        return (
            <Card className="p-6 border-slate-200 mt-4">
                <div className="flex items-center justify-between mb-4">
                    <h3 className="font-medium text-slate-900">Dati anagrafici e previdenziali</h3>
                    <div className="flex gap-2">
                        {canEdit && (
                            <Button variant="outline" onClick={geocode} data-testid="geocode-button">
                                <MapPin size={14} className="mr-1" /> Geocodifica
                            </Button>
                        )}
                        {canEdit && (
                            <Button onClick={() => setEditing(true)} data-testid="anag-edit-button" className="bg-sky-700 hover:bg-sky-800">
                                Modifica
                            </Button>
                        )}
                    </div>
                </div>
                <div className="grid grid-cols-2 md:grid-cols-3 gap-x-8 gap-y-4">
                    {[
                        ["Codice fiscale", ana.codice_fiscale],
                        ["Partita IVA", ana.partita_iva],
                        ["Data nascita", fmtDate(ana.data_nascita)],
                        ["Sesso", ana.sesso === "M" ? "Maschio" : ana.sesso === "F" ? "Femmina" : "-"],
                        ["Comune nascita", ana.comune_nascita],
                        ["Email", ana.email],
                        ["Telefono", ana.telefono],
                        ["Cellulare", ana.cellulare],
                        ["IBAN", ana.iban],
                        ["Indirizzo", ana.indirizzo],
                        ["Comune", `${ana.comune || ""} ${ana.provincia ? `(${ana.provincia})` : ""}`],
                        ["CAP", ana.cap],
                        ["Professione", ana.professione],
                        ["Tipo lavoratore", ana.tipo_lavoratore],
                        ["Stato civile", ana.stato_civile],
                        ["N. figli", ana.numero_figli],
                        ["Figli a carico", ana.numero_figli_a_carico],
                        ["Reddito annuo lordo", ana.reddito_annuo_lordo ? fmtEur(ana.reddito_annuo_lordo) : "-"],
                        ["Inizio contribuzione", fmtDate(ana.data_inizio_contribuzione)],
                        ["Settimane contributive", ana.settimane_contributive],
                        ["Coordinate", ana.lat && ana.lng ? `${ana.lat.toFixed(4)}, ${ana.lng.toFixed(4)}` : "-"],
                    ].map(([k, v]) => (
                        <div key={k}>
                            <div className="text-[11px] uppercase tracking-wider text-slate-500 mb-1">{k}</div>
                            <div className="text-sm text-slate-800 num">{v || "—"}</div>
                        </div>
                    ))}
                </div>
                {ana.note && (
                    <div className="mt-5 pt-4 border-t border-slate-100">
                        <div className="text-[11px] uppercase tracking-wider text-slate-500 mb-1">Note</div>
                        <div className="text-sm text-slate-700 whitespace-pre-line">{ana.note}</div>
                    </div>
                )}
            </Card>
        );
    }

    return (
        <Card className="p-6 border-slate-200 mt-4">
            <h3 className="font-medium text-slate-900 mb-4">Modifica anagrafica</h3>
            <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
                <div><Label>Ragione sociale</Label><Input value={f.ragione_sociale || ""} onChange={(e) => set("ragione_sociale", e.target.value)} /></div>
                <div><Label>Codice fiscale</Label><Input value={f.codice_fiscale || ""} onChange={(e) => set("codice_fiscale", e.target.value.toUpperCase())} /></div>
                <div><Label>Partita IVA</Label><Input value={f.partita_iva || ""} onChange={(e) => set("partita_iva", e.target.value)} /></div>
                <div><Label>Data nascita</Label><Input type="date" value={f.data_nascita || ""} onChange={(e) => set("data_nascita", e.target.value)} /></div>
                <div>
                    <Label>Stato civile</Label>
                    <Select value={f.stato_civile || ""} onValueChange={(v) => set("stato_civile", v)}>
                        <SelectTrigger><SelectValue placeholder="-" /></SelectTrigger>
                        <SelectContent>
                            {["celibe", "nubile", "coniugato", "coniugata", "divorziato", "divorziata", "vedovo", "vedova", "unito civilmente"].map((s) =>
                                <SelectItem key={s} value={s}>{s}</SelectItem>)}
                        </SelectContent>
                    </Select>
                </div>
                <div>
                    <Label>Tipo lavoratore</Label>
                    <Select value={f.tipo_lavoratore || ""} onValueChange={(v) => set("tipo_lavoratore", v)}>
                        <SelectTrigger data-testid="tipo-lavoratore"><SelectValue placeholder="-" /></SelectTrigger>
                        <SelectContent>
                            <SelectItem value="dipendente">Dipendente</SelectItem>
                            <SelectItem value="autonomo">Autonomo</SelectItem>
                            <SelectItem value="parasubordinato">Parasubordinato</SelectItem>
                            <SelectItem value="pensionato">Pensionato</SelectItem>
                            <SelectItem value="altro">Altro</SelectItem>
                        </SelectContent>
                    </Select>
                </div>
                <div><Label>Professione</Label><Input value={f.professione || ""} onChange={(e) => set("professione", e.target.value)} /></div>
                <div><Label>N. figli</Label><Input type="number" value={f.numero_figli || 0} onChange={(e) => set("numero_figli", parseInt(e.target.value) || 0)} /></div>
                <div><Label>Figli a carico</Label><Input type="number" value={f.numero_figli_a_carico || 0} onChange={(e) => set("numero_figli_a_carico", parseInt(e.target.value) || 0)} /></div>
                <div><Label>Reddito annuo lordo €</Label><Input type="number" step="0.01" value={f.reddito_annuo_lordo || ""} onChange={(e) => set("reddito_annuo_lordo", parseFloat(e.target.value) || null)} /></div>
                <div><Label>Inizio contribuzione</Label><Input type="date" value={f.data_inizio_contribuzione || ""} onChange={(e) => set("data_inizio_contribuzione", e.target.value)} /></div>
                <div><Label>Settimane contributive</Label><Input type="number" value={f.settimane_contributive || ""} onChange={(e) => set("settimane_contributive", parseInt(e.target.value) || null)} /></div>
                <div><Label>Email</Label><Input value={f.email || ""} onChange={(e) => set("email", e.target.value)} /></div>
                <div><Label>Telefono</Label><Input value={f.telefono || ""} onChange={(e) => set("telefono", e.target.value)} /></div>
                <div><Label>Cellulare</Label><Input value={f.cellulare || ""} onChange={(e) => set("cellulare", e.target.value)} /></div>
                <div><Label>IBAN</Label><Input value={f.iban || ""} onChange={(e) => set("iban", e.target.value)} /></div>
                <div>
                    <Label>Preferenza pagamento</Label>
                    <Select value={f.preferenza_pagamento || "__none__"} onValueChange={(v) => set("preferenza_pagamento", v === "__none__" ? null : v)}>
                        <SelectTrigger data-testid="anag-pref-pag"><SelectValue placeholder="—" /></SelectTrigger>
                        <SelectContent>
                            <SelectItem value="__none__">— nessuna preferenza —</SelectItem>
                            {mezzi.map((m) => (
                                <SelectItem key={m.codice} value={m.codice}>{m.label}</SelectItem>
                            ))}
                        </SelectContent>
                    </Select>
                    {f.ultimo_mezzo_pagamento && (
                        <div className="text-[10px] text-slate-500 mt-1">
                            Ultimo utilizzato: <strong>{f.ultimo_mezzo_pagamento}</strong>
                            {f.ultimo_mezzo_pagamento_data && ` il ${f.ultimo_mezzo_pagamento_data}`}
                        </div>
                    )}
                </div>
                <div className="col-span-2">
                    <Label>Indirizzo</Label>
                    <AddressAutocomplete
                        value={f.indirizzo || ""}
                        onChange={(v) => set("indirizzo", v)}
                        onSelect={(p) => {
                            // riempi tutti i campi indirizzo in un colpo + lat/lng
                            setF((prev) => ({
                                ...prev,
                                indirizzo: p.indirizzo || prev.indirizzo,
                                comune: p.comune || prev.comune,
                                cap: p.cap || prev.cap,
                                provincia: (p.provincia || "").slice(0, 2).toUpperCase() || prev.provincia,
                                lat: p.lat,
                                lng: p.lng,
                                indirizzo_geocoded: p.display_name,
                            }));
                            toast.success("Indirizzo geolocalizzato automaticamente");
                        }}
                        testid="anag-indirizzo-autocomplete"
                    />
                </div>
                <div><Label>Comune</Label><Input value={f.comune || ""} onChange={(e) => set("comune", e.target.value)} /></div>
                <div><Label>Provincia</Label><Input maxLength={2} value={f.provincia || ""} onChange={(e) => set("provincia", e.target.value.toUpperCase())} /></div>
                <div><Label>CAP</Label><Input value={f.cap || ""} onChange={(e) => set("cap", e.target.value)} /></div>
                <div>
                    <Label>Tipologia lavoratore</Label>
                    <Select value={f.tipologia_lavoratore || "__none__"} onValueChange={(v) => set("tipologia_lavoratore", v === "__none__" ? null : v)}>
                        <SelectTrigger data-testid="anag-tipo-lavoro"><SelectValue placeholder="—" /></SelectTrigger>
                        <SelectContent>
                            <SelectItem value="__none__">— non specificato —</SelectItem>
                            <SelectItem value="dipendente">Dipendente</SelectItem>
                            <SelectItem value="autonomo">Autonomo / Partita IVA</SelectItem>
                            <SelectItem value="professionista">Professionista (albo)</SelectItem>
                            <SelectItem value="imprenditore">Imprenditore</SelectItem>
                            <SelectItem value="pensionato">Pensionato</SelectItem>
                            <SelectItem value="disoccupato">Disoccupato</SelectItem>
                            <SelectItem value="studente">Studente</SelectItem>
                            <SelectItem value="casalinga">Casalinga / Casalingo</SelectItem>
                            <SelectItem value="altro">Altro</SelectItem>
                        </SelectContent>
                    </Select>
                </div>
                <div>
                    <Label>Professione</Label>
                    <Input value={f.professione || ""} onChange={(e) => set("professione", e.target.value)}
                           placeholder="Es: medico, geometra, impiegato" />
                </div>
                <div>
                    <Label>Datore di lavoro</Label>
                    <Input value={f.datore_lavoro || ""} onChange={(e) => set("datore_lavoro", e.target.value)} />
                </div>
            </div>
            <div className="mt-4">
                <Label>Note</Label>
                <Textarea rows={3} value={f.note || ""} onChange={(e) => set("note", e.target.value)} />
            </div>
            <div className="mt-4 flex justify-end gap-2">
                <Button variant="outline" onClick={() => { setEditing(false); setF({ ...ana }); }}>Annulla</Button>
                <Button onClick={save} className="bg-sky-700 hover:bg-sky-800" data-testid="anag-save-edit">Salva</Button>
            </div>
        </Card>
    );
}

function PolizzeTab({ polizze }) {
    return (
        <Card className="border-slate-200 mt-4 overflow-hidden">
            {polizze.length === 0 ? (
                <div className="p-8 text-center text-slate-500 text-sm">Nessuna polizza intestata.</div>
            ) : (
                <table className="tbl w-full">
                    <thead><tr><th>Numero</th><th>Compagnia</th><th>Ramo</th><th>Stato</th><th>Effetto</th><th>Scadenza</th><th className="text-right">Premio</th></tr></thead>
                    <tbody>
                        {polizze.map((p) => (
                            <tr key={p.id}>
                                <td><Link to={`/polizze/${p.id}`} className="text-sky-700 hover:underline">{p.numero_polizza}</Link></td>
                                <td>{p.compagnia_nome}</td>
                                <td>{p.ramo}</td>
                                <td><StatusBadge stato={p.stato} /></td>
                                <td className="num">{fmtDate(p.effetto)}</td>
                                <td className="num">{fmtDate(p.scadenza)}</td>
                                <td className="num text-right">{fmtEur(p.premio_lordo)}</td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            )}
        </Card>
    );
}

function AlberoGenealogico({ ana, canEdit, onReload }) {
    const [open, setOpen] = useState(false);
    const [target, setTarget] = useState("");
    const [rel, setRel] = useState("figlio");
    const [relInv, setRelInv] = useState("genitore");
    const [lavoratore, setLavoratore] = useState(false);
    const [aCarico, setACarico] = useState(true);
    const [handicap, setHandicap] = useState(false);
    const [options, setOptions] = useState([]);
    const [editing, setEditing] = useState(null);
    const [network, setNetwork] = useState(null);
    useEffect(() => { api.get("/anagrafiche").then((r) => setOptions(r.data.filter((a) => a.id !== ana.id))); }, [ana.id]);
    useEffect(() => { api.get(`/anagrafiche/${ana.id}/network`).then((r) => setNetwork(r.data)).catch(() => setNetwork(null)); }, [ana.id, ana.relazioni_risolte?.length]);

    // mostra attributi differenti in base alla relazione
    const showLavoratore = rel === "coniuge";
    const showCarico = rel === "coniuge" || rel === "figlio";
    const showHandicap = rel === "figlio";

    // Lista delle relazioni possibili. Le coppie sono auto-suggerite ma modificabili.
    const RELAZIONI_PERSONA = ["genitore", "figlio", "coniuge", "fratello", "nonno", "nipote", "zio", "cugino", "altro"];
    const RELAZIONI_AZIENDA = ["legale_rappresentante", "rappresenta", "socio", "dipendente_di", "datore_lavoro_di"];
    const TUTTE_RELAZIONI = [...RELAZIONI_PERSONA, ...RELAZIONI_AZIENDA];
    const INVERSE_MAP = {
        genitore: "figlio", figlio: "genitore", coniuge: "coniuge",
        fratello: "fratello", nonno: "nipote", nipote: "nonno",
        zio: "nipote", cugino: "cugino",
        legale_rappresentante: "rappresenta", rappresenta: "legale_rappresentante",
        socio: "socio",
        dipendente_di: "datore_lavoro_di", datore_lavoro_di: "dipendente_di",
        altro: "altro",
    };

    const onRelChange = (r) => {
        setRel(r);
        if (INVERSE_MAP[r]) setRelInv(INVERSE_MAP[r]);
    };

    const aggiungi = async () => {
        if (!target) return;
        try {
            const body = {
                anagrafica_id: target, relazione: rel, relazione_inversa: relInv,
            };
            if (showLavoratore) body.lavoratore = lavoratore;
            if (showCarico) body.a_carico = aCarico;
            if (showHandicap) body.handicap = handicap;
            await api.post(`/anagrafiche/${ana.id}/relazioni`, body);
            toast.success("Relazione aggiunta");
            setOpen(false); setTarget("");
            setLavoratore(false); setACarico(true); setHandicap(false);
            onReload();
        } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
    };
    const rimuovi = async (tid) => {
        if (!window.confirm("Rimuovere la relazione?")) return;
        await api.delete(`/anagrafiche/${ana.id}/relazioni/${tid}`); toast.success("Relazione rimossa"); onReload();
    };

    const saveEdit = async () => {
        if (!editing) return;
        try {
            const body = {};
            if (editing.relazione === "coniuge") body.lavoratore = !!editing.lavoratore;
            if (editing.relazione === "coniuge" || editing.relazione === "figlio") body.a_carico = !!editing.a_carico;
            if (editing.relazione === "figlio") body.handicap = !!editing.handicap;
            await api.patch(`/anagrafiche/${ana.id}/relazioni/${editing.id}`, body);
            toast.success("Attributi aggiornati");
            setEditing(null); onReload();
        } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
    };

    return (
        <>
        {network && network.collegati.length > 0 && (
            <NetworkPositionCard network={network} />
        )}
        <Card className="p-6 border-slate-200 mt-4">
            <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-2"><GitBranch size={18} className="text-sky-700" /><h3 className="font-medium">Relazioni familiari</h3></div>
                {canEdit && (
                    <Dialog open={open} onOpenChange={setOpen}>
                        <DialogTrigger asChild>
                            <Button size="sm" variant="outline" data-testid="add-relation-button"><UserPlus size={14} className="mr-1" />Aggiungi</Button>
                        </DialogTrigger>
                        <DialogContent>
                            <DialogHeader><DialogTitle>Aggiungi relazione</DialogTitle></DialogHeader>
                            <div className="space-y-3 py-2">
                                <div>
                                    <Label>Anagrafica collegata</Label>
                                    <Select value={target} onValueChange={setTarget}>
                                        <SelectTrigger data-testid="rel-target"><SelectValue placeholder="Seleziona..." /></SelectTrigger>
                                        <SelectContent>
                                            {options.map((o) => <SelectItem key={o.id} value={o.id}>{o.ragione_sociale}</SelectItem>)}
                                        </SelectContent>
                                    </Select>
                                </div>
                                <div className="grid grid-cols-2 gap-3">
                                    <div>
                                        <Label>{ana.ragione_sociale} &egrave;</Label>
                                        <Select value={rel} onValueChange={onRelChange}><SelectTrigger data-testid="rel-relazione"><SelectValue /></SelectTrigger>
                                            <SelectContent>
                                                <div className="px-2 py-1 text-[10px] uppercase font-semibold text-slate-500">Famiglia</div>
                                                {RELAZIONI_PERSONA.map((r) => <SelectItem key={r} value={r}>{r}</SelectItem>)}
                                                <div className="px-2 py-1 text-[10px] uppercase font-semibold text-slate-500 border-t mt-1 pt-2">Aziende / Lavoro</div>
                                                {RELAZIONI_AZIENDA.map((r) => <SelectItem key={r} value={r}>{r.replace(/_/g, " ")}</SelectItem>)}
                                            </SelectContent>
                                        </Select>
                                    </div>
                                    <div>
                                        <Label>{"L'altro è"}</Label>
                                        <Select value={relInv} onValueChange={setRelInv}><SelectTrigger><SelectValue /></SelectTrigger>
                                            <SelectContent>
                                                {TUTTE_RELAZIONI.map((r) => <SelectItem key={r} value={r}>{r.replace(/_/g, " ")}</SelectItem>)}
                                            </SelectContent>
                                        </Select>
                                    </div>
                                </div>

                                {(showLavoratore || showCarico || showHandicap) && (
                                    <div className="bg-amber-50 border border-amber-200 rounded-md p-3 space-y-2">
                                        <div className="text-xs font-semibold text-amber-900 uppercase tracking-wider">
                                            Dati per assegno familiare / nucleo
                                        </div>
                                        {showLavoratore && (
                                            <label className="flex items-center gap-2 text-sm cursor-pointer">
                                                <input
                                                    type="checkbox" checked={lavoratore}
                                                    onChange={(e) => setLavoratore(e.target.checked)}
                                                    data-testid="rel-lavoratore"
                                                />
                                                Il coniuge è lavoratore (incide sull&apos;assegno familiare)
                                            </label>
                                        )}
                                        {showCarico && (
                                            <label className="flex items-center gap-2 text-sm cursor-pointer">
                                                <input
                                                    type="checkbox" checked={aCarico}
                                                    onChange={(e) => setACarico(e.target.checked)}
                                                    data-testid="rel-carico"
                                                />
                                                A carico fiscalmente
                                            </label>
                                        )}
                                        {showHandicap && (
                                            <label className="flex items-center gap-2 text-sm cursor-pointer">
                                                <input
                                                    type="checkbox" checked={handicap}
                                                    onChange={(e) => setHandicap(e.target.checked)}
                                                    data-testid="rel-handicap"
                                                />
                                                Figlio con handicap (L.104)
                                            </label>
                                        )}
                                    </div>
                                )}
                            </div>
                            <DialogFooter><Button onClick={aggiungi} className="bg-sky-700 hover:bg-sky-800" data-testid="rel-save">Salva</Button></DialogFooter>
                        </DialogContent>
                    </Dialog>
                )}
            </div>
            {!ana.relazioni_risolte?.length ? (
                <div className="text-sm text-slate-500 py-6 text-center">Nessuna relazione registrata.</div>
            ) : (
                <div className="relative">
                    <div className="flex justify-center mb-8">
                        <div className="tree-node bg-sky-50 border-sky-200 font-medium">{ana.ragione_sociale}</div>
                    </div>
                    <div className="flex flex-wrap justify-center gap-4">
                        {ana.relazioni_risolte.map((r) => {
                            const badges = [];
                            if (r.relazione === "coniuge") {
                                badges.push(r.lavoratore ? { t: "lavoratore", c: "bg-sky-100 text-sky-800" } : { t: "non lavoratore", c: "bg-slate-100 text-slate-700" });
                            }
                            if (r.relazione === "coniuge" || r.relazione === "figlio") {
                                if (r.a_carico) badges.push({ t: "a carico", c: "bg-emerald-100 text-emerald-800" });
                                else if (r.a_carico === false) badges.push({ t: "non a carico", c: "bg-slate-100 text-slate-700" });
                            }
                            if (r.relazione === "figlio" && r.handicap) {
                                badges.push({ t: "L.104", c: "bg-amber-100 text-amber-800" });
                            }
                            return (
                            <div key={r.id} className="flex flex-col items-center" data-testid={`relation-${r.id}`}>
                                <div className="h-6 w-px bg-slate-300 -mt-8" />
                                <div className="text-[10px] uppercase tracking-widest text-slate-500 mb-1">{r.relazione}</div>
                                <div className="tree-node">
                                    <Link to={`/anagrafiche/${r.id}`} className="text-sky-700 hover:underline">{r.ragione_sociale}</Link>
                                    <div className="text-[11px] text-slate-500 num">{r.codice_fiscale || "-"}</div>
                                    {badges.length > 0 && (
                                        <div className="flex flex-wrap gap-1 mt-1 justify-center">
                                            {badges.map((b, i) => (
                                                <span key={i} className={`text-[10px] px-1.5 py-0.5 rounded ${b.c}`}>{b.t}</span>
                                            ))}
                                        </div>
                                    )}
                                    {canEdit && (
                                        <div className="flex gap-2 justify-center mt-1">
                                            {(r.relazione === "coniuge" || r.relazione === "figlio") && (
                                                <button
                                                    onClick={() => setEditing(r)}
                                                    className="text-[10px] text-sky-700 hover:underline"
                                                    data-testid={`relation-edit-${r.id}`}
                                                >
                                                    modifica
                                                </button>
                                            )}
                                            <button onClick={() => rimuovi(r.id)} className="text-[10px] text-rose-600 hover:underline">rimuovi</button>
                                        </div>
                                    )}
                                </div>
                            </div>
                        );
                        })}
                    </div>
                </div>
            )}

            {editing && (
                <Dialog open onOpenChange={(o) => !o && setEditing(null)}>
                    <DialogContent>
                        <DialogHeader>
                            <DialogTitle>Attributi relazione: {editing.ragione_sociale}</DialogTitle>
                        </DialogHeader>
                        <div className="space-y-2 py-2">
                            <div className="text-xs text-slate-500">Relazione: <b>{editing.relazione}</b></div>
                            {editing.relazione === "coniuge" && (
                                <label className="flex items-center gap-2 text-sm cursor-pointer">
                                    <input
                                        type="checkbox"
                                        checked={!!editing.lavoratore}
                                        onChange={(e) => setEditing({ ...editing, lavoratore: e.target.checked })}
                                        data-testid="rel-edit-lavoratore"
                                    />
                                    Il coniuge è lavoratore
                                </label>
                            )}
                            {(editing.relazione === "coniuge" || editing.relazione === "figlio") && (
                                <label className="flex items-center gap-2 text-sm cursor-pointer">
                                    <input
                                        type="checkbox"
                                        checked={!!editing.a_carico}
                                        onChange={(e) => setEditing({ ...editing, a_carico: e.target.checked })}
                                        data-testid="rel-edit-carico"
                                    />
                                    A carico fiscalmente
                                </label>
                            )}
                            {editing.relazione === "figlio" && (
                                <label className="flex items-center gap-2 text-sm cursor-pointer">
                                    <input
                                        type="checkbox"
                                        checked={!!editing.handicap}
                                        onChange={(e) => setEditing({ ...editing, handicap: e.target.checked })}
                                        data-testid="rel-edit-handicap"
                                    />
                                    Figlio con handicap (L.104)
                                </label>
                            )}
                        </div>
                        <DialogFooter>
                            <Button variant="outline" onClick={() => setEditing(null)}>Annulla</Button>
                            <Button onClick={saveEdit} className="bg-sky-700 hover:bg-sky-800" data-testid="rel-edit-save">Salva</Button>
                        </DialogFooter>
                    </DialogContent>
                </Dialog>
            )}
        </Card>
        </>
    );
}

function NetworkPositionCard({ network }) {
    const { root, collegati, totali } = network;
    const fmt = (n) => (n || 0).toLocaleString("it-IT", { style: "currency", currency: "EUR" });
    return (
        <Card className="p-6 border-slate-200 mt-4" data-testid="network-position-card">
            <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                    <Users size={18} className="text-emerald-700" />
                    <h3 className="font-medium">Posizione assicurativa del network</h3>
                </div>
                <div className="text-xs text-slate-500">{totali.n_persone} entità collegate</div>
            </div>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
                <div className="bg-slate-50 rounded p-3">
                    <div className="text-[10px] uppercase tracking-widest text-slate-500">Polizze attive</div>
                    <div className="text-lg font-bold text-slate-800 num">{totali.n_polizze_attive}</div>
                </div>
                <div className="bg-slate-50 rounded p-3">
                    <div className="text-[10px] uppercase tracking-widest text-slate-500">Preventivi</div>
                    <div className="text-lg font-bold text-sky-700 num">{totali.n_preventivi}</div>
                </div>
                <div className="bg-emerald-50 rounded p-3">
                    <div className="text-[10px] uppercase tracking-widest text-emerald-700">Premio totale</div>
                    <div className="text-lg font-bold text-emerald-800 num">{fmt(totali.premio_totale)}</div>
                </div>
                <div className="bg-sky-50 rounded p-3">
                    <div className="text-[10px] uppercase tracking-widest text-sky-700">Provvigioni totali</div>
                    <div className="text-lg font-bold text-sky-800 num">{fmt(totali.provvigioni_totale)}</div>
                </div>
            </div>
            <div className="overflow-x-auto">
                <table className="w-full text-sm">
                    <thead className="text-[11px] uppercase tracking-wider text-slate-500 border-b">
                        <tr>
                            <th className="text-left py-2 pr-2">Anagrafica</th>
                            <th className="text-left py-2 pr-2">Relazione</th>
                            <th className="text-right py-2 pr-2">Attive</th>
                            <th className="text-right py-2 pr-2">Preventivi</th>
                            <th className="text-right py-2 pr-2">Premio</th>
                            <th className="text-right py-2 pr-2">Provvigioni</th>
                        </tr>
                    </thead>
                    <tbody>
                        <tr className="border-b border-slate-100 bg-sky-50/40">
                            <td className="py-2 pr-2 font-semibold">
                                <Link to={`/anagrafiche/${root.id}`} className="text-sky-700 hover:underline">{root.ragione_sociale}</Link>
                            </td>
                            <td className="py-2 pr-2 text-xs text-slate-500">— scheda corrente —</td>
                            <td className="text-right py-2 pr-2 num">{root.n_polizze_attive}</td>
                            <td className="text-right py-2 pr-2 num">{root.n_preventivi}</td>
                            <td className="text-right py-2 pr-2 num font-semibold">{fmt(root.premio_totale)}</td>
                            <td className="text-right py-2 pr-2 num font-semibold text-emerald-700">{fmt(root.provvigioni_totale)}</td>
                        </tr>
                        {collegati.map((c) => (
                            <tr key={c.id} className="border-b border-slate-100 hover:bg-slate-50">
                                <td className="py-2 pr-2">
                                    <Link to={`/anagrafiche/${c.id}`} className="text-sky-700 hover:underline">{c.ragione_sociale}</Link>
                                </td>
                                <td className="py-2 pr-2 text-xs text-slate-600 capitalize">{(c.relazione || "—").replace(/_/g, " ")}</td>
                                <td className="text-right py-2 pr-2 num">{c.n_polizze_attive}</td>
                                <td className="text-right py-2 pr-2 num">{c.n_preventivi}</td>
                                <td className="text-right py-2 pr-2 num">{fmt(c.premio_totale)}</td>
                                <td className="text-right py-2 pr-2 num text-emerald-700">{fmt(c.provvigioni_totale)}</td>
                            </tr>
                        ))}
                        <tr className="border-t-2 border-slate-300 font-bold">
                            <td colSpan={2} className="py-2 pr-2 text-right uppercase text-xs tracking-widest">Totale network</td>
                            <td className="text-right py-2 pr-2 num">{totali.n_polizze_attive}</td>
                            <td className="text-right py-2 pr-2 num">{totali.n_preventivi}</td>
                            <td className="text-right py-2 pr-2 num">{fmt(totali.premio_totale)}</td>
                            <td className="text-right py-2 pr-2 num text-emerald-700">{fmt(totali.provvigioni_totale)}</td>
                        </tr>
                    </tbody>
                </table>
            </div>
        </Card>
    );
}

function InterviewTab({ anagrafica_id, canEdit }) {
    const [list, setList] = useState([]);
    const load = () => api.get(`/anagrafiche/${anagrafica_id}/interviste`).then((r) => setList(r.data));
    useEffect(() => { load(); /* eslint-disable-next-line */ }, [anagrafica_id]);
    const [f, setF] = useState({ note: "", situazione_familiare: {}, situazione_lavorativa: {}, obiettivi: {} });

    const salva = async () => {
        try {
            await api.post(`/anagrafiche/${anagrafica_id}/interviste`, f);
            toast.success("Intervista salvata"); load();
            setF({ note: "", situazione_familiare: {}, situazione_lavorativa: {}, obiettivi: {} });
        } catch (e) { toast.error("Errore: " + e.message); }
    };

    return (
        <div className="space-y-6 mt-4">
            {canEdit && (
                <Card className="p-6 border-slate-200">
                    <div className="flex items-center gap-2 mb-4"><ClipboardList size={18} className="text-sky-700" /><h3 className="font-medium">Nuova intervista</h3></div>
                    <Textarea rows={4} placeholder="Note generali..." value={f.note} onChange={(e) => setF((p) => ({ ...p, note: e.target.value }))} />
                    <div className="mt-3 text-right">
                        <Button onClick={salva} data-testid="intervista-save-button" className="bg-sky-700 hover:bg-sky-800">Salva</Button>
                    </div>
                </Card>
            )}
            <Card className="p-6 border-slate-200">
                <h3 className="font-medium mb-3">Interviste precedenti ({list.length})</h3>
                {list.length === 0 ? <div className="text-sm text-slate-500">Nessuna intervista.</div> : (
                    <ul className="divide-y divide-slate-100">
                        {list.map((i) => (
                            <li key={i.id} className="py-3 text-sm">
                                <div className="font-medium text-slate-900 num">{fmtDate(i.data_intervista)}</div>
                                {i.note && <div className="text-xs text-slate-600 mt-1">{i.note}</div>}
                            </li>
                        ))}
                    </ul>
                )}
            </Card>
        </div>
    );
}

const DIARIO_TIPI = [
    { v: "telefonata", l: "Telefonata", i: <Phone size={12} /> },
    { v: "incontro", l: "Incontro", i: <Calendar size={12} /> },
    { v: "email", l: "Email", i: <Mail size={12} /> },
    { v: "whatsapp", l: "WhatsApp", i: <Phone size={12} /> },
    { v: "chat", l: "Chat", i: <BookText size={12} /> },
    { v: "documento", l: "Documento", i: <BookText size={12} /> },
    { v: "nota", l: "Nota", i: <BookText size={12} /> },
    { v: "altro", l: "Altro", i: <BookText size={12} /> },
];

function DiarioTab({ anagrafica_id, canEdit }) {
    const [list, setList] = useState(null);
    const [open, setOpen] = useState(false);
    const [editing, setEditing] = useState(null);
    const load = () => api.get(`/anagrafiche/${anagrafica_id}/diario`).then((r) => setList(r.data));
    useEffect(() => { load(); /* eslint-disable-next-line */ }, [anagrafica_id]);

    const elimina = async (id) => {
        try { await api.delete(`/diario/${id}`); toast.success("Eliminato"); load(); }
        catch { toast.error("Errore"); }
    };

    return (
        <div className="mt-4">
            <div className="flex items-center justify-between mb-3">
                <span className="text-sm text-slate-500 num">{list ? `${list.length} voci` : ""}</span>
                {canEdit && (
                    <Dialog open={open || !!editing} onOpenChange={(o) => { if (!o) { setOpen(false); setEditing(null); } }}>
                        <DialogTrigger asChild>
                            <Button onClick={() => setOpen(true)} className="bg-sky-700 hover:bg-sky-800" data-testid="diario-new-button">
                                <Plus size={14} className="mr-1" /> Nuova voce
                            </Button>
                        </DialogTrigger>
                        <DiarioForm anagrafica_id={anagrafica_id} editing={editing} onClose={() => { setOpen(false); setEditing(null); load(); }} />
                    </Dialog>
                )}
            </div>
            <Card className="border-slate-200 overflow-hidden">
                {list === null ? <Loading /> : list.length === 0 ? <div className="p-8 text-center text-slate-500 text-sm">Nessuna voce di diario.</div> : (
                    <ul className="divide-y divide-slate-100">
                        {list.map((v) => {
                            const tipo = DIARIO_TIPI.find((t) => t.v === v.tipo) || DIARIO_TIPI[4];
                            return (
                                <li key={v.id} className="px-4 py-3 hover:bg-slate-50 flex gap-3" data-testid={`diario-${v.id}`}>
                                    <div className="w-9 h-9 rounded-full bg-sky-50 text-sky-700 flex items-center justify-center shrink-0">{tipo.i}</div>
                                    <div className="flex-1 min-w-0">
                                        <div className="flex items-center justify-between gap-2">
                                            <div className="font-medium text-sm">{v.titolo}</div>
                                            <span className="badge badge-neutral">{tipo.l}</span>
                                        </div>
                                        {v.descrizione && <div className="text-xs text-slate-600 mt-1 whitespace-pre-line">{v.descrizione}</div>}
                                        <div className="text-[11px] text-slate-400 mt-2 num">
                                            {fmtDate(v.data_evento)} · {v.autore_nome || "—"}
                                        </div>
                                    </div>
                                    <RowActions onEdit={canEdit ? () => setEditing(v) : null} onDelete={() => elimina(v.id)} label="voce" />
                                </li>
                            );
                        })}
                    </ul>
                )}
            </Card>
        </div>
    );
}

function DiarioForm({ anagrafica_id, editing, onClose }) {
    const [f, setF] = useState(editing || {
        data_evento: new Date().toISOString().slice(0, 10),
        tipo: "nota", titolo: "", descrizione: "",
    });
    const set = (k, v) => setF((p) => ({ ...p, [k]: v }));
    const save = async () => {
        if (!f.titolo) { toast.error("Titolo obbligatorio"); return; }
        try {
            if (editing) await api.put(`/diario/${editing.id}`, f);
            else await api.post(`/anagrafiche/${anagrafica_id}/diario`, f);
            toast.success("Salvato"); onClose();
        } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
    };

    return (
        <DialogContent>
            <DialogHeader><DialogTitle>{editing ? "Modifica voce" : "Nuova voce di diario"}</DialogTitle></DialogHeader>
            <div className="space-y-3 py-2">
                <div className="grid grid-cols-2 gap-3">
                    <div><Label>Data evento</Label><Input type="date" value={f.data_evento || ""} onChange={(e) => set("data_evento", e.target.value)} /></div>
                    <div>
                        <Label>Tipo</Label>
                        <Select value={f.tipo} onValueChange={(v) => set("tipo", v)}>
                            <SelectTrigger><SelectValue /></SelectTrigger>
                            <SelectContent>{DIARIO_TIPI.map((t) => <SelectItem key={t.v} value={t.v}>{t.l}</SelectItem>)}</SelectContent>
                        </Select>
                    </div>
                </div>
                <div><Label>Titolo *</Label><Input data-testid="diario-titolo-input" value={f.titolo || ""} onChange={(e) => set("titolo", e.target.value)} /></div>
                <div><Label>Descrizione</Label><Textarea rows={5} value={f.descrizione || ""} onChange={(e) => set("descrizione", e.target.value)} /></div>
            </div>
            <DialogFooter><Button onClick={save} data-testid="diario-save-button" className="bg-sky-700 hover:bg-sky-800">{editing ? "Aggiorna" : "Salva"}</Button></DialogFooter>
        </DialogContent>
    );
}

function AllegatiTab({ entita_tipo, entita_id, canEdit }) {
    const [list, setList] = useState(null);
    const [uploading, setUploading] = useState(false);

    const load = () => api.get("/allegati", { params: { entita_tipo, entita_id } }).then((r) => setList(r.data));
    useEffect(() => { load(); /* eslint-disable-next-line */ }, [entita_tipo, entita_id]);

    const handleFile = async (file) => {
        if (!file) return;
        setUploading(true);
        const fd = new FormData(); fd.append("file", file);
        try {
            await api.post(
                `/allegati?entita_tipo=${entita_tipo}&entita_id=${entita_id}`,
                fd, { headers: { "Content-Type": "multipart/form-data" } },
            );
            toast.success("File caricato"); load();
        } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
        finally { setUploading(false); }
    };

    const elimina = async (id) => {
        try { await api.delete(`/allegati/${id}`); toast.success("Eliminato"); load(); }
        catch { toast.error("Errore"); }
    };

    return (
        <Card className="p-6 border-slate-200 mt-4">
            <div className="flex items-center justify-between mb-4">
                <h3 className="font-medium">Documenti allegati</h3>
                {canEdit && (
                    <label className="inline-flex items-center gap-2 cursor-pointer">
                        <input type="file" className="hidden" onChange={(e) => handleFile(e.target.files?.[0])} data-testid="allegato-upload-input" />
                        <Button asChild className="bg-sky-700 hover:bg-sky-800" disabled={uploading}>
                            <span><Upload size={14} className="mr-1" /> {uploading ? "Caricamento..." : "Carica file"}</span>
                        </Button>
                    </label>
                )}
            </div>
            {list === null ? <Loading /> : list.length === 0 ? (
                <div className="text-center py-10 text-sm text-slate-500">
                    <Paperclip size={28} className="mx-auto text-slate-300 mb-2" />
                    Nessun documento caricato. Trascina un file o clicca &quot;Carica file&quot;.
                </div>
            ) : (
                <ul className="divide-y divide-slate-100">
                    {list.map((a) => (
                        <li key={a.id} className="py-3 flex items-center gap-3" data-testid={`allegato-${a.id}`}>
                            <Paperclip size={16} className="text-slate-400" />
                            <div className="flex-1 min-w-0">
                                <a
                                    href={`${api.defaults.baseURL}/allegati/${a.id}/download`}
                                    target="_blank" rel="noreferrer"
                                    className="text-sm text-sky-700 hover:underline truncate block"
                                >
                                    {a.nome_file}
                                </a>
                                <div className="text-[11px] text-slate-500 num">
                                    {fmtDate(a.created_at)} · {(a.size / 1024).toFixed(0)} KB · {a.content_type}
                                </div>
                            </div>
                            <RowActions onDelete={() => elimina(a.id)} canEdit={false} label="allegato" />
                        </li>
                    ))}
                </ul>
            )}
        </Card>
    );
}

function PensioneTab({ anagrafica_id, ana, canEdit, onReload }) {
    const [preview, setPreview] = useState(null);
    const [risultati, setRisultati] = useState(null);
    const [params, setParams] = useState({ percentuale_invalidita: 75 });
    const [uploading, setUploading] = useState(false);
    const fileRef = useRef(null);

    const loadPreview = () => {
        api.get(`/anagrafiche/${anagrafica_id}/calcolo-pensione/preview`).then((r) => setPreview(r.data));
    };
    useEffect(loadPreview, [anagrafica_id]);

    const calcola = async () => {
        try {
            const res = await api.post(`/anagrafiche/${anagrafica_id}/calcolo-pensione/calcola`, params);
            setRisultati(res.data);
            toast.success("Calcolo completato");
        } catch (e) { toast.error("Errore: " + e.message); }
    };

    const uploadEstratto = async (file) => {
        if (!file) return;
        setUploading(true);
        const fd = new FormData();
        fd.append("file", file);
        try {
            const r = await api.post(`/anagrafiche/${anagrafica_id}/calcolo-pensione/auto-da-estratto`, fd,
                { headers: { "Content-Type": "multipart/form-data" }, timeout: 60000 });
            const p = r.data.parsed;
            toast.success(`Estratto importato: ${p.settimane_contributive} settimane, ${p.anni_stimati} anni`);
            loadPreview();
            onReload?.();
        } catch (e) {
            toast.error(e.response?.data?.detail || "Errore");
        } finally { setUploading(false); }
    };

    if (!preview) return <Loading />;

    return (
        <div className="space-y-6 mt-4" data-testid="pensione-tab">
            <Card className="p-6 border-slate-200">
                <h3 className="font-medium mb-4 flex items-center gap-2">
                    <Calculator size={18} className="text-sky-700" /> Parametri (precompilati dall&apos;anagrafica)
                </h3>

                {/* Toolbar caricamento estratto contributivo */}
                {canEdit && (
                    <div className="bg-sky-50 border border-sky-200 rounded-md p-3 mb-4 flex items-center justify-between gap-3 flex-wrap">
                        <div className="text-xs text-sky-900 flex-1">
                            <strong>Auto-popola</strong> caricando il PDF dell&apos;estratto contributivo INPS:
                            settimane, anni, retribuzione media e dati anagrafici verranno estratti automaticamente.
                        </div>
                        <input
                            ref={fileRef}
                            type="file"
                            accept=".pdf"
                            className="hidden"
                            onChange={(e) => uploadEstratto(e.target.files?.[0])}
                            data-testid="ec-upload-input"
                        />
                        <Button
                            type="button" variant="outline" size="sm"
                            onClick={() => fileRef.current?.click()}
                            disabled={uploading}
                            data-testid="ec-upload-button"
                        >
                            <Upload size={13} className="mr-1" /> {uploading ? "Caricamento..." : "Carica estratto INPS"}
                        </Button>
                    </div>
                )}

                {preview.warnings?.filter(Boolean).length > 0 && (
                    <div className="mb-4 space-y-1">
                        {preview.warnings.filter(Boolean).map((w, i) => (
                            <div key={i} className="text-xs bg-amber-50 border border-amber-200 text-amber-900 rounded px-3 py-2">⚠ {w}</div>
                        ))}
                    </div>
                )}

                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                    <Field label="Età" value={`${preview.eta} anni`} />
                    <Field label="Stato civile" value={preview.stato_civile || "—"} hint={preview.coniugato ? "Coniuge presente" : "Non coniugato"} />
                    <Field label="Tipo lavoratore" value={preview.tipo_lavoratore || "—"} />
                    <Field label="Familiari aventi diritto" value={preview.numero_familiari} hint={preview.requisiti_superstite_ok ? "Pensione superstite spettante" : "Pensione superstite NON spettante"} />
                    <Field label="Settimane contributive" value={preview.settimane_contributive} />
                    <Field label="Reddito annuo lordo" value={fmtEur(preview.reddito_annuo_lordo)} />
                    <Field label="Figli a carico" value={preview.numero_figli_a_carico} />
                    <Field label="Professione" value={preview.professione || "—"} />
                </div>

                <div className="mt-4 pt-4 border-t border-slate-100 grid grid-cols-3 gap-3 items-end">
                    <div>
                        <Label>% Invalidità (per pensione invalidità)</Label>
                        <Input
                            data-testid="pensione-invalidita-input"
                            type="number"
                            value={params.percentuale_invalidita || ""}
                            onChange={(e) => setParams((p) => ({ ...p, percentuale_invalidita: parseFloat(e.target.value) || 0 }))}
                        />
                    </div>
                    <div className="text-xs text-slate-500">
                        {!canEdit && "Solo lo staff può aggiornare i dati anagrafici."}
                    </div>
                    <Button onClick={calcola} data-testid="pensione-calcola-button" className="bg-sky-700 hover:bg-sky-800">
                        Calcola tutte le pensioni
                    </Button>
                </div>
            </Card>

            {risultati && (
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                    {Object.entries(risultati.risultati).map(([tipo, r]) => (
                        <Card key={tipo} className="p-5 border-slate-200" data-testid={`pensione-result-${tipo}`}>
                            <div className="text-[11px] uppercase tracking-widest text-slate-500">{tipo}</div>
                            <div className="text-3xl font-semibold tracking-tight num text-slate-900 mt-1">
                                {fmtEur(r.pensione_lorda_mensile)}
                            </div>
                            <div className="text-xs text-slate-500 mt-0.5">al mese (lordo)</div>
                            <div className="mt-3 pt-3 border-t border-slate-100 space-y-1 text-xs">
                                <div className="flex justify-between"><span className="text-slate-500">Annuo lordo:</span><span className="num font-medium">{fmtEur(r.pensione_lorda_annua)}</span></div>
                                <div className="flex justify-between"><span className="text-slate-500">Netto stimato:</span><span className="num">{fmtEur(r.pensione_netta_stimata)}</span></div>
                                <div className="text-[10px] text-slate-400 mt-1">{r.metodologia}</div>
                            </div>
                            {/* GAP di reddito */}
                            <div className="mt-3 pt-3 border-t border-slate-100">
                                <div className="text-[10px] uppercase tracking-widest text-rose-600 mb-1">Gap reddito</div>
                                <div className="text-xl font-semibold num text-rose-700">
                                    -{fmtEur(risultati.gap_reddito[tipo].gap_annuo)} <span className="text-xs text-slate-500 font-normal">/anno</span>
                                </div>
                                <div className="text-[11px] text-slate-500 mt-1">
                                    Copertura attuale: <span className="num font-medium text-slate-700">{risultati.gap_reddito[tipo].copertura_percentuale}%</span>
                                </div>
                                <div className="text-[11px] text-slate-500">
                                    Da integrare: <span className="num font-medium text-rose-700">{fmtEur(risultati.gap_reddito[tipo].gap_mensile)}/mese</span>
                                </div>
                            </div>
                        </Card>
                    ))}
                </div>
            )}
        </div>
    );
}

function Field({ label, value, hint }) {
    return (
        <div>
            <div className="text-[11px] uppercase tracking-wider text-slate-500 mb-0.5">{label}</div>
            <div className="text-sm text-slate-900 font-medium num">{value || "—"}</div>
            {hint && <div className="text-[10px] text-slate-500 mt-0.5">{hint}</div>}
        </div>
    );
}


// ============== DOCUMENTI ANAGRAFICA (CI, patente, passaporto, CF, privacy) ==============
const DOC_TIPI_ANAG = [
    { key: "carta_identita", label: "Carta d'identità", icon: "🪪" },
    { key: "patente", label: "Patente di guida", icon: "🚗" },
    { key: "passaporto", label: "Passaporto", icon: "📘" },
    { key: "codice_fiscale_doc", label: "Tessera codice fiscale", icon: "🧾" },
    { key: "tessera_sanitaria", label: "Tessera sanitaria", icon: "❤️" },
    { key: "visura_camerale", label: "Visura camerale", icon: "🏢" },
    { key: "privacy_firmata", label: "Privacy firmata", icon: "✍️" },
];

function DocumentiTab({ anagrafica_id, ana, canEdit, onReload }) {
    const [docs, setDocs] = useState(ana?.documenti || {});
    const [busyTipo, setBusyTipo] = useState(null);
    const [privacyOpen, setPrivacyOpen] = useState(false);

    const upload = async (tipo, file, scadenza) => {
        if (!file) return;
        setBusyTipo(tipo);
        // Per CI/patente/passaporto, prima OCR + aggiornamento campi anagrafica, poi upload
        const isOcrable = ["carta_identita", "patente", "passaporto"].includes(tipo);
        try {
            if (isOcrable) {
                const fd = new FormData();
                fd.append("file", file);
                fd.append("anagrafica_id", anagrafica_id);
                fd.append("tipo", tipo);
                const r = await api.post("/utility/ocr-documento-identita", fd,
                    { headers: { "Content-Type": "multipart/form-data" }, timeout: 60000 });
                const d = r.data;
                // proponi aggiornamento campi su anagrafica
                const updates = {};
                if (d.codice_fiscale && !ana.codice_fiscale) updates.codice_fiscale = d.codice_fiscale;
                if (d.data_nascita && !ana.data_nascita) updates.data_nascita = d.data_nascita;
                if (d.numero_documento && tipo === "carta_identita") updates.numero_documento = d.numero_documento;
                if (d.data_scadenza && tipo === "carta_identita") updates.data_scadenza = d.data_scadenza;
                if (Object.keys(updates).length > 0 && window.confirm(
                    `OCR ha estratto:\n${Object.entries(updates).map(([k, v]) => `• ${k}: ${v}`).join("\n")}\n\nAggiornare l'anagrafica?`)) {
                    await api.put(`/anagrafiche/${anagrafica_id}`, updates);
                }
                setDocs((p) => ({ ...p, [tipo]: { url: d._documento_salvato, nome_file: file.name, data_caricamento: new Date().toISOString(), size_kb: Math.round(file.size / 1024) } }));
                toast.success(`${tipo.replace("_", " ")} riconosciuto e salvato`);
            } else {
                const fd = new FormData();
                fd.append("file", file);
                if (scadenza) fd.append("scadenza", scadenza);
                const r = await api.post(`/anagrafiche/${anagrafica_id}/documenti/${tipo}`, fd,
                    { headers: { "Content-Type": "multipart/form-data" } });
                setDocs((p) => ({ ...p, [tipo]: r.data[tipo] }));
                toast.success("Documento caricato");
            }
            onReload?.();
        } catch (e) {
            toast.error(e.response?.data?.detail || "Errore");
        } finally { setBusyTipo(null); }
    };

    const elimina = async (tipo) => {
        if (!window.confirm("Eliminare il documento?")) return;
        try {
            await api.delete(`/anagrafiche/${anagrafica_id}/documenti/${tipo}`);
            setDocs((p) => { const c = { ...p }; delete c[tipo]; return c; });
            toast.success("Eliminato");
            onReload?.();
        } catch (e) { toast.error("Errore"); }
    };

    const scaricaPrivacy = () => setPrivacyOpen(true);

    return (
        <div className="space-y-4 mt-4" data-testid="documenti-tab">
            <div className="bg-sky-50 border border-sky-200 rounded-md p-3 flex items-center justify-between flex-wrap gap-3">
                <div className="text-xs text-sky-900">
                    <strong>Documenti del cliente</strong>: CI, patente, passaporto, codice fiscale, privacy firmata.
                    Tutti i file sono protetti (solo staff può vederli).
                </div>
                <Button size="sm" variant="outline" onClick={scaricaPrivacy} data-testid="genera-privacy-btn">
                    <FileText size={13} className="mr-1" /> Privacy & Consensi
                </Button>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {DOC_TIPI_ANAG.map((dt) => {
                    const doc = docs?.[dt.key];
                    return (
                        <Card key={dt.key} className="p-3 border-slate-200">
                            <div className="flex items-center justify-between mb-2">
                                <div className="font-medium text-sm flex items-center gap-2">
                                    <span className="text-lg">{dt.icon}</span> {dt.label}
                                </div>
                                {doc && <span className="badge badge-success text-[10px]">caricato</span>}
                            </div>
                            {doc ? (
                                <div className="bg-slate-50 rounded-md p-2 text-xs space-y-1">
                                    <div>
                                        📎 <a href={doc.url} target="_blank" rel="noreferrer" className="text-sky-700 hover:underline">{doc.nome_file}</a>
                                    </div>
                                    <div className="text-slate-500">
                                        {doc.size_kb} KB · caricato {doc.data_caricamento?.slice(0, 10)}
                                        {doc.scadenza && <span className="ml-2 text-amber-700">scad. {doc.scadenza}</span>}
                                    </div>
                                    {canEdit && (
                                        <div className="flex gap-2 mt-2">
                                            <label className="cursor-pointer text-[11px] px-2 py-1 bg-sky-700 text-white rounded hover:bg-sky-800" data-testid={`doc-replace-${dt.key}`}>
                                                Sostituisci
                                                <input type="file" className="hidden" accept=".pdf,image/*"
                                                       onChange={(e) => upload(dt.key, e.target.files?.[0])} />
                                            </label>
                                            <button onClick={() => elimina(dt.key)} className="text-[11px] text-red-600 hover:underline" data-testid={`doc-delete-${dt.key}`}>
                                                Elimina
                                            </button>
                                        </div>
                                    )}
                                </div>
                            ) : canEdit ? (
                                <label className="cursor-pointer block border border-dashed border-slate-300 rounded-md p-3 text-center bg-slate-50 hover:bg-sky-50 hover:border-sky-300 transition" data-testid={`doc-upload-${dt.key}`}>
                                    <Upload size={14} className="mx-auto text-slate-400" />
                                    <div className="text-[11px] text-slate-500 mt-1">
                                        {busyTipo === dt.key ? "Caricamento..." : "Click per caricare (PDF/JPG/PNG)"}
                                    </div>
                                    <input type="file" className="hidden" accept=".pdf,image/*"
                                           onChange={(e) => upload(dt.key, e.target.files?.[0])} />
                                </label>
                            ) : (
                                <div className="text-xs text-slate-400 italic py-3 text-center">Nessun documento</div>
                            )}
                        </Card>
                    );
                })}
            </div>

            {ana?.firma_cliente_url && (
                <Card className="p-3 border-emerald-200 bg-emerald-50">
                    <div className="font-medium text-sm flex items-center gap-2 mb-2">
                        ✍️ Firma digitale del cliente
                    </div>
                    <img src={ana.firma_cliente_url} alt="firma" className="bg-white rounded-md border max-h-24" />
                </Card>
            )}

            <PrivacyConsensiDialog
                open={privacyOpen}
                onOpenChange={setPrivacyOpen}
                anagrafica_id={anagrafica_id}
                ana={ana}
                canEdit={canEdit}
                onReload={onReload}
            />
        </div>
    );
}
