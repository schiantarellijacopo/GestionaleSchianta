/**
 * DocumentiSezioneSplit — sezione documenti riutilizzabile con DUE riquadri:
 * "VISIBILI al cliente" e "INTERNI (non visibili al cliente)".
 * Funziona per qualsiasi entità (polizza, sinistro, anagrafica, titolo, libro-matricola).
 * Stile coerente con il pattern di DocumentiTab di AnagraficaDetail.
 */
import { useEffect, useState } from "react";
import { api, API_BASE } from "@/lib/api";
import { Card } from "@/components/ui/card";
import { Switch } from "@/components/ui/switch";
import { Eye, EyeOff, Upload, FileText, Trash2, Lock, Sparkles, PenTool, AlertTriangle } from "lucide-react";
import { toast } from "sonner";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export default function DocumentiSezioneSplit({
    entita_tipo,
    entita_id,
    applicazione_matricola_id = null,
    canEdit = true,
    titolo = "Documenti",
    sottotitolo = null,
    categorie = [],
    layout = "split",
}) {
    const [items, setItems] = useState(null);
    const [uploading, setUploading] = useState(null);
    const [firme, setFirme] = useState([]);
    const [visCfg, setVisCfg] = useState(null); // {cardKey: bool} per questa entità
    const [apiCards, setApiCards] = useState([]); // card dalla config (incluse custom)

    useEffect(() => {
        api.get("/config/card-visibilita")
            .then((r) => {
                const list = r.data?.[entita_tipo] || [];
                setApiCards(list);
                setVisCfg(Object.fromEntries(list.map((c) => [c.key, c.visibile_cliente])));
            })
            .catch(() => { setApiCards([]); setVisCfg({}); });
    }, [entita_tipo]);

    // Card effettive: l'ordine, l'icona e l'obbligatorietà sono guidati dalla
    // config (Librerie → Visibilità documenti). Da `categorie` (passate dal
    // dettaglio) recuperiamo descrizione/multiple per chiave.
    const hardByKey = Object.fromEntries(categorie.map((c) => [c.key, c]));
    const presentKeys = new Set(categorie.map((c) => c.key));
    const mergedCategorie = apiCards.length > 0
        ? apiCards.map((c) => {
            const h = hardByKey[c.key] || {};
            return {
                key: c.key, label: c.label || h.label,
                icon: c.icon || h.icon || "📄",
                descrizione: h.descrizione,
                multiple: h.multiple,
                default_visibile: c.default_visibile ?? h.default_visibile ?? false,
                obbligatoria: !!c.obbligatoria,
            };
        })
        : [
            ...categorie,
            ...apiCards
                .filter((c) => c.custom && !presentKeys.has(c.key))
                .map((c) => ({ key: c.key, label: c.label, icon: c.icon || "🗂️", default_visibile: c.default_visibile, obbligatoria: !!c.obbligatoria })),
        ];

    // visibilità di default per una card: config Librerie → altrimenti default della card
    const defVis = (c) => (visCfg && c.key in visCfg) ? visCfg[c.key] : (c.default_visibile ?? false);

    const loadFirme = async () => {
        try {
            const r = await api.get("/esignature/richieste", { params: { entita_tipo, entita_id } });
            setFirme(r.data?.items || []);
        } catch { setFirme([]); }
    };

    const load = async () => {
        try {
            const r = await api.get("/allegati", {
                params: { entita_tipo, entita_id },
            });
            let arr = r.data || [];
            if (applicazione_matricola_id) {
                arr = arr.filter((a) => a.applicazione_matricola_id === applicazione_matricola_id);
            }
            setItems(arr);
        } catch (e) {
            setItems([]);
        }
        loadFirme();
    };
    useEffect(() => { load(); /* eslint-disable-next-line */ }, [entita_tipo, entita_id, applicazione_matricola_id]);
    const firmeByOrig = Object.fromEntries(firme.map((f) => [f.allegato_origine_id, f]));
    const firmatiIds = new Set(firme.filter((f) => f.allegato_firmato_id).map((f) => f.allegato_firmato_id));

    const upload = async (fileOrList, { visibile, categoria }) => {
        const files = fileOrList && fileOrList.length !== undefined && !(fileOrList instanceof File)
            ? Array.from(fileOrList) : (fileOrList ? [fileOrList] : []);
        if (!files.length) return;
        setUploading(categoria || (visibile ? "visibile" : "interno"));
        try {
            for (const file of files) {
                const fd = new FormData(); fd.append("file", file);
                const params = new URLSearchParams({
                    entita_tipo, entita_id,
                    visibile_cliente: visibile ? "true" : "false",
                });
                if (categoria) params.set("categoria", categoria);
                if (applicazione_matricola_id) params.set("applicazione_matricola_id", applicazione_matricola_id);
                await api.post(`/allegati?${params.toString()}`, fd, {
                    headers: { "Content-Type": "multipart/form-data" },
                });
            }
            toast.success(`${files.length > 1 ? files.length + " documenti caricati" : "Documento caricato"}${visibile ? " (visibile al cliente)" : " (interno)"}`);
            await load();
        } catch (e) { toast.error(e.response?.data?.detail || "Errore upload"); }
        finally { setUploading(null); }
    };

    const ocrLibretto = async (file) => {
        if (!file) return;
        setUploading("libretto");
        try {
            const fd = new FormData(); fd.append("file", file);
            const r = await api.post(`/ocr/libretto?polizza_id=${entita_id}`, fd, {
                headers: { "Content-Type": "multipart/form-data" }, timeout: 120000,
            });
            const dati = r.data?.dati || {};
            const campi = Object.entries(dati).filter(([, v]) => v !== null && v !== "").map(([k]) => k);
            if (campi.length) {
                await api.post("/ocr/libretto/apply", { polizza_id: entita_id, dati, campi });
            }
            toast.success("Libretto analizzato: dati veicolo aggiornati e file archiviato");
            await load();
        } catch (e) { toast.error(e.response?.data?.detail || "Errore OCR libretto"); }
        finally { setUploading(null); }
    };

    const toggleVisibilita = async (alleg) => {
        const newVis = !alleg.visibile_cliente;
        try {
            await api.patch(`/allegati/${alleg.id}/visibilita`, { visibile_cliente: newVis });
            toast.success(newVis ? "Reso visibile al cliente" : "Nascosto al cliente");
            await load();
        } catch (e) { toast.error("Errore aggiornamento visibilità"); }
    };

    const elimina = async (id) => {
        if (!window.confirm("Eliminare questo documento?")) return;
        try { await api.delete(`/allegati/${id}`); toast.success("Eliminato"); await load(); }
        catch (e) { toast.error("Errore"); }
    };

    if (!items) return <div className="text-sm text-slate-400 py-4">Caricamento…</div>;

    // === Layout QUADROTTI: una card per categoria (come scheda Anagrafica) ===
    if (layout === "quadrotti" && mergedCategorie.length > 0) {
        const catKeys = mergedCategorie.map((c) => c.key);
        const hasAltri = catKeys.includes("altri");
        const gruppi = {};
        items.forEach((a) => {
            let key = a.categoria && catKeys.includes(a.categoria) ? a.categoria : (hasAltri ? "altri" : (catKeys[catKeys.length - 1] || "altri"));
            (gruppi[key] = gruppi[key] || []).push(a);
        });
        return (
            <div className="space-y-3 mt-2" data-testid="docs-quadrotti">
                <div className="bg-sky-50 border border-sky-200 rounded p-3 text-xs text-sky-900">
                    <strong>{titolo}</strong> — {sottotitolo || "Documenti organizzati per categoria. Ogni riquadro mostra i file e ne indica la visibilità al cliente."}
                </div>
                <RiepilogoMancanti categorie={mergedCategorie} gruppi={gruppi} />
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    {mergedCategorie.map((c) => (
                        <QuadrottoCategoria
                            key={c.key}
                            categoria={c}
                            files={gruppi[c.key] || []}
                            canEdit={canEdit}
                            uploading={uploading === c.key || (uploading === "libretto" && c.key.includes("libretto"))}
                            onUpload={(files) => upload(files, { visibile: defVis(c), categoria: c.key })}
                            onOcrLibretto={entita_tipo === "polizza" && c.key.includes("libretto") ? ocrLibretto : null}
                            onToggle={toggleVisibilita}
                            onDelete={elimina}
                            firmeByOrig={firmeByOrig}
                            firmatiIds={firmatiIds}
                            onFirmaChange={load}
                        />
                    ))}
                </div>
            </div>
        );
    }

    const visibili = items.filter((a) => a.visibile_cliente === true);
    const interni = items.filter((a) => a.visibile_cliente !== true);

    return (
        <div className="space-y-4 mt-2" data-testid="docs-split">
            <div className="bg-sky-50 border border-sky-200 rounded p-3 text-xs text-sky-900">
                <strong>{titolo}</strong> — {sottotitolo || "Organizzati in due aree: documenti visibili al cliente nel suo portale e documenti interni allo staff."}
            </div>

            {/* Categorie caricamento rapido (se previste) */}
            {canEdit && mergedCategorie.length > 0 && (
                <Card className="p-3">
                    <div className="text-[10px] uppercase tracking-wider text-slate-500 mb-2">
                        Carica documento per categoria
                    </div>
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                        {mergedCategorie.map((c) => (
                            <CategoriaUpload key={c.key} categoria={c}
                                onPick={(files) => upload(files, { visibile: defVis(c), categoria: c.key })}
                                busy={uploading === c.key} />
                        ))}
                    </div>
                </Card>
            )}

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
                {/* === VISIBILI === */}
                <DocBox
                    titolo="Visibili al cliente"
                    icona={Eye}
                    color="emerald"
                    items={visibili}
                    canEdit={canEdit}
                    onUpload={(f) => upload(f, { visibile: true })}
                    onToggle={toggleVisibilita}
                    onDelete={elimina}
                    uploading={uploading === "visibile"}
                    testid="docs-box-visibili"
                    firmeByOrig={firmeByOrig}
                    firmatiIds={firmatiIds}
                    onFirmaChange={load}
                />
                {/* === INTERNI === */}
                <DocBox
                    titolo="Interni · solo staff"
                    icona={EyeOff}
                    color="slate"
                    items={interni}
                    canEdit={canEdit}
                    onUpload={(f) => upload(f, { visibile: false })}
                    onToggle={toggleVisibilita}
                    onDelete={elimina}
                    uploading={uploading === "interno"}
                    testid="docs-box-interni"
                    firmeByOrig={firmeByOrig}
                    firmatiIds={firmatiIds}
                    onFirmaChange={load}
                />
            </div>
        </div>
    );
}

