import { useEffect, useState, useCallback } from "react";
import { api } from "@/lib/api";
import { openPdf } from "@/lib/pdf";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Plus, Trash2, Pencil, FileDown, Printer, ClipboardList } from "lucide-react";
import { toast } from "sonner";

const TIPI = [
    { value: "testo", label: "Testo libero" },
    { value: "si_no", label: "Sì / No" },
    { value: "scelta_multipla", label: "Scelta multipla" },
    { value: "numero", label: "Numero" },
    { value: "data", label: "Data" },
];
const TIPO_LABEL = Object.fromEntries(TIPI.map((t) => [t.value, t.label]));

const rispostaFmt = (d) => {
    if (d.tipo === "si_no") {
        const v = String(d.risposta || "").toLowerCase();
        if (["si", "sì", "true", "1", "yes"].includes(v)) return "SÌ";
        if (["no", "false", "0"].includes(v)) return "NO";
        return "—";
    }
    return d.risposta == null || String(d.risposta).trim() === "" ? "—" : String(d.risposta);
};

// ── Stampa diretta: apre una finestra con l'HTML del questionario ──
function stampaQuestionario(q) {
    const righe = (q.domande || []).map((d, i) => `
        <div style="margin:14px 0;">
            <div style="font-weight:600;font-size:13px;">${i + 1}. ${escapeHtml(d.testo)}</div>
            ${d.tipo === "scelta_multipla" && (d.opzioni || []).length
            ? `<div style="font-size:10px;color:#94a3b8;">Opzioni: ${(d.opzioni || []).map(escapeHtml).join(", ")}</div>` : ""}
            <div style="font-size:13px;margin-left:12px;color:#0f172a;">Risposta: ${escapeHtml(rispostaFmt(d))}</div>
        </div>`).join("");
    const html = `<!doctype html><html><head><meta charset="utf-8"><title>${escapeHtml(q.titolo || "Questionario")}</title>
        <style>body{font-family:Arial,Helvetica,sans-serif;color:#0f172a;padding:32px;max-width:720px;margin:auto;}
        h1{font-size:20px;margin:0 0 4px;} .sub{color:#64748b;font-size:12px;margin-bottom:16px;}</style></head>
        <body><h1>${escapeHtml(q.titolo || "Questionario")}</h1>
        ${q.descrizione ? `<div class="sub">${escapeHtml(q.descrizione)}</div>` : ""}
        ${righe || '<div class="sub">Nessuna domanda inserita.</div>'}
        <script>window.onload=function(){window.print();}</script></body></html>`;
    const w = window.open("", "_blank");
    if (!w) { toast.error("Abilita i popup per stampare"); return; }
    w.document.write(html);
    w.document.close();
}

