import { useEffect, useState, useRef, useMemo, useCallback } from "react";
import { Link } from "react-router-dom";
import { api, fmtDate } from "@/lib/api";
import { PageHeader, Empty, Loading } from "@/components/Shared";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
    Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger, DialogFooter,
} from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Plus, Search, ScanLine, Calculator, MapPin, X } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { toast } from "sonner";

// Colori per categoria
const CAT_BADGE = {
    con_polizze: { dot: "bg-sky-500", label: "Con polizze", text: "text-sky-700" },
    senza_polizze: { dot: "bg-red-500", label: "Senza polizze", text: "text-red-700" },
    condominio: { dot: "bg-emerald-500", label: "Condominio", text: "text-emerald-700" },
};

export default function Anagrafiche() {
    const { user } = useAuth();
    const [list, setList] = useState(null);
    const [q, setQ] = useState("");
    const [open, setOpen] = useState(false);
    const [tagFilter, setTagFilter] = useState(null);
    const [catFilter, setCatFilter] = useState("all");
    const canCreate = ["admin", "collaboratore", "dipendente"].includes(user?.role);

    const load = useCallback(() => {
        api.get("/anagrafiche", { params: { q: q || undefined, tag: tagFilter || undefined } })
            .then((r) => setList(r.data));
    }, [q, tagFilter]);

    useEffect(() => { load(); }, [load]);

    // Tag univoci per chip filtri
    const tagsUnivoci = useMemo(() => {
        if (!list) return [];
        const all = new Set();
        list.forEach((a) => (a.tags || []).forEach((t) => all.add(t)));
        return Array.from(all).sort();
    }, [list]);

    const filtered = useMemo(() => {
        if (!list) return [];
        if (catFilter === "all") return list;
        return list.filter((a) => a.categoria_ui === catFilter);
    }, [list, catFilter]);

    const counts = useMemo(() => {
        if (!list) return { con: 0, senza: 0, cond: 0 };
        return {
            con: list.filter((a) => a.categoria_ui === "con_polizze").length,
            senza: list.filter((a) => a.categoria_ui === "senza_polizze").length,
            cond: list.filter((a) => a.categoria_ui === "condominio").length,
        };
    }, [list]);

    return (
        <div data-testid="anagrafiche-page">
            <PageHeader
                title="Anagrafiche clienti"
                subtitle="Persone fisiche e giuridiche presenti a portafoglio"
                actions={
                    canCreate && (
                        <Dialog open={open} onOpenChange={setOpen}>
                            <DialogTrigger asChild>
                                <Button data-testid="anagrafica-new-button" className="bg-sky-700 hover:bg-sky-800">
                                    <Plus size={16} className="mr-1" /> Nuova anagrafica
                                </Button>
                            </DialogTrigger>
                            <NuovaAnagraficaDialog onClose={() => { setOpen(false); load(); }} />
                        </Dialog>
                    )
                }
            />

            <div className="flex items-center gap-2 mb-3">
                <div className="relative flex-1 max-w-md">
                    <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
                    <Input
                        data-testid="anagrafiche-search"
                        placeholder="Cerca per nome, codice fiscale, email..."
                        value={q}
                        onChange={(e) => setQ(e.target.value)}
                        className="pl-9"
                    />
                </div>
                <span className="text-sm text-slate-500 num">
                    {list ? `${filtered.length} risultati` : ""}
                </span>
            </div>

            {/* Chips filtri categoria */}
            <div className="flex flex-wrap items-center gap-2 mb-3">
                <CatChip active={catFilter === "all"} onClick={() => setCatFilter("all")} dot="bg-slate-300" label={`Tutte (${list?.length || 0})`} />
                <CatChip active={catFilter === "con_polizze"} onClick={() => setCatFilter("con_polizze")} dot="bg-sky-500" label={`Con polizze (${counts.con})`} />
                <CatChip active={catFilter === "senza_polizze"} onClick={() => setCatFilter("senza_polizze")} dot="bg-red-500" label={`Senza polizze (${counts.senza})`} />
                <CatChip active={catFilter === "condominio"} onClick={() => setCatFilter("condominio")} dot="bg-emerald-500" label={`Condomini (${counts.cond})`} />
                {tagFilter && (
                    <button onClick={() => setTagFilter(null)} className="inline-flex items-center gap-1 text-xs px-2 py-1 rounded-full bg-amber-100 text-amber-800 hover:bg-amber-200" data-testid="anag-tag-active">
                        Tag: {tagFilter} <X size={10} />
                    </button>
                )}
            </div>

            {/* Chips tag univoci */}
            {tagsUnivoci.length > 0 && (
                <div className="flex flex-wrap items-center gap-1.5 mb-3">
                    <span className="text-xs text-slate-500 mr-1">Tag:</span>
                    {tagsUnivoci.slice(0, 30).map((t) => (
                        <button
                            key={t}
                            onClick={() => setTagFilter(tagFilter === t ? null : t)}
                            data-testid={`anag-tag-chip-${t}`}
                            className={`text-[10px] uppercase tracking-wide px-2 py-0.5 rounded-full border ${
                                tagFilter === t
                                    ? "bg-sky-600 text-white border-sky-600"
                                    : "bg-white text-slate-600 border-slate-300 hover:bg-slate-100"
                            }`}
                        >
                            {t}
                        </button>
                    ))}
                </div>
            )}

            <div className="bg-white border border-slate-200 rounded-md overflow-hidden">
                {list === null ? <Loading /> : filtered.length === 0 ? <Empty /> : (
                    <table className="tbl w-full">
                        <thead>
                            <tr>
                                <th className="w-[10px]"></th>
                                <th>Ragione sociale</th>
                                <th>CF / P.IVA</th>
                                <th>Polizze</th>
                                <th>Comune</th>
                                <th>Email</th>
                                <th>Telefono</th>
                                <th>Operatore</th>
                                <th>Tag</th>
                            </tr>
                        </thead>
                        <tbody>
                            {filtered.map((a) => {
                                const cat = CAT_BADGE[a.categoria_ui] || CAT_BADGE.senza_polizze;
                                return (
                                    <tr key={a.id} data-testid={`anagrafica-row-${a.id}`}>
                                        <td>
                                            <span title={cat.label} className={`inline-block w-2 h-2 rounded-full ${cat.dot}`} />
                                        </td>
                                        <td>
                                            <Link to={`/anagrafiche/${a.id}`} className={`hover:underline font-medium ${cat.text}`}>
                                                {a.ragione_sociale}
                                            </Link>
                                            {a.tipo === "persona_giuridica" && <span className="ml-1 text-[9px] text-slate-400">PG</span>}
                                        </td>
                                        <td className="num font-mono text-xs">{a.codice_fiscale || a.partita_iva || "-"}</td>
                                        <td className="num text-center">
                                            {a.polizze_attive_count > 0
                                                ? <span className="badge badge-info">{a.polizze_attive_count}</span>
                                                : <span className="text-slate-300">—</span>}
                                        </td>
                                        <td>{a.comune || "-"}{a.provincia ? ` (${a.provincia})` : ""}</td>
                                        <td className="text-xs">{a.email || "-"}</td>
                                        <td className="text-xs">{a.cellulare || a.telefono || "-"}</td>
                                        <td className="text-xs">{a.collaboratore_nome || <span className="text-slate-300">—</span>}</td>
                                        <td>
                                            <div className="flex flex-wrap gap-1">
                                                {(a.tags || []).slice(0, 3).map((t) => (
                                                    <button
                                                        key={t}
                                                        onClick={() => setTagFilter(t)}
                                                        className="text-[9px] uppercase px-1.5 py-0.5 rounded bg-slate-100 text-slate-600 hover:bg-sky-100 hover:text-sky-700"
                                                    >
                                                        {t}
                                                    </button>
                                                ))}
                                                {(a.tags || []).length > 3 && <span className="text-[9px] text-slate-400">+{a.tags.length - 3}</span>}
                                            </div>
                                        </td>
                                    </tr>
                                );
                            })}
                        </tbody>
                    </table>
                )}
            </div>
        </div>
    );
}