const COL = {
    emerald: { ring: "border-emerald-300", bg: "bg-emerald-50/30", header: "text-emerald-800 bg-emerald-50", ic: "text-emerald-600" },
    slate: { ring: "border-slate-300", bg: "bg-slate-50/30", header: "text-slate-800 bg-slate-100", ic: "text-slate-600" },
};

export function RiepilogoMancanti({ categorie, gruppi }) {
    const mancanti = categorie.filter((c) => c.obbligatoria && (gruppi[c.key] || []).length === 0);
    if (mancanti.length === 0) return null;
    return (
        <div className="rounded-md border-2 border-rose-300 bg-rose-50 p-3" data-testid="riepilogo-mancanti">
            <div className="flex items-center gap-2 text-sm font-semibold text-rose-800">
                <AlertTriangle size={15} />
                Documenti obbligatori mancanti
                <span className="ml-1 text-[11px] bg-rose-200 text-rose-800 px-2 py-0.5 rounded-full font-mono" data-testid="riepilogo-mancanti-count">{mancanti.length}</span>
            </div>
            <div className="mt-2 flex flex-wrap gap-1.5">
                {mancanti.map((c) => (
                    <span key={c.key} className="inline-flex items-center gap-1 text-xs bg-white border border-rose-200 text-rose-700 px-2 py-1 rounded-md"
                        data-testid={`riepilogo-mancante-${c.key}`}>
                        <span>{c.icon || "📄"}</span> {c.label}
                    </span>
                ))}
            </div>
        </div>
    );
}

