/**
 * DocumentiAnnualiCollab — vista "documenti annuali per collaboratore".
 * Admin: panoramica immediata di tutti i collaboratori con stato per anno e
 * upload diretto. Collaboratore/dipendente: vede e carica SOLO i propri.
 * Checklist configurabile (casellario, carichi pendenti, attestato IVASS, ecc.).
 */
import { useEffect, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { api, imgUrl } from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { PageHeader, Loading, Empty } from "@/components/Shared";
import {
    FolderCheck, Upload, Trash2, Plus, Settings2, ChevronDown, ChevronRight,
    FileText, ExternalLink, GraduationCap, Search, Check, AlertTriangle,
} from "lucide-react";
import { toast } from "sonner";

const STATI = {
    presente: { label: "Presente", cls: "bg-emerald-100 text-emerald-700 border-emerald-200" },
    in_scadenza: { label: "In scadenza", cls: "bg-amber-100 text-amber-800 border-amber-200" },
    scaduto: { label: "Scaduto", cls: "bg-rose-100 text-rose-700 border-rose-300" },
    mancante: { label: "Mancante", cls: "bg-rose-50 text-rose-600 border-rose-200" },
    parziale: { label: "Parziale", cls: "bg-amber-100 text-amber-800 border-amber-200" },
    assente: { label: "Facoltativo", cls: "bg-slate-100 text-slate-500 border-slate-200" },
};

function StatoBadge({ item }) {
    const s = STATI[item.stato] || STATI.assente;
    let txt = s.label;
    if (item.is_ivass) txt = `${s.label} · ${item.ore_ivass || 0}/${item.obiettivo || 30}h`;
    return (
        <Badge variant="outline" className={`${s.cls} text-[10px] font-semibold`} data-testid={`stato-${item.key}`}>
            {txt}
        </Badge>
    );
}

/* Dialog di upload per un singolo documento richiesto */
function UploadDialog({ open, onOpenChange, item, onUpload }) {
    const [file, setFile] = useState(null);
    const [dataRilascio, setDataRilascio] = useState("");
    const [dataScadenza, setDataScadenza] = useState("");
    const [busy, setBusy] = useState(false);

    useEffect(() => {
        if (!open) { setFile(null); setDataRilascio(""); setDataScadenza(""); setBusy(false); }
    }, [open]);

    const submit = async () => {
        if (!file) { toast.error("Seleziona un file"); return; }
        setBusy(true);
        try {
            await onUpload({ file, data_rilascio: dataRilascio, data_scadenza: dataScadenza });
            onOpenChange(false);
        } catch (e) {
            toast.error(e.response?.data?.detail || "Errore durante il caricamento");
        } finally { setBusy(false); }
    };

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="max-w-md">
                <DialogHeader><DialogTitle>Carica · {item?.label}</DialogTitle></DialogHeader>
                <div className="space-y-3 py-1">
                    <div>
                        <Label className="text-xs">File (PDF o immagine) *</Label>
                        <Input type="file" accept="application/pdf,image/*"
                            onChange={(e) => setFile(e.target.files?.[0] || null)}
                            data-testid="upload-file-input" />
                    </div>
                    <div className="grid grid-cols-2 gap-3">
                        <div>
                            <Label className="text-xs">Data rilascio</Label>
                            <Input type="date" value={dataRilascio} onChange={(e) => setDataRilascio(e.target.value)} data-testid="upload-data-rilascio" />
                        </div>
                        <div>
                            <Label className="text-xs">Scadenza</Label>
                            <Input type="date" value={dataScadenza} onChange={(e) => setDataScadenza(e.target.value)} data-testid="upload-data-scadenza" />
                        </div>
                    </div>
                    <p className="text-[11px] text-slate-500">La scadenza permette l'avviso automatico "In scadenza".</p>
                </div>
                <DialogFooter>
                    <Button onClick={submit} disabled={busy} className="bg-emerald-700 hover:bg-emerald-800" data-testid="upload-confirm-btn">
                        <Upload size={14} className="mr-1" /> {busy ? "Caricamento…" : "Carica"}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}

/* Card di un singolo collaboratore con tutte le voci della checklist */
export function CollabCard({ collab, anno, canUpload, isAdmin, onChanged }) {
    const navigate = useNavigate();
    const [upItem, setUpItem] = useState(null);

    const doUpload = async ({ file, data_rilascio, data_scadenza }) => {
        const fd = new FormData();
        fd.append("file", file);
        fd.append("req_key", upItem.key);
        fd.append("tipologia", upItem.label);
        fd.append("anno", String(anno));
        if (data_rilascio) fd.append("data_rilascio", data_rilascio);
        if (data_scadenza) fd.append("data_scadenza", data_scadenza);
        const url = isAdmin ? `/auth/users/${collab.id}/documenti-annuali` : "/me/documenti-annuali";
        await api.post(url, fd, { headers: { "Content-Type": "multipart/form-data" } });
        toast.success("Documento caricato");
        onChanged();
    };

    const doDelete = async (fileId) => {
        if (!window.confirm("Eliminare questo documento?")) return;
        const url = isAdmin ? `/auth/users/${collab.id}/documenti-annuali/${fileId}` : `/me/documenti-annuali/${fileId}`;
        await api.delete(url);
        toast.success("Eliminato");
        onChanged();
    };

    return (
        <div className="space-y-2" data-testid={`collab-card-${collab.id}`}>
            {collab.items.map((item) => (
                <div key={item.key} className="flex items-center gap-3 py-2 px-3 rounded-lg border border-slate-100 bg-white hover:bg-slate-50 transition">
                    <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 flex-wrap">
                            <span className="text-sm font-medium text-slate-800">{item.label}</span>
                            {item.obbligatorio && <span className="text-[9px] uppercase tracking-wide text-rose-500 font-bold">obbligatorio</span>}
                            <StatoBadge item={item} />
                        </div>
                        {item.files?.length > 0 && (
                            <div className="flex flex-wrap gap-2 mt-1">
                                {item.files.map((f) => (
                                    <span key={f.id} className="inline-flex items-center gap-1 text-[11px] bg-slate-100 rounded px-1.5 py-0.5">
                                        <FileText size={10} className="text-slate-500" />
                                        <a href={imgUrl(f.url)} target="_blank" rel="noreferrer"
                                            className="text-sky-700 hover:underline max-w-[160px] truncate"
                                            data-testid={`file-link-${f.id}`}>{f.nome_file || "documento"}</a>
                                        {f.data_scadenza && <span className="text-slate-400">· scad. {f.data_scadenza}</span>}
                                        {f.source === "cert" && <span className="text-[9px] text-violet-500 font-semibold">da Certificati</span>}
                                        {canUpload && f.source !== "cert" && (
                                            <button onClick={() => doDelete(f.id)} className="text-rose-500 hover:text-rose-700" data-testid={`file-del-${f.id}`}>
                                                <Trash2 size={11} />
                                            </button>
                                        )}
                                    </span>
                                ))}
                            </div>
                        )}
                    </div>
                    <div className="shrink-0">
                        {item.is_ivass ? (
                            <Button size="sm" variant="outline" className="h-7 text-xs"
                                onClick={() => navigate(`/corsi-ivass?uid=${collab.id}`)} data-testid={`ivass-open-${collab.id}`}>
                                <GraduationCap size={13} className="mr-1" /> Corsi IVASS
                            </Button>
                        ) : canUpload ? (
                            <Button size="sm" variant="outline" className="h-7 text-xs"
                                onClick={() => setUpItem(item)} data-testid={`upload-open-${collab.id}-${item.key}`}>
                                <Upload size={13} className="mr-1" /> {item.files?.length ? "Aggiungi" : "Carica"}
                            </Button>
                        ) : null}
                    </div>
                </div>
            ))}
            <UploadDialog open={!!upItem} onOpenChange={(v) => !v && setUpItem(null)} item={upItem} onUpload={doUpload} />
        </div>
    );
}

/* Dialog configurazione checklist (solo admin) */
function ConfigDialog({ open, onOpenChange, checklist, onSaved }) {
    const [rows, setRows] = useState([]);
    const [busy, setBusy] = useState(false);
    useEffect(() => { if (open) setRows(checklist.map((c) => ({ ...c }))); }, [open, checklist]);

    const set = (i, k, v) => setRows((p) => p.map((r, idx) => idx === i ? { ...r, [k]: v } : r));
    const add = () => setRows((p) => [...p, { key: "", label: "", obbligatorio: true, is_ivass: false }]);
    const remove = (i) => setRows((p) => p.filter((_, idx) => idx !== i));

    const save = async () => {
        const valid = rows.filter((r) => (r.label || "").trim());
        if (!valid.length) { toast.error("Aggiungi almeno un documento"); return; }
        setBusy(true);
        try {
            const r = await api.put("/config/documenti-annuali-collab", { checklist: valid });
            toast.success("Checklist salvata");
            onSaved(r.data.checklist);
            onOpenChange(false);
        } catch (e) { toast.error(e.response?.data?.detail || "Errore salvataggio"); }
        finally { setBusy(false); }
    };

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="max-w-2xl">
                <DialogHeader><DialogTitle>Documenti annuali richiesti</DialogTitle></DialogHeader>
                <div className="space-y-2 py-1 max-h-[55vh] overflow-y-auto">
                    {rows.map((r, i) => (
                        <div key={i} className="flex items-center gap-2 p-2 rounded border border-slate-100">
                            <Input value={r.label} placeholder="Nome documento…"
                                onChange={(e) => set(i, "label", e.target.value)}
                                className="flex-1" data-testid={`cfg-label-${i}`} />
                            <label className="flex items-center gap-1 text-xs text-slate-600 whitespace-nowrap cursor-pointer">
                                <input type="checkbox" checked={!!r.obbligatorio}
                                    onChange={(e) => set(i, "obbligatorio", e.target.checked)}
                                    data-testid={`cfg-obbl-${i}`} /> Obbligatorio
                            </label>
                            {r.is_ivass && <span className="text-[10px] text-emerald-600 font-semibold whitespace-nowrap">auto IVASS</span>}
                            <button onClick={() => remove(i)} className="text-rose-500 hover:text-rose-700 p-1" data-testid={`cfg-del-${i}`}>
                                <Trash2 size={14} />
                            </button>
                        </div>
                    ))}
                    <Button variant="outline" size="sm" onClick={add} data-testid="cfg-add-row">
                        <Plus size={14} className="mr-1" /> Aggiungi card documento
                    </Button>
                </div>
                <DialogFooter>
                    <Button onClick={save} disabled={busy} className="bg-emerald-700 hover:bg-emerald-800" data-testid="cfg-save-btn">
                        {busy ? "Salvataggio…" : "Salva checklist"}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}

export default function DocumentiAnnualiCollab() {
    const { user } = useAuth();
    const [anno, setAnno] = useState(new Date().getFullYear());
    const [data, setData] = useState(null);
    const [loading, setLoading] = useState(true);
    const [cfgOpen, setCfgOpen] = useState(false);
    const [expanded, setExpanded] = useState({});
    const [q, setQ] = useState("");

    const isAdmin = user?.role === "admin";

    const load = useCallback(() => {
        setLoading(true);
        api.get("/collaboratori/documenti-annuali", { params: { anno } })
            .then((r) => setData(r.data))
            .catch(() => toast.error("Errore caricamento"))
            .finally(() => setLoading(false));
    }, [anno]);

    useEffect(() => { load(); }, [load]);

    const toggle = (id) => setExpanded((p) => ({ ...p, [id]: !p[id] }));

    const collaboratori = (data?.collaboratori || []).filter((c) =>
        !q || (c.name || "").toLowerCase().includes(q.toLowerCase()) || (c.email || "").toLowerCase().includes(q.toLowerCase()));

    return (
        <div data-testid="documenti-collaboratori-page" className="space-y-4">
            <PageHeader
                title={<span className="flex items-center gap-2"><FolderCheck className="text-emerald-600" /> Documenti Collaboratori</span>}
                subtitle={isAdmin ? "Vista annuale conformità · casellario, carichi pendenti, IVASS e altro · upload diretto" : "I tuoi documenti annuali da fornire · carica direttamente da qui"}
                actions={
                    <div className="flex gap-2 items-center">
                        <Select value={String(anno)} onValueChange={(v) => setAnno(parseInt(v))}>
                            <SelectTrigger className="w-28" data-testid="anno-sel"><SelectValue /></SelectTrigger>
                            <SelectContent>
                                {[1, 0, -1, -2, -3].map((d) => {
                                    const y = new Date().getFullYear() + d;
                                    return <SelectItem key={y} value={String(y)}>{y}</SelectItem>;
                                })}
                            </SelectContent>
                        </Select>
                        {isAdmin && (
                            <Button variant="outline" onClick={() => setCfgOpen(true)} data-testid="cfg-open-btn">
                                <Settings2 size={14} className="mr-1" /> Gestisci documenti richiesti
                            </Button>
                        )}
                    </div>
                }
            />

            {loading || !data ? <Loading /> : (
                !isAdmin ? (
                    /* Vista collaboratore: solo i propri */
                    collaboratori.length === 0 ? <Empty message="Nessun documento richiesto." /> : (
                        <Card className="p-4">
                            <h4 className="font-semibold text-sm mb-3 text-slate-800">Checklist documenti {anno}</h4>
                            <CollabCard collab={collaboratori[0]} anno={anno} canUpload isAdmin={false} onChanged={load} />
                        </Card>
                    )
                ) : (
                    /* Vista admin: panoramica immediata di tutti */
                    <>
                        <div className="relative max-w-sm">
                            <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
                            <Input placeholder="Cerca collaboratore…" value={q} onChange={(e) => setQ(e.target.value)}
                                className="pl-9" data-testid="search-collab" />
                        </div>
                        {collaboratori.length === 0 ? <Empty message="Nessun collaboratore trovato." /> : (
                            <div className="space-y-2">
                                {collaboratori.map((c) => {
                                    const open = !!expanded[c.id];
                                    const ok = c.mancanti === 0;
                                    return (
                                        <Card key={c.id} className="overflow-hidden">
                                            <button onClick={() => toggle(c.id)}
                                                className="w-full flex items-center gap-3 p-3 hover:bg-slate-50 text-left transition"
                                                data-testid={`collab-row-${c.id}`}>
                                                {open ? <ChevronDown size={16} className="text-slate-400" /> : <ChevronRight size={16} className="text-slate-400" />}
                                                <div className="flex-1 min-w-0">
                                                    <div className="font-medium text-sm text-slate-800 truncate">{c.name}</div>
                                                    <div className="text-[11px] text-slate-400 truncate">{c.email}</div>
                                                </div>
                                                <div className="flex items-center gap-1.5">
                                                    {c.items.map((it) => {
                                                        const s = STATI[it.stato] || STATI.assente;
                                                        return <span key={it.key} title={`${it.label}: ${s.label}`}
                                                            className={`inline-block w-2.5 h-2.5 rounded-full ${s.cls.split(" ")[0]}`}
                                                            data-testid={`dot-${c.id}-${it.key}`} />;
                                                    })}
                                                </div>
                                                {ok ? (
                                                    <Badge variant="outline" className="bg-emerald-50 text-emerald-700 border-emerald-200 text-[10px]">
                                                        <Check size={11} className="mr-0.5" /> Completo
                                                    </Badge>
                                                ) : (
                                                    <Badge variant="outline" className="bg-rose-50 text-rose-600 border-rose-200 text-[10px]" data-testid={`mancanti-${c.id}`}>
                                                        <AlertTriangle size={11} className="mr-0.5" /> {c.mancanti} da sistemare
                                                    </Badge>
                                                )}
                                            </button>
                                            {open && (
                                                <div className="p-3 pt-0 border-t border-slate-100">
                                                    <CollabCard collab={c} anno={anno} canUpload isAdmin onChanged={load} />
                                                </div>
                                            )}
                                        </Card>
                                    );
                                })}
                            </div>
                        )}
                    </>
                )
            )}

            <ConfigDialog open={cfgOpen} onOpenChange={setCfgOpen}
                checklist={data?.checklist || []}
                onSaved={() => load()} />
        </div>
    );
}