function CatChip({ active, onClick, dot, label }) {
    return (
        <button
            onClick={onClick}
            className={`inline-flex items-center gap-2 text-xs px-3 py-1 rounded-full border transition ${
                active ? "bg-slate-900 text-white border-slate-900" : "bg-white text-slate-600 border-slate-300 hover:bg-slate-50"
            }`}
        >
            <span className={`w-2 h-2 rounded-full ${dot}`} />
            {label}
        </button>
    );
}

// ============================================================
// DIALOG NUOVA ANAGRAFICA con OCR CI + Calcolo CF + Geocoding auto
// ============================================================
function NuovaAnagraficaDialog({ onClose }) {
    const ciFileRef = useRef(null);
    const [collaboratori, setCollaboratori] = useState([]);
    const [ocrLoading, setOcrLoading] = useState(false);
    const [geoLoading, setGeoLoading] = useState(false);
    const [form, setForm] = useState({
        tipo: "persona_fisica",
        ragione_sociale: "", nome: "", cognome: "",
        codice_fiscale: "", partita_iva: "",
        data_nascita: "", sesso: "",
        comune_nascita: "", provincia_nascita: "",
        email: "", cellulare: "", telefono: "",
        indirizzo: "", comune: "", provincia: "", cap: "",
        numero_documento: "", data_rilascio: "", data_scadenza: "",
        comune_emissione: "",
        collaboratore_id: "",
        lat: null, lng: null,
    });

    useEffect(() => { api.get("/collaboratori").then((r) => setCollaboratori(r.data)); }, []);

    const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));
    const setU = (k, v) => set(k, (v || "").toUpperCase());

    // --- Calcolo CF ---
    const calcolaCF = async () => {
        if (!form.nome || !form.cognome || !form.sesso || !form.data_nascita || !form.comune_nascita) {
            toast.error("Servono Nome, Cognome, Sesso, Data nascita, Comune nascita");
            return;
        }
        try {
            const r = await api.post("/utility/codice-fiscale/calcola", {
                nome: form.nome, cognome: form.cognome, sesso: form.sesso,
                data_nascita: form.data_nascita, comune_nascita: form.comune_nascita,
            });
            set("codice_fiscale", r.data.codice_fiscale);
            toast.success("CF calcolato: " + r.data.codice_fiscale);
        } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
    };

    // --- Decodifica CF (compila campi anagrafici) ---
    const decodificaCF = async () => {
        if (!form.codice_fiscale || form.codice_fiscale.length !== 16) {
            toast.error("Inserisci un CF valido (16 caratteri)");
            return;
        }
        try {
            const r = await api.post("/utility/codice-fiscale/decodifica", {
                codice_fiscale: form.codice_fiscale,
            });
            setForm((f) => ({
                ...f,
                sesso: r.data.sesso || f.sesso,
                data_nascita: r.data.data_nascita || f.data_nascita,
                comune_nascita: (r.data.comune_nascita || f.comune_nascita || "").toUpperCase(),
                provincia_nascita: r.data.provincia_nascita || f.provincia_nascita,
            }));
            toast.success("Dati estratti dal CF");
        } catch (e) { toast.error(e.response?.data?.detail || "CF non valido"); }
    };

    // --- OCR Carta Identità ---
    const onOcrCI = async (file) => {
        if (!file) return;
        setOcrLoading(true);
        const fd = new FormData();
        fd.append("file", file);
        try {
            const r = await api.post("/utility/ocr-carta-identita", fd,
                { headers: { "Content-Type": "multipart/form-data" }, timeout: 60000 });
            const d = r.data;
            setForm((p) => ({
                ...p,
                tipo: "persona_fisica",
                cognome: (d.cognome || p.cognome || "").toUpperCase(),
                nome: (d.nome || p.nome || "").toUpperCase(),
                sesso: d.sesso || p.sesso,
                data_nascita: d.data_nascita || p.data_nascita,
                comune_nascita: (d.comune_nascita || p.comune_nascita || "").toUpperCase(),
                provincia_nascita: d.provincia_nascita || p.provincia_nascita,
                codice_fiscale: (d.codice_fiscale || p.codice_fiscale || "").toUpperCase(),
                numero_documento: (d.numero_documento || p.numero_documento || "").toUpperCase(),
                data_rilascio: d.data_rilascio || p.data_rilascio,
                data_scadenza: d.data_scadenza || p.data_scadenza,
                comune_emissione: (d.comune_emissione || p.comune_emissione || "").toUpperCase(),
                indirizzo: (d.indirizzo_residenza || p.indirizzo || "").toUpperCase(),
                comune: (d.comune_residenza || p.comune || "").toUpperCase(),
                _ci_file_da_salvare: file,  // verrà ricaricato dopo create anagrafica per salvare in documenti
            }));
            toast.success("Carta d'identità riconosciuta — verifica i campi");
        } catch (e) { toast.error("OCR fallito: " + (e.response?.data?.detail || e.message)); }
        finally { setOcrLoading(false); }
    };

    // --- OCR Visura camerale ---
    const onOcrVisura = async (file) => {
        if (!file) return;
        setOcrLoading(true);
        const fd = new FormData();
        fd.append("file", file);
        try {
            const r = await api.post("/utility/ocr-visura-camerale", fd,
                { headers: { "Content-Type": "multipart/form-data" }, timeout: 90000 });
            const d = r.data;
            setForm((p) => ({
                ...p,
                tipo: "persona_giuridica",
                ragione_sociale: (d.ragione_sociale || p.ragione_sociale || "").toUpperCase(),
                partita_iva: d.partita_iva || p.partita_iva,
                codice_fiscale: (d.codice_fiscale_ditta || p.codice_fiscale || "").toUpperCase(),
                indirizzo: (d.indirizzo_sede || p.indirizzo || "").toUpperCase(),
                comune: (d.comune_sede || p.comune || "").toUpperCase(),
                provincia: d.provincia_sede || p.provincia,
                cap: d.cap_sede || p.cap,
                telefono: d.telefono || p.telefono,
                email: d.email || p.email,
                _visura_file_da_salvare: file,
                _amministratori: d.amministratori || [],
                _dati_extra_visura: {
                    forma_giuridica: d.forma_giuridica, rea: d.rea,
                    capitale_sociale: d.capitale_sociale, pec: d.pec,
                    oggetto_sociale: d.oggetto_sociale, codice_ateco: d.codice_ateco,
                    stato_attivita: d.stato_attivita, data_inizio_attivita: d.data_inizio_attivita,
                    data_costituzione: d.data_costituzione,
                },
            }));
            const nAmm = (d.amministratori || []).length;
            toast.success(`Visura riconosciuta: ${d.ragione_sociale}${nAmm ? ` + ${nAmm} amministratori` : ""}`);
        } catch (e) { toast.error("OCR visura fallito: " + (e.response?.data?.detail || e.message)); }
        finally { setOcrLoading(false); }
    };

    // --- Geocoding automatico al blur dell'indirizzo o comune ---
    const geocoda = async () => {
        if (!form.indirizzo && !form.comune) return;
        setGeoLoading(true);
        try {
            const r = await api.post("/utility/geocoding", {
                indirizzo: form.indirizzo, comune: form.comune, cap: form.cap, provincia: form.provincia,
            });
            if (r.data?.trovato) {
                setForm((f) => ({ ...f, lat: r.data.lat, lng: r.data.lng }));
                toast.success(`Geo: ${r.data.lat.toFixed(4)}, ${r.data.lng.toFixed(4)}`);
            }
        } catch (e) { console.warn("geocoding:", e?.message || e); }
        finally { setGeoLoading(false); }
    };

    const save = async () => {
        const isPF = form.tipo === "persona_fisica";
        if (isPF && !form.nome && !form.cognome) { toast.error("Inserisci Cognome o Nome"); return; }
        if (!isPF && !form.ragione_sociale) { toast.error("Inserisci la ragione sociale"); return; }
        const { _ci_file_da_salvare, _visura_file_da_salvare, _amministratori, _dati_extra_visura, ...payload } = form;
        if (isPF && !payload.ragione_sociale) {
            payload.ragione_sociale = `${form.cognome || ""} ${form.nome || ""}`.trim();
        }
        // attacca note dalla visura (forma giuridica, REA, capitale, oggetto sociale)
        if (_dati_extra_visura) {
            const extra = Object.entries(_dati_extra_visura).filter(([, v]) => v).map(([k, v]) => `${k}: ${v}`).join(" · ");
            if (extra) payload.note = (payload.note ? payload.note + "\n" : "") + `[Da visura] ${extra}`;
        }
        try {
            const created = await api.post("/anagrafiche", payload);
            const newId = created.data.id;
            // Salva la CI come documento, se caricata
            if (_ci_file_da_salvare) {
                const fd = new FormData();
                fd.append("file", _ci_file_da_salvare);
                api.post(`/anagrafiche/${newId}/documenti/carta_identita`, fd,
                    { headers: { "Content-Type": "multipart/form-data" } }).catch(() => {});
            }
            // Salva visura come documento
            if (_visura_file_da_salvare) {
                const fd = new FormData();
                fd.append("file", _visura_file_da_salvare);
                api.post(`/anagrafiche/${newId}/documenti/visura_camerale`, fd,
                    { headers: { "Content-Type": "multipart/form-data" } }).catch(() => {});
            }
            // Crea anagrafiche per amministratori
            if (_amministratori?.length) {
                for (const a of _amministratori) {
                    if (!a.cognome && !a.nome) continue;
                    const amm = {
                        tipo: "persona_fisica",
                        ragione_sociale: `${a.cognome || ""} ${a.nome || ""}`.trim(),
                        cognome: (a.cognome || "").toUpperCase(),
                        nome: (a.nome || "").toUpperCase(),
                        codice_fiscale: (a.codice_fiscale || "").toUpperCase(),
                        data_nascita: a.data_nascita,
                        comune_nascita: (a.comune_nascita || "").toUpperCase(),
                        provincia_nascita: a.provincia_nascita,
                        indirizzo: (a.indirizzo_residenza || "").toUpperCase(),
                        comune: (a.comune_residenza || "").toUpperCase(),
                        note: `Ruolo nella ditta ${payload.ragione_sociale}: ${a.ruolo || "amministratore"}`
                              + (a.poteri ? ` - ${a.poteri}` : ""),
                        tags: ["amministratore", "da_visura"],
                    };
                    try { await api.post("/anagrafiche", amm); } catch (err) { /* skip */ }
                }
                toast.success(`Ditta + ${_amministratori.length} amministratori creati`);
            } else {
                toast.success("Anagrafica creata");
            }
            onClose();
        } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
    };

    const isPF = form.tipo === "persona_fisica";

    return (
        <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto">
            <DialogHeader>
                <DialogTitle>Nuova anagrafica</DialogTitle>
            </DialogHeader>

            {/* Toolbar OCR */}
            <div className="bg-sky-50 border border-sky-200 rounded-md p-3 flex items-center gap-3 flex-wrap" data-testid="ocr-toolbar">
                <div className="text-xs text-sky-900 flex-1">
                    <strong>Auto-compila</strong> caricando {isPF ? "la carta d'identità" : "la visura camerale"} (PDF/JPG/PNG).
                    {!isPF && " Verranno create anche le anagrafiche degli amministratori."}
                </div>
                <input
                    ref={ciFileRef}
                    type="file"
                    accept=".pdf,image/*"
                    className="hidden"
                    onChange={(e) => {
                        const f = e.target.files?.[0];
                        if (isPF) onOcrCI(f); else onOcrVisura(f);
                    }}
                    data-testid="anag-ocr-input"
                />
                <Button
                    type="button" variant="outline" size="sm"
                    onClick={() => ciFileRef.current?.click()}
                    disabled={ocrLoading}
                    data-testid="anag-ocr-button"
                >
                    <ScanLine size={13} className="mr-1" />
                    {ocrLoading ? "Riconosco..." : (isPF ? "Carica CI" : "Carica visura camerale")}
                </Button>
            </div>

            <div className="grid grid-cols-2 gap-3 py-2">
                <div className="col-span-2">
                    <Label>Tipo *</Label>
                    <Select value={form.tipo} onValueChange={(v) => set("tipo", v)}>
                        <SelectTrigger data-testid="anag-tipo-select"><SelectValue /></SelectTrigger>
                        <SelectContent>
                            <SelectItem value="persona_fisica">Persona fisica</SelectItem>
                            <SelectItem value="persona_giuridica">Azienda / Persona giuridica</SelectItem>
                        </SelectContent>
                    </Select>
                </div>

                {isPF ? (
                    <>
                        <div>
                            <Label>Cognome *</Label>
                            <Input data-testid="anag-cognome-input" className="uc"
                                value={form.cognome} onChange={(e) => setU("cognome", e.target.value)} />
                        </div>
                        <div>
                            <Label>Nome *</Label>
                            <Input data-testid="anag-nome-input" className="uc"
                                value={form.nome} onChange={(e) => setU("nome", e.target.value)} />
                        </div>
                    </>
                ) : (
                    <div className="col-span-2">
                        <Label>Ragione sociale *</Label>
                        <Input data-testid="anag-rs-input" className="uc"
                            value={form.ragione_sociale} onChange={(e) => setU("ragione_sociale", e.target.value)} />
                    </div>
                )}

                {isPF && (
                    <>
                        <div className="col-span-2 flex items-end gap-2">
                            <div className="flex-1">
                                <Label>Codice fiscale</Label>
                                <Input data-testid="anag-cf-input" className="uc"
                                    value={form.codice_fiscale} maxLength={16}
                                    onChange={(e) => setU("codice_fiscale", e.target.value)} />
                            </div>
                            <Button type="button" size="sm" variant="outline" onClick={calcolaCF} title="Calcola CF da dati anagrafici" data-testid="anag-cf-calcola">
                                <Calculator size={13} className="mr-1" /> Calcola
                            </Button>
                            <Button type="button" size="sm" variant="outline" onClick={decodificaCF} title="Estrai dati dal CF" data-testid="anag-cf-decodifica">
                                ← Compila da CF
                            </Button>
                        </div>
                        <div>
                            <Label>Data nascita</Label>
                            <Input type="date" value={form.data_nascita} onChange={(e) => set("data_nascita", e.target.value)} />
                        </div>
                        <div>
                            <Label>Sesso</Label>
                            <Select value={form.sesso || undefined} onValueChange={(v) => set("sesso", v)}>
                                <SelectTrigger><SelectValue placeholder="-" /></SelectTrigger>
                                <SelectContent>
                                    <SelectItem value="M">Maschio</SelectItem>
                                    <SelectItem value="F">Femmina</SelectItem>
                                </SelectContent>
                            </Select>
                        </div>
                        <div>
                            <Label>Comune di nascita</Label>
                            <Input className="uc" value={form.comune_nascita} onChange={(e) => setU("comune_nascita", e.target.value)} />
                        </div>
                        <div>
                            <Label>Provincia nascita</Label>
                            <Input className="uc" maxLength={2} value={form.provincia_nascita} onChange={(e) => setU("provincia_nascita", e.target.value)} />
                        </div>
                    </>
                )}

                {!isPF && (
                    <div className="col-span-2">
                        <Label>Partita IVA</Label>
                        <Input value={form.partita_iva} onChange={(e) => set("partita_iva", e.target.value)} />
                    </div>
                )}

                <div className="col-span-2 text-xs uppercase tracking-widest font-semibold text-slate-500 pt-3 border-t border-slate-100">Documento</div>
                {isPF && (
                    <>
                        <div><Label>Numero documento</Label><Input className="uc" value={form.numero_documento} onChange={(e) => setU("numero_documento", e.target.value)} /></div>
                        <div><Label>Comune emissione</Label><Input className="uc" value={form.comune_emissione} onChange={(e) => setU("comune_emissione", e.target.value)} /></div>
                        <div><Label>Data rilascio</Label><Input type="date" value={form.data_rilascio || ""} onChange={(e) => set("data_rilascio", e.target.value)} /></div>
                        <div><Label>Data scadenza</Label><Input type="date" value={form.data_scadenza || ""} onChange={(e) => set("data_scadenza", e.target.value)} /></div>
                    </>
                )}

                <div className="col-span-2 text-xs uppercase tracking-widest font-semibold text-slate-500 pt-3 border-t border-slate-100">Contatti</div>
                <div>
                    <Label>Email</Label>
                    <Input type="email" data-testid="anag-email-input"
                        value={form.email} onChange={(e) => set("email", e.target.value.toLowerCase())} />
                </div>
                <div><Label>Cellulare</Label><Input value={form.cellulare} onChange={(e) => set("cellulare", e.target.value)} /></div>
                <div><Label>Telefono</Label><Input value={form.telefono} onChange={(e) => set("telefono", e.target.value)} /></div>

                <div className="col-span-2 text-xs uppercase tracking-widest font-semibold text-slate-500 pt-3 border-t border-slate-100 flex items-center gap-2">
                    Residenza
                    {form.lat && form.lng && (
                        <span className="text-emerald-600 normal-case flex items-center gap-1 text-[10px] font-medium" data-testid="anag-geo-ok">
                            <MapPin size={11} /> {form.lat.toFixed(4)}, {form.lng.toFixed(4)}
                        </span>
                    )}
                </div>
                <div className="col-span-2">
                    <Label>Indirizzo</Label>
                    <Input className="uc" value={form.indirizzo} onBlur={geocoda}
                        onChange={(e) => setU("indirizzo", e.target.value)} />
                </div>
                <div>
                    <Label>Comune</Label>
                    <Input className="uc" value={form.comune} onBlur={geocoda}
                        onChange={(e) => setU("comune", e.target.value)} />
                </div>
                <div>
                    <Label>Provincia</Label>
                    <Input className="uc" maxLength={2} value={form.provincia}
                        onChange={(e) => setU("provincia", e.target.value)} />
                </div>
                <div>
                    <Label>CAP</Label>
                    <Input value={form.cap} onChange={(e) => set("cap", e.target.value)} onBlur={geocoda} />
                </div>

                <div className="col-span-2 text-xs uppercase tracking-widest font-semibold text-slate-500 pt-3 border-t border-slate-100">Operatore assegnato</div>
                <div className="col-span-2">
                    <Label>Collaboratore / Sub-agente</Label>
                    <Select value={form.collaboratore_id || "__none__"} onValueChange={(v) => set("collaboratore_id", v === "__none__" ? "" : v)}>
                        <SelectTrigger data-testid="anag-collab-select"><SelectValue /></SelectTrigger>
                        <SelectContent>
                            <SelectItem value="__none__">— nessuno —</SelectItem>
                            {collaboratori.map((c) => <SelectItem key={c.id} value={c.id}>{c.name} ({c.role})</SelectItem>)}
                        </SelectContent>
                    </Select>
                </div>
            </div>

            <DialogFooter>
                {geoLoading && <span className="text-xs text-slate-500 mr-auto">Geolocalizzo...</span>}
                <Button data-testid="anag-save-button" onClick={save} className="bg-sky-700 hover:bg-sky-800">Salva</Button>
            </DialogFooter>
        </DialogContent>
    );
}