function DocBox({ titolo, icona: Icon, color, items, canEdit, onUpload, onToggle, onDelete, uploading, testid, firmeByOrig = {}, firmatiIds = new Set(), onFirmaChange }) {
    const c = COL[color];
    return (
        <Card className={`overflow-hidden border-2 ${c.ring}`} data-testid={testid}>
            <div className={`px-3 py-2 border-b ${c.ring} ${c.header} flex items-center justify-between`}>
                <div className="flex items-center gap-2 font-semibold text-sm">
                    <Icon size={14} className={c.ic} /> {titolo}
                </div>
                <span className="text-[10px] bg-white/60 px-2 py-0.5 rounded-full font-mono">{items.length}</span>
            </div>
            <div className={`p-3 space-y-2 ${c.bg} min-h-[140px]`}>
                {items.length === 0 ? (
                    <div className="text-center text-xs text-slate-400 italic py-6">Nessun documento</div>
                ) : (
                    items.map((a) => (
                        <div key={a.id} className="flex items-center gap-2 p-2 bg-white rounded border border-slate-200 hover:border-sky-300 group">
                            <FileText size={14} className="text-sky-600 shrink-0" />
                            <div className="flex-1 min-w-0">
                                <a href={`${API_BASE}/allegati/${a.id}/download`} target="_blank" rel="noreferrer"
                                    className="text-sm font-medium text-sky-700 hover:underline truncate block" data-testid={`doc-link-${a.id}`}>
                                    {a.nome_file}
                                </a>
                                <div className="text-[10px] text-slate-500 flex items-center gap-1.5 flex-wrap">
                                    {a.categoria && <span className="bg-sky-100 text-sky-700 px-1 rounded">{a.categoria}</span>}
                                    {a.descrizione && <span className="italic truncate">{a.descrizione}</span>}
                                    <span>· {(a.size / 1024).toFixed(0)} KB</span>
                                    {a.created_at && <span>· {a.created_at.slice(0, 10)}</span>}
                                    <FirmaBadge rec={firmeByOrig[a.id]} isFirmato={firmatiIds.has(a.id)} />
                                </div>
                            </div>
                            {canEdit && (
                                <div className="flex items-center gap-1.5">
                                    <FirmaButton allegato={a} stato={firmeByOrig[a.id]?.stato} onDone={onFirmaChange} />
                                    <label className="flex items-center gap-1 text-[10px] text-slate-500 cursor-pointer" title="Toggle visibilità">
                                        <Switch checked={!!a.visibile_cliente} onCheckedChange={() => onToggle(a)}
                                            className="scale-75" data-testid={`doc-visibile-${a.id}`} />
                                    </label>
                                    <button onClick={() => onDelete(a.id)} className="text-rose-500 hover:bg-rose-50 p-1 rounded opacity-0 group-hover:opacity-100"
                                        data-testid={`doc-del-${a.id}`}>
                                        <Trash2 size={11} />
                                    </button>
                                </div>
                            )}
                        </div>
                    ))
                )}
                {canEdit && (
                    <label className={`block w-full p-3 text-center border-2 border-dashed ${c.ring} rounded cursor-pointer hover:bg-white text-xs ${c.ic}`}
                        data-testid={`docs-upload-${color === "emerald" ? "visibile" : "interno"}`}>
                        <Upload size={13} className="inline mr-1" />
                        {uploading ? "Caricamento…" : "Carica documento qui"}
                        <input type="file" multiple hidden onChange={(e) => onUpload(e.target.files)} />
                    </label>
                )}
            </div>
        </Card>
    );
}

