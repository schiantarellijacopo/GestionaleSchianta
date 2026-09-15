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
import { Eye, EyeOff, Upload, FileText, Trash2, Lock, Sparkles } from "lucide-react";
import { toast } from "sonner";

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
    };
    useEffect(() => { load(); /* eslint-disable-next-line */ }, [entita_tipo, entita_id, applicazione_matricola_id]);

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
    if (layout === "quadrotti" && categorie.length > 0) {
        const catKeys = categorie.map((c) => c.key);
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
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    {categorie.map((c) => (
                        <QuadrottoCategoria
                            key={c.key}
                            categoria={c}
                            files={gruppi[c.key] || []}
                            canEdit={canEdit}
                            uploading={uploading === c.key}
                            onUpload={(files) => upload(files, { visibile: c.default_visibile ?? false, categoria: c.key })}
                            onToggle={toggleVisibilita}
                            onDelete={elimina}
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
            {canEdit && categorie.length > 0 && (
                <Card className="p-3">
                    <div className="text-[10px] uppercase tracking-wider text-slate-500 mb-2">
                        Carica documento per categoria
                    </div>
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                        {categorie.map((c) => (
                            <CategoriaUpload key={c.key} categoria={c}
                                onPick={(files) => upload(files, { visibile: c.default_visibile ?? false, categoria: c.key })}
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
                />
            </div>
        </div>
    );
}

const COL = {
    emerald: { ring: "border-emerald-300", bg: "bg-emerald-50/30", header: "text-emerald-800 bg-emerald-50", ic: "text-emerald-600" },
    slate: { ring: "border-slate-300", bg: "bg-slate-50/30", header: "text-slate-800 bg-slate-100", ic: "text-slate-600" },
};

function DocBox({ titolo, icona: Icon, color, items, canEdit, onUpload, onToggle, onDelete, uploading, testid }) {
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
                                </div>
                            </div>
                            {canEdit && (
                                <div className="flex items-center gap-1.5">
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

function QuadrottoCategoria({ categoria, files, canEdit, uploading, onUpload, onToggle, onDelete }) {
    const [open, setOpen] = useState(true);
    const c = categoria;
    return (
        <Card className="p-0 overflow-hidden border-slate-200" data-testid={`quadrotto-${c.key}`}>
            <button type="button" onClick={() => setOpen((o) => !o)}
                className="w-full flex items-center gap-2 px-3 py-2.5 bg-slate-50 hover:bg-slate-100 transition-colors text-left"
                data-testid={`quadrotto-toggle-${c.key}`}>
                <span className="text-lg">{c.icon || "📄"}</span>
                <span className="font-medium text-sm text-slate-800 flex-1">{c.label}</span>
                {c.default_visibile ? <Eye size={12} className="text-emerald-600" title="Di default visibile al cliente" />
                    : <Lock size={12} className="text-slate-400" title="Di default interno" />}
                <span className="text-[11px] px-2 py-0.5 rounded-full bg-slate-200 text-slate-600">{files.length}</span>
                <span className={`text-slate-400 transition-transform ${open ? "rotate-180" : ""}`}>▾</span>
            </button>
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
                                </div>
                            </div>
                            {canEdit && (
                                <div className="flex items-center gap-1.5">
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