function escapeHtml(s) {
    return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

// ============================================================
// VIEWER — compilabile per-entità (Anagrafica / Polizza / Sinistri)
// Le risposte vengono salvate per QUEL record specifico.
// ============================================================
export function QuestionariViewer({ entita, entitaId }) {
    const [items, setItems] = useState([]);
    const [loading, setLoading] = useState(true);
    const [answers, setAnswers] = useState({}); // {questionarioId: {domandaId: valore}}
    const [saving, setSaving] = useState(null);

    const load = useCallback(() => {
        if (!entitaId) { setLoading(false); return; }
        setLoading(true);
        api.get(`/questionari/compilati?entita_tipo=${entita}&entita_id=${entitaId}`)
            .then((r) => {
                const list = r.data || [];
                setItems(list);
                const init = {};
                list.forEach((q) => {
                    init[q.id] = {};
                    (q.domande || []).forEach((d) => { init[q.id][d.id] = d.risposta ?? ""; });
                });
                setAnswers(init);
            })
            .catch(() => setItems([]))
            .finally(() => setLoading(false));
    }, [entita, entitaId]);
    useEffect(() => { load(); }, [load]);

    const setAns = (qid, did, v) => setAnswers((p) => ({ ...p, [qid]: { ...(p[qid] || {}), [did]: v } }));

    const salva = async (q) => {
        setSaving(q.id);
        try {
            await api.post("/questionari/compilati", {
                questionario_id: q.id, entita_tipo: entita, entita_id: entitaId,
                risposte: answers[q.id] || {},
            });
            toast.success("Risposte salvate");
            load();
        } catch (e) { toast.error(e.response?.data?.detail || "Errore salvataggio"); }
        finally { setSaving(null); }
    };

    if (loading) return <p className="text-sm text-slate-400 py-3">Caricamento questionari…</p>;
    if (!items.length) return <p className="text-sm text-slate-400 py-3">Nessun questionario disponibile per questa sezione. Creane uno in Librerie → Questionari.</p>;

    const pdfParams = `?entita_tipo=${entita}&entita_id=${entitaId}`;

    return (
        <div className="space-y-4" data-testid="questionari-viewer">
            {items.map((q) => (
                <div key={q.id} className="border border-slate-200 rounded-lg p-4 bg-white" data-testid={`questionario-view-${q.id}`}>
                    <div className="flex items-start justify-between gap-3 mb-3">
                        <div>
                            <div className="font-semibold text-slate-800 flex items-center gap-2">
                                <ClipboardList size={15} className="text-sky-600" /> {q.titolo}
                                {q.compilato && <span className="px-1.5 py-0.5 rounded bg-emerald-100 text-emerald-800 text-[10px] font-semibold">Compilato</span>}
                            </div>
                            {q.descrizione && <div className="text-xs text-slate-500 mt-0.5">{q.descrizione}</div>}
                        </div>
                        <div className="flex gap-1.5 shrink-0">
                            <Button size="sm" variant="outline" className="h-8" onClick={() => openPdf(`/questionari/${q.id}/pdf${pdfParams}`)} data-testid={`questionario-pdf-${q.id}`}>
                                <FileDown size={13} className="mr-1" /> PDF
                            </Button>
                            <Button size="sm" variant="outline" className="h-8" onClick={() => stampaQuestionario({ ...q, domande: (q.domande || []).map((d) => ({ ...d, risposta: (answers[q.id] || {})[d.id] ?? d.risposta })) })} data-testid={`questionario-print-${q.id}`}>
                                <Printer size={13} className="mr-1" /> Stampa
                            </Button>
                        </div>
                    </div>
                    <div className="space-y-2.5">
                        {(q.domande || []).map((d, i) => (
                            <div key={d.id || i} className="flex gap-2 items-center" data-testid={`questionario-field-${q.id}-${i}`}>
                                <span className="text-slate-500 text-sm w-5 shrink-0">{i + 1}.</span>
                                <span className="flex-1 text-sm text-slate-700">
                                    {d.testo}
                                    {d.tipo === "scelta_multipla" && (d.opzioni || []).length
                                        ? <span className="text-[10px] text-slate-400 ml-1">({(d.opzioni || []).join(", ")})</span> : null}
                                </span>
                                <div className="w-56">
                                    <RispostaInput d={{ ...d, risposta: (answers[q.id] || {})[d.id] ?? "" }}
                                        onChange={(v) => setAns(q.id, d.id, v)} />
                                </div>
                            </div>
                        ))}
                        {!(q.domande || []).length && <p className="text-sm text-slate-400">Questionario senza domande.</p>}
                    </div>
                    <div className="flex justify-end mt-3">
                        <Button size="sm" onClick={() => salva(q)} disabled={saving === q.id} className="bg-sky-700 hover:bg-sky-800" data-testid={`questionario-salva-risposte-${q.id}`}>
                            {saving === q.id ? "Salvataggio…" : "Salva risposte"}
                        </Button>
                    </div>
                </div>
            ))}
        </div>
    );
}

// ============================================================
// MANAGER — builder completo, usato in Librerie
// ============================================================
export function QuestionariManager() {
    const [items, setItems] = useState([]);
    const [loading, setLoading] = useState(true);
    const [editing, setEditing] = useState(null); // questionario o {} per nuovo
    const load = useCallback(() => {
        setLoading(true);
        api.get("/questionari").then((r) => setItems(r.data || [])).finally(() => setLoading(false));
    }, []);
    useEffect(() => { load(); }, [load]);

    const del = async (q) => {
        if (!window.confirm(`Eliminare il questionario "${q.titolo}"?`)) return;
        try { await api.delete(`/questionari/${q.id}`); toast.success("Eliminato"); load(); }
        catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
    };

    return (
        <div className="space-y-4">
            <div className="flex items-center justify-between">
                <p className="text-sm text-slate-500">
                    Crea questionari con domande e risposte, poi rendili visibili in Anagrafica, Polizza o Sinistri. Esportabili in PDF e stampabili.
                </p>
                <Button onClick={() => setEditing({})} className="bg-sky-700 hover:bg-sky-800" data-testid="questionario-nuovo">
                    <Plus size={15} className="mr-1" /> Nuovo questionario
                </Button>
            </div>

            {loading ? <p className="text-sm text-slate-400 py-6 text-center">Caricamento…</p>
                : !items.length ? <p className="text-sm text-slate-400 py-6 text-center">Nessun questionario. Creane uno con "Nuovo questionario".</p>
                : (
                    <div className="grid gap-3">
                        {items.map((q) => (
                            <div key={q.id} className="border border-slate-200 rounded-lg p-4 bg-white flex items-start justify-between gap-3" data-testid={`questionario-card-${q.id}`}>
                                <div className="min-w-0">
                                    <div className="font-semibold text-slate-800 flex items-center gap-2">
                                        <ClipboardList size={15} className="text-sky-600" /> {q.titolo}
                                    </div>
                                    {q.descrizione && <div className="text-xs text-slate-500 mt-0.5">{q.descrizione}</div>}
                                    <div className="text-[11px] text-slate-500 mt-1">{(q.domande || []).length} domande</div>
                                    <div className="flex gap-1.5 mt-2 flex-wrap">
                                        {q.visibile_anagrafica && <span className="px-1.5 py-0.5 rounded bg-emerald-100 text-emerald-800 text-[10px] font-semibold">Anagrafica</span>}
                                        {q.visibile_polizza && <span className="px-1.5 py-0.5 rounded bg-sky-100 text-sky-800 text-[10px] font-semibold">Polizza</span>}
                                        {q.visibile_sinistri && <span className="px-1.5 py-0.5 rounded bg-amber-100 text-amber-800 text-[10px] font-semibold">Sinistri</span>}
                                        {!q.visibile_anagrafica && !q.visibile_polizza && !q.visibile_sinistri && <span className="text-[10px] text-slate-400">Non visibile in nessuna sezione</span>}
                                    </div>
                                </div>
                                <div className="flex gap-1.5 shrink-0">
                                    <Button size="sm" variant="outline" className="h-8" onClick={() => openPdf(`/questionari/${q.id}/pdf`)} data-testid={`questionario-pdf-${q.id}`}><FileDown size={13} /></Button>
                                    <Button size="sm" variant="outline" className="h-8" onClick={() => stampaQuestionario(q)}><Printer size={13} /></Button>
                                    <Button size="sm" variant="outline" className="h-8" onClick={() => setEditing(q)} data-testid={`questionario-edit-${q.id}`}><Pencil size={13} /></Button>
                                    <Button size="sm" variant="outline" className="h-8 text-rose-600" onClick={() => del(q)} data-testid={`questionario-del-${q.id}`}><Trash2 size={13} /></Button>
                                </div>
                            </div>
                        ))}
                    </div>
                )}

            {editing !== null && (
                <QuestionarioBuilder editing={editing} onClose={() => setEditing(null)} onSaved={() => { setEditing(null); load(); }} />
            )}
        </div>
    );
}

function QuestionarioBuilder({ editing, onClose, onSaved }) {
    const isEdit = !!editing?.id;
    const [f, setF] = useState({
        titolo: editing?.titolo || "",
        descrizione: editing?.descrizione || "",
        visibile_anagrafica: !!editing?.visibile_anagrafica,
        visibile_polizza: !!editing?.visibile_polizza,
        visibile_sinistri: !!editing?.visibile_sinistri,
        domande: (editing?.domande || []).map((d) => ({ ...d })),
    });
    const [saving, setSaving] = useState(false);
    const set = (k, v) => setF((p) => ({ ...p, [k]: v }));
    const setDom = (i, k, v) => setF((p) => ({ ...p, domande: p.domande.map((d, j) => (j === i ? { ...d, [k]: v } : d)) }));
    const addDom = () => setF((p) => ({ ...p, domande: [...p.domande, { testo: "", tipo: "testo", opzioni: [], risposta: "" }] }));
    const delDom = (i) => setF((p) => ({ ...p, domande: p.domande.filter((_, j) => j !== i) }));

    const save = async () => {
        if (!f.titolo.trim()) { toast.error("Inserisci un titolo"); return; }
        setSaving(true);
        try {
            if (isEdit) await api.put(`/questionari/${editing.id}`, f);
            else await api.post("/questionari", f);
            toast.success(isEdit ? "Questionario aggiornato" : "Questionario creato");
            onSaved();
        } catch (e) { toast.error(e.response?.data?.detail || "Errore salvataggio"); }
        finally { setSaving(false); }
    };

    return (
        <Dialog open onOpenChange={(o) => { if (!o) onClose(); }}>
            <DialogContent className="max-w-2xl">
                <DialogHeader><DialogTitle>{isEdit ? "Modifica" : "Nuovo"} questionario</DialogTitle></DialogHeader>
                <div className="space-y-4 py-2 max-h-[70vh] overflow-y-auto">
                    <div>
                        <Label>Titolo *</Label>
                        <Input value={f.titolo} onChange={(e) => set("titolo", e.target.value)} data-testid="questionario-titolo" />
                    </div>
                    <div>
                        <Label>Descrizione</Label>
                        <Textarea value={f.descrizione} onChange={(e) => set("descrizione", e.target.value)} rows={2} />
                    </div>
                    <div className="bg-slate-50 border border-slate-200 rounded-md p-3">
                        <Label className="text-xs font-semibold text-slate-600">Rendi visibile in:</Label>
                        <div className="flex gap-4 mt-2 flex-wrap">
                            {[["visibile_anagrafica", "Anagrafica"], ["visibile_polizza", "Polizza"], ["visibile_sinistri", "Sinistri"]].map(([k, lbl]) => (
                                <label key={k} className="flex items-center gap-2 text-sm cursor-pointer">
                                    <input type="checkbox" checked={f[k]} onChange={(e) => set(k, e.target.checked)} data-testid={`questionario-${k}`} />
                                    {lbl}
                                </label>
                            ))}
                        </div>
                    </div>

                    <div>
                        <div className="flex items-center justify-between mb-2">
                            <Label className="font-semibold">Domande</Label>
                            <Button size="sm" variant="outline" onClick={addDom} data-testid="questionario-add-domanda"><Plus size={13} className="mr-1" /> Aggiungi domanda</Button>
                        </div>
                        <div className="space-y-3">
                            {f.domande.map((d, i) => (
                                <div key={i} className="border border-slate-200 rounded-md p-3 space-y-2" data-testid={`questionario-domanda-${i}`}>
                                    <div className="flex gap-2 items-start">
                                        <span className="text-slate-400 text-sm mt-2">{i + 1}.</span>
                                        <Input className="flex-1" placeholder="Testo della domanda" value={d.testo} onChange={(e) => setDom(i, "testo", e.target.value)} />
                                        <Button size="sm" variant="outline" className="text-rose-600" onClick={() => delDom(i)}><Trash2 size={13} /></Button>
                                    </div>
                                    <div className="flex gap-2 pl-6">
                                        <div className="w-44">
                                            <Select value={d.tipo} onValueChange={(v) => setDom(i, "tipo", v)}>
                                                <SelectTrigger className="h-8 text-xs"><SelectValue /></SelectTrigger>
                                                <SelectContent>
                                                    {TIPI.map((t) => <SelectItem key={t.value} value={t.value}>{t.label}</SelectItem>)}
                                                </SelectContent>
                                            </Select>
                                        </div>
                                        <div className="flex-1">
                                            <RispostaInput d={d} onChange={(v) => setDom(i, "risposta", v)} />
                                        </div>
                                    </div>
                                    {d.tipo === "scelta_multipla" && (
                                        <div className="pl-6">
                                            <Input className="h-8 text-xs" placeholder="Opzioni separate da virgola (es. Lieve, Grave)"
                                                value={(d.opzioni || []).join(", ")}
                                                onChange={(e) => setDom(i, "opzioni", e.target.value.split(",").map((x) => x.trim()).filter(Boolean))} />
                                        </div>
                                    )}
                                </div>
                            ))}
                            {!f.domande.length && <p className="text-sm text-slate-400 text-center py-3">Nessuna domanda. Aggiungine una.</p>}
                        </div>
                    </div>
                </div>
                <DialogFooter>
                    <Button variant="outline" onClick={onClose}>Annulla</Button>
                    <Button onClick={save} disabled={saving} className="bg-sky-700 hover:bg-sky-800" data-testid="questionario-salva">
                        {saving ? "Salvataggio…" : "Salva"}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}

function RispostaInput({ d, onChange }) {
    if (d.tipo === "si_no") {
        return (
            <Select value={String(d.risposta || "")} onValueChange={onChange}>
                <SelectTrigger className="h-8 text-xs"><SelectValue placeholder="Risposta…" /></SelectTrigger>
                <SelectContent>
                    <SelectItem value="si">SÌ</SelectItem>
                    <SelectItem value="no">NO</SelectItem>
                </SelectContent>
            </Select>
        );
    }
    if (d.tipo === "scelta_multipla") {
        return (
            <Select value={String(d.risposta || "")} onValueChange={onChange}>
                <SelectTrigger className="h-8 text-xs"><SelectValue placeholder="Scegli…" /></SelectTrigger>
                <SelectContent>
                    {(d.opzioni || []).filter(Boolean).map((o) => <SelectItem key={o} value={o}>{o}</SelectItem>)}
                </SelectContent>
            </Select>
        );
    }
    const type = d.tipo === "numero" ? "number" : d.tipo === "data" ? "date" : "text";
    return <Input className="h-8 text-xs" type={type} placeholder="Risposta" value={d.risposta || ""} onChange={(e) => onChange(e.target.value)} />;
}