function QuadrottoCategoria({ categoria, files, canEdit, uploading, onUpload, onOcrLibretto, onToggle, onDelete, firmeByOrig = {}, firmatiIds = new Set(), onFirmaChange }) {
    const [open, setOpen] = useState(true);
    const c = categoria;
    const manca = !!c.obbligatoria && files.length === 0;
    return (
        <Card className={`p-0 overflow-hidden ${manca ? "border-2 border-rose-400" : "border-slate-200"}`} data-testid={`quadrotto-${c.key}`}>
            <button type="button" onClick={() => setOpen((o) => !o)}
                className={`w-full flex items-center gap-2 px-3 py-2.5 transition-colors text-left ${manca ? "bg-rose-50 hover:bg-rose-100" : "bg-slate-50 hover:bg-slate-100"}`}
                data-testid={`quadrotto-toggle-${c.key}`}>
                <span className="text-lg">{c.icon || "📄"}</span>
                <span className={`font-medium text-sm flex-1 ${manca ? "text-rose-800" : "text-slate-800"}`}>{c.label}</span>
                {c.obbligatoria && (
                    <span className="inline-flex items-center gap-0.5 text-rose-600 shrink-0" title="Documento obbligatorio">
                        <AlertTriangle size={12} />
                    </span>
                )}
                {c.default_visibile ? <Eye size={12} className="text-emerald-600" title="Di default visibile al cliente" />
                    : <Lock size={12} className="text-slate-400" title="Di default interno" />}
                <span className={`text-[11px] px-2 py-0.5 rounded-full ${manca ? "bg-rose-200 text-rose-700" : "bg-slate-200 text-slate-600"}`}>{files.length}</span>
                <span className={`text-slate-400 transition-transform ${open ? "rotate-180" : ""}`}>▾</span>
            </button>
            {manca && (
                <div className="px-3 py-1.5 bg-rose-50 border-b border-rose-200 text-[11px] text-rose-700 font-medium flex items-center gap-1" data-testid={`quadrotto-manca-${c.key}`}>
                    <AlertTriangle size={11} /> Documento obbligatorio mancante
                </div>
            )}
            {open && (
                <div className="p-2.5 space-y-2">
                    {c.descrizione && <div className="text-[10px] text-slate-400 -mt-0.5 mb-1">{c.descrizione}</div>}
                    {files.length === 0 ? (
                        <div className="text-center text-xs text-slate-400 italic py-3">Nessun documento</div>
                    ) : files.map((a) => (
                        <div key={a.id} className="flex items-center gap-2 p-2 bg-white rounded border border-slate-200 hover:border-sky-300 group">
                            <FileText size={14} className="text-sky-600 shrink-0" />
                            <div className="flex-1 min-w-0">
                                <a href={`${API_BASE}/allegati/${a.id}/download`} target="_blank" rel="noreferrer"
                                    className="text-sm font-medium text-sky-700 hover:underline truncate block" data-testid={`doc-link-${a.id}`}>
                                    {a.nome_file}
                                </a>
                                <div className="text-[10px] text-slate-500 flex items-center gap-1.5 flex-wrap">
                                    {a.visibile_cliente
                                        ? <span className="bg-emerald-100 text-emerald-700 px-1 rounded">visibile cliente</span>
                                        : <span className="bg-slate-100 text-slate-500 px-1 rounded">interno</span>}
                                    <span>· {(a.size / 1024).toFixed(0)} KB</span>
                                    {a.created_at && <span>· {a.created_at.slice(0, 10)}</span>}
                                    <FirmaBadge rec={firmeByOrig[a.id]} isFirmato={firmatiIds.has(a.id)} />
                                </div>
                            </div>
                            {canEdit && (
                                <div className="flex items-center gap-1.5">
                                    <FirmaButton allegato={a} stato={firmeByOrig[a.id]?.stato} onDone={onFirmaChange} />
                                    <Switch checked={!!a.visibile_cliente} onCheckedChange={() => onToggle(a)}
                                        className="scale-75" data-testid={`doc-visibile-${a.id}`} />
                                    <button onClick={() => onDelete(a.id)} className="text-rose-500 hover:bg-rose-50 p-1 rounded opacity-0 group-hover:opacity-100"
                                        data-testid={`doc-del-${a.id}`}>
                                        <Trash2 size={11} />
                                    </button>
                                </div>
                            )}
                        </div>
                    ))}
                    {canEdit && (
                        <label className="block w-full p-2.5 text-center border-2 border-dashed border-slate-300 rounded cursor-pointer hover:bg-sky-50 hover:border-sky-300 text-xs text-slate-500 transition"
                            data-testid={`quadrotto-upload-${c.key}`}>
                            <Upload size={13} className="inline mr-1" />
                            {uploading ? "Caricamento…" : "Carica documento"}
                            <input type="file" multiple={c.multiple !== false} hidden onChange={(e) => onUpload(e.target.files)} />
                        </label>
                    )}
                    {canEdit && onOcrLibretto && (
                        <label className="block w-full p-2.5 text-center border-2 border-dashed border-violet-300 bg-violet-50 rounded cursor-pointer hover:bg-violet-100 text-xs text-violet-700 font-medium transition"
                            data-testid={`quadrotto-ocr-${c.key}`} title="Carica il libretto: l'AI estrae targa, telaio, marca, modello… e li applica alla polizza">
                            <Sparkles size={13} className="inline mr-1" />
                            {uploading ? "Analisi OCR in corso…" : "Carica + OCR libretto (estrai dati veicolo)"}
                            <input type="file" accept=".pdf,.jpg,.jpeg,.png,.heic,.webp" hidden
                                onChange={(e) => e.target.files?.[0] && onOcrLibretto(e.target.files[0])} />
                        </label>
                    )}
                </div>
            )}
        </Card>
    );
}

function CategoriaUpload({ categoria, onPick, busy }) {
    return (
        <label className="border border-dashed border-violet-300 bg-violet-50 hover:bg-violet-100 rounded p-2 text-center cursor-pointer transition"
            title={categoria.descrizione || categoria.label}>
            <div className="flex flex-col items-center gap-1">
                <span className="text-base">{categoria.icon || "📄"}</span>
                <span className="text-[11px] font-medium text-violet-800">{categoria.label}</span>
                {categoria.default_visibile && <Sparkles size={10} className="text-emerald-600" />}
                {categoria.default_visibile === false && <Lock size={10} className="text-slate-500" />}
            </div>
            <span className="text-[9px] text-violet-600 block mt-0.5">{busy ? "Caricamento…" : "Click per caricare"}</span>
            <input type="file" multiple={categoria.multiple !== false} hidden onChange={(e) => onPick(e.target.files)} />
        </label>
    );
}


function isPdf(a) {
    return (a.content_type || "").toLowerCase().includes("pdf") || (a.nome_file || "").toLowerCase().endsWith(".pdf");
}

const STATO_FIRMA = {
    DONE: { label: "Firmato", cls: "bg-emerald-100 text-emerald-700" },
    ERROR: { label: "Errore firma", cls: "bg-rose-100 text-rose-700" },
};
function FirmaBadge({ rec, isFirmato }) {
    if (isFirmato) return <span className="bg-emerald-600 text-white px-1.5 rounded font-medium">✓ Documento firmato</span>;
    if (!rec) return null;
    const s = STATO_FIRMA[(rec.stato || "").toUpperCase()] || { label: "In attesa firma", cls: "bg-amber-100 text-amber-700" };
    return <span className={`px-1.5 rounded font-medium ${s.cls}`} data-testid={`firma-badge-${rec.allegato_origine_id}`}>{s.label}</span>;
}

export function FirmaButton({ allegato, stato, onDone }) {
    const [open, setOpen] = useState(false);
    const [sending, setSending] = useState(false);
    const [signer, setSigner] = useState({ name: "", surname: "", email: "", mobile: "" });
    const [req, setReq] = useState(null);
    const [checking, setChecking] = useState(false);
    const [canali, setCanali] = useState({ wa: true, email: true });
    const [firmatario, setFirmatario] = useState(null);
    const giaFirmato = (stato || "").toUpperCase() === "DONE";

    useEffect(() => {
        if (!open || !allegato.entita_tipo || !allegato.entita_id) return;
        api.get("/esignature/firmatario", { params: { entita_tipo: allegato.entita_tipo, entita_id: allegato.entita_id } })
            .then((r) => setFirmatario(r.data)).catch(() => setFirmatario(null));
    }, [open, allegato.entita_tipo, allegato.entita_id]);

    // Validità effettiva considerando eventuali dati inseriti manualmente
    const emailOk = /.+@.+\..+/.test(signer.email) || (firmatario?.email_ok && !signer.email);
    const mobileOk = (signer.mobile.replace(/\D/g, "").length >= 8) || (firmatario?.mobile_ok && !signer.mobile);
    const bloccato = !!firmatario && (!emailOk || !mobileOk);

    if (!isPdf(allegato)) return null;

    const invia = async () => {
        setSending(true);
        try {
            const payload = { allegato_id: allegato.id, invia_whatsapp: canali.wa, invia_email: canali.email };
            if (signer.mobile || signer.email || signer.name || signer.surname) payload.firmatario = signer;
            const r = await api.post("/esignature/invia", payload);
            setReq(r.data);
            toast.success("Richiesta di firma inviata (link via WhatsApp/Email)");
            if (onDone) onDone();
        } catch (e) {
            toast.error(e.response?.data?.detail || "Errore invio firma");
        } finally {
            setSending(false);
        }
    };

    const controlla = async () => {
        if (!req?.id) return;
        setChecking(true);
        try {
            const r = await api.get(`/esignature/stato/${req.id}`);
            if (r.data.allegato_firmato_id) {
                toast.success("Documento firmato ricevuto e salvato in questa sezione!");
                setOpen(false);
                if (onDone) onDone(); else setTimeout(() => window.location.reload(), 800);
            } else {
                toast(`Stato firma: ${r.data.stato}`);
            }
        } catch (e) {
            toast.error(e.response?.data?.detail || "Errore verifica stato");
        } finally {
            setChecking(false);
        }
    };

    return (
        <>
            {!giaFirmato && (
                <button onClick={() => setOpen(true)} title="Invia per firma (FEA · OTP SMS)"
                    className="text-violet-600 hover:bg-violet-50 p-1 rounded" data-testid={`doc-firma-${allegato.id}`}>
                    <PenTool size={12} />
                </button>
            )}
            <Dialog open={open} onOpenChange={setOpen}>
                <DialogContent className="max-w-md" data-testid="firma-dialog">
                    <DialogHeader>
                        <DialogTitle className="flex items-center gap-2"><PenTool size={16} className="text-violet-600" /> Invia per firma</DialogTitle>
                    </DialogHeader>
                    <div className="space-y-3 text-sm">
                        <div className="text-xs text-slate-500 bg-slate-50 rounded p-2">
                            Documento: <b>{allegato.nome_file}</b><br />
                            Firma Elettronica Avanzata con OTP via SMS. Il firmatario riceve il link via WhatsApp ed email.
                        </div>
                        <div className="text-[11px] text-slate-500">Dati firmatario (lascia vuoto per usare il contraente):</div>
                        {bloccato && (
                            <div className="text-xs bg-rose-50 border border-rose-200 text-rose-700 rounded p-2" data-testid="firma-avviso-contatti">
                                ⚠️ Il contraente non ha {(!emailOk && !mobileOk) ? "email e cellulare validi" : (!emailOk ? "un'email valida" : "un cellulare valido")}.
                                La firma FES richiede <b>entrambi</b>: compila i campi sotto oppure aggiorna l'anagrafica.
                            </div>
                        )}
                        <div className="grid grid-cols-2 gap-2">
                            <div><Label className="text-xs">Nome</Label><Input value={signer.name} onChange={(e) => setSigner({ ...signer, name: e.target.value })} data-testid="firma-nome" /></div>
                            <div><Label className="text-xs">Cognome</Label><Input value={signer.surname} onChange={(e) => setSigner({ ...signer, surname: e.target.value })} data-testid="firma-cognome" /></div>
                            <div><Label className="text-xs">Email</Label><Input value={signer.email} onChange={(e) => setSigner({ ...signer, email: e.target.value })} data-testid="firma-email" /></div>
                            <div><Label className="text-xs">Cellulare</Label><Input value={signer.mobile} onChange={(e) => setSigner({ ...signer, mobile: e.target.value })} placeholder="+39…" data-testid="firma-cellulare" /></div>
                        </div>
                        <div>
                            <div className="text-[11px] text-slate-500 mb-1">Invia il link di firma via:</div>
                            <div className="flex gap-2">
                                <button type="button" onClick={() => setCanali((c) => ({ ...c, wa: !c.wa }))} data-testid="firma-canale-wa"
                                    className={`text-xs px-2 py-1 rounded border ${canali.wa ? "bg-emerald-600 text-white border-emerald-600" : "bg-white border-slate-200 text-slate-500"}`}>🟢 WhatsApp</button>
                                <button type="button" onClick={() => setCanali((c) => ({ ...c, email: !c.email }))} data-testid="firma-canale-email"
                                    className={`text-xs px-2 py-1 rounded border ${canali.email ? "bg-sky-600 text-white border-sky-600" : "bg-white border-slate-200 text-slate-500"}`}>✉️ Email</button>
                            </div>
                        </div>
                        {req && (
                            <div className="text-xs bg-emerald-50 border border-emerald-200 rounded p-2 space-y-1">
                                <div>✅ Inviata. Stato: <b>{req.stato}</b></div>
                                {req.signing_url && <a href={req.signing_url} target="_blank" rel="noreferrer" className="text-sky-700 underline break-all">Apri link di firma</a>}
                            </div>
                        )}
                    </div>
                    <DialogFooter>
                        {!req ? (
                            <Button onClick={invia} disabled={sending || bloccato} className="bg-violet-600 hover:bg-violet-700" data-testid="firma-invia-btn">
                                {sending ? "Invio…" : "Invia richiesta firma"}
                            </Button>
                        ) : (
                            <Button onClick={controlla} disabled={checking} variant="outline" data-testid="firma-controlla-btn">
                                {checking ? "Controllo…" : "Controlla stato / scarica firmato"}
                            </Button>
                        )}
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </>
    );
}
