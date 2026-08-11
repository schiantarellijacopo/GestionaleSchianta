/**
 * Biblioteca — archivio PDF normativi in due sezioni (Previdenza + Condizioni
 * di Polizza) + Schede di Calcolo auto-generate dall'AI con verifica annuale.
 */
import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { PageHeader, Loading } from "@/components/Shared";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
    Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
    FolderOpen, Folder, Upload, Trash2, Download, Plus, Cloud,
    Sparkles, FileText, Loader2, Landmark, ShieldCheck, Calculator,
    AlertTriangle, CheckCircle2, RefreshCw,
} from "lucide-react";
import { toast } from "sonner";

const TABS = [
    { key: "previdenza", label: "Biblioteca Previdenza", icon: Landmark },
    { key: "condizioni", label: "Condizioni di Polizza", icon: ShieldCheck },
    { key: "schede", label: "Schede di Calcolo", icon: Calculator },
];

export default function BibliotecaPrevidenza() {
    const [tab, setTab] = useState("previdenza");
    return (
        <div className="space-y-4" data-testid="biblioteca-page">
            <PageHeader title="Biblioteca"
                subtitle="PDF normativi e condizioni di polizza usati dall'AI: calcoli pensione, analisi cliente e verifiche annuali" />
            <div className="flex flex-wrap gap-2">
                {TABS.map((t) => (
                    <button key={t.key} onClick={() => setTab(t.key)}
                            className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold border transition-colors ${tab === t.key ? "bg-sky-700 text-white border-sky-700" : "bg-white text-slate-700 border-slate-300 hover:border-sky-500"}`}
                            data-testid={`biblioteca-tab-${t.key}`}>
                        <t.icon size={15} /> {t.label}
                    </button>
                ))}
            </div>
            {tab === "schede" ? <SchedeCalcoloTab /> : <SezioneBiblioteca key={tab} sezione={tab} />}
        </div>
    );
}

// ─────────────────────────────────────────────────────────────
function SezioneBiblioteca({ sezione }) {
    const [cartelle, setCartelle] = useState(null);
    const [sel, setSel] = useState(null);
    const [docs, setDocs] = useState([]);
    const [uploading, setUploading] = useState(false);
    const [syncing, setSyncing] = useState(false);
    const [dragOver, setDragOver] = useState(false);
    const [nuovaCartella, setNuovaCartella] = useState("");
    const fileRef = useRef(null);

    const loadCartelle = async () => {
        const r = await api.get("/biblioteca-previdenza/cartelle", { params: { sezione } });
        setCartelle(r.data);
        return r.data;
    };
    const loadDocs = async (cart) => {
        const r = await api.get("/biblioteca-previdenza/documenti", { params: { sezione, cartella: cart } });
        setDocs(r.data);
    };
    useEffect(() => {
        loadCartelle().then((c) => {
            if (c?.length) setSel(c[0].nome);
        }).catch((e) => toast.error("Errore caricamento: " + e.message));
    }, []);
    useEffect(() => { if (sel) loadDocs(sel).catch(() => {}); }, [sel]);

    const uploadFiles = async (fileList) => {
        const files = Array.from(fileList || []);
        if (!files.length || !sel) return;
        setUploading(true);
        try {
            const fd = new FormData();
            files.forEach((f) => fd.append("files", f));
            fd.append("cartella", sel);
            fd.append("sezione", sezione);
            const r = await api.post("/biblioteca-previdenza/upload", fd, {
                headers: { "Content-Type": "multipart/form-data" },
            });
            const { importati, saltati, errori, su_drive } = r.data;
            if (importati.length) {
                toast.success(`${importati.length} documenti importati in ${sel}` +
                    (su_drive ? ` (${su_drive} copiati anche su Google Drive)` : ""));
            }
            if (saltati.length) toast.info(`${saltati.length} già presenti (saltati)`);
            (errori || []).forEach((e) => toast.error(`${e.file}: ${e.errore}`));
            await Promise.all([loadCartelle(), loadDocs(sel)]);
        } catch (e) {
            toast.error("Errore upload: " + (e.response?.data?.detail || e.message));
        } finally { setUploading(false); }
    };

    const syncDrive = async () => {
        setSyncing(true);
        try {
            let restanti = 1, tot = 0, giri = 0, msg = null;
            while (restanti > 0 && giri < 25) {
                const r = await api.post("/biblioteca-previdenza/sync-drive", {});
                tot += r.data.importati.length;
                restanti = r.data.restanti || 0;
                giri += 1;
                msg = r.data.messaggio;
                (r.data.errori || []).slice(0, 3).forEach((e) => toast.error(`${e.file}: ${e.errore}`));
                if (msg) break;
            }
            if (msg) toast.info(msg, { duration: 9000 });
            else toast.success(`Sync Drive completata: ${tot} documenti importati`);
            await Promise.all([loadCartelle(), sel ? loadDocs(sel) : Promise.resolve()]);
        } catch (e) {
            toast.error(e.response?.data?.detail || e.message);
        } finally { setSyncing(false); }
    };

    const creaCartella = async () => {
        const nome = nuovaCartella.trim();
        if (!nome) return;
        try {
            await api.post("/biblioteca-previdenza/cartelle", { nome, sezione });
            setNuovaCartella("");
            await loadCartelle();
            setSel(nome.toUpperCase());
            toast.success("Cartella creata");
        } catch (e) { toast.error(e.response?.data?.detail || e.message); }
    };

    const deleteDoc = async (d) => {
        if (!window.confirm(`Eliminare "${d.nome_file}"?`)) return;
        await api.delete(`/biblioteca-previdenza/documenti/${d.id}`);
        toast.success("Documento eliminato");
        await Promise.all([loadCartelle(), loadDocs(sel)]);
    };

    const downloadDoc = async (d) => {
        try {
            const r = await api.get(`/biblioteca-previdenza/documenti/${d.id}/download`, { responseType: "blob" });
            const url = URL.createObjectURL(r.data);
            window.open(url, "_blank");
        } catch { toast.error("Download non riuscito"); }
    };

    if (!cartelle) return <Loading />;

    const driveRoot = sezione === "previdenza" ? "PASS PREVIDENZA" : "CONDIZIONI DI POLIZZA";

    return (
        <div className="space-y-4" data-testid={`biblioteca-sezione-${sezione}`}>
            {/* Cartelle */}
            <div className="flex flex-wrap gap-2 items-center">
                {cartelle.map((c) => (
                    <button key={c.nome} onClick={() => setSel(c.nome)}
                            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium border transition-colors ${sel === c.nome ? "bg-sky-700 text-white border-sky-700" : "bg-white text-slate-700 border-slate-300 hover:border-sky-500"}`}
                            data-testid={`cartella-${c.nome.toLowerCase().replace(/ /g, "-")}`}>
                        {sel === c.nome ? <FolderOpen size={13} /> : <Folder size={13} />}
                        {c.nome}
                        <span className={`rounded-full px-1.5 text-[10px] ${sel === c.nome ? "bg-white/20" : "bg-slate-100"}`}>{c.documenti}</span>
                    </button>
                ))}
                <div className="flex items-center gap-1">
                    <Input value={nuovaCartella} onChange={(e) => setNuovaCartella(e.target.value)}
                           placeholder="Nuova cartella..." className="h-8 w-36 text-xs"
                           onKeyDown={(e) => e.key === "Enter" && creaCartella()}
                           data-testid="nuova-cartella-input" />
                    <Button size="sm" variant="outline" onClick={creaCartella} data-testid="nuova-cartella-btn">
                        <Plus size={14} />
                    </Button>
                </div>
            </div>

            {/* Upload area */}
            <Card
                className={`p-6 border-2 border-dashed text-center transition-colors ${dragOver ? "border-sky-500 bg-sky-50" : "border-slate-300"}`}
                onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
                onDragLeave={() => setDragOver(false)}
                onDrop={(e) => { e.preventDefault(); setDragOver(false); uploadFiles(e.dataTransfer.files); }}
                data-testid="upload-dropzone">
                <input ref={fileRef} type="file" multiple accept=".pdf,.txt"
                       className="hidden" onChange={(e) => { uploadFiles(e.target.files); e.target.value = ""; }}
                       data-testid="upload-input" />
                <Upload className="mx-auto text-slate-400 mb-2" size={28} />
                <div className="text-sm text-slate-600">
                    Trascina qui i PDF (anche molti in un colpo) oppure{" "}
                    <button className="text-sky-700 font-semibold underline" onClick={() => fileRef.current?.click()}>
                        selezionali
                    </button>
                    {" "}— archiviati in <strong>{sel}</strong> e copiati anche su Google Drive
                </div>
                <div className="mt-3 flex justify-center gap-2 flex-wrap">
                    <Button size="sm" variant="outline" disabled={syncing} onClick={syncDrive} data-testid="sync-drive-btn">
                        {syncing ? <Loader2 size={14} className="animate-spin mr-1" /> : <Cloud size={14} className="mr-1" />}
                        Sincronizza da Google Drive
                    </Button>
                    {sezione === "condizioni" && (
                        <CercaCondizioniButtons onImported={() => loadDocs(sel).catch(() => {})} loadCartelle={loadCartelle} />
                    )}
                </div>
                <div className="mt-2 text-[11px] text-slate-400">
                    Cartella Drive: <strong>{driveRoot}</strong> (anche condivisa) — le sottocartelle diventano categorie.
                </div>
                {uploading && <div className="mt-2 text-xs text-sky-700 flex items-center justify-center gap-1"><Loader2 size={12} className="animate-spin" /> Caricamento ed estrazione testo in corso...</div>}
            </Card>

            {/* Documenti */}
            <Card className="p-5 border-slate-200">
                <div className="text-sm font-semibold text-slate-800 mb-3 flex items-center gap-2">
                    <FileText size={15} /> Documenti in {sel} ({docs.length})
                </div>
                {docs.length === 0 ? (
                    <div className="text-xs text-slate-400 italic">Nessun documento in questa cartella.</div>
                ) : (
                    <div className="max-h-[480px] overflow-y-auto">
                        <table className="w-full text-xs">
                            <thead className="sticky top-0 bg-white">
                                <tr className="text-slate-500 border-b">
                                    <th className="text-left py-1.5">Nome file</th>
                                    <th className="text-left py-1.5">Sottocategoria</th>
                                    <th className="text-left py-1.5">Pag.</th>
                                    <th className="text-left py-1.5">Testo AI</th>
                                    <th className="text-left py-1.5">Data</th>
                                    <th></th>
                                </tr>
                            </thead>
                            <tbody>
                                {docs.map((d) => (
                                    <tr key={d.id} className="border-b border-slate-100 hover:bg-slate-50" data-testid={`doc-row-${d.id}`}>
                                        <td className="py-1.5 font-medium text-slate-800">{d.nome_file}</td>
                                        <td className="text-slate-500">{d.sottocartella || "—"}</td>
                                        <td>{d.pagine || "—"}</td>
                                        <td>{d.testo_ok
                                            ? <span className="text-emerald-600 font-semibold">✓</span>
                                            : <span className="text-amber-600">solo archivio</span>}</td>
                                        <td className="text-slate-500">{(d.created_at || "").slice(0, 10)}</td>
                                        <td className="text-right whitespace-nowrap">
                                            <Button size="sm" variant="ghost" onClick={() => downloadDoc(d)} title="Apri/Scarica"
                                                    data-testid={`doc-download-${d.id}`}>
                                                <Download size={13} />
                                            </Button>
                                            <Button size="sm" variant="ghost" onClick={() => deleteDoc(d)} title="Elimina"
                                                    data-testid={`doc-delete-${d.id}`}>
                                                <Trash2 size={13} className="text-rose-600" />
                                            </Button>
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                )}
            </Card>

            {/* Consulto AI */}
            <ConsultaAI cartelle={cartelle} defaultCartella={sel} sezione={sezione} />
        </div>
    );
}

function ConsultaAI({ cartelle, defaultCartella, sezione }) {
    const [cartella, setCartella] = useState(defaultCartella || "");
    const [domanda, setDomanda] = useState("");
    const [risposta, setRisposta] = useState(null);
    const [loading, setLoading] = useState(false);

    useEffect(() => { if (defaultCartella) setCartella(defaultCartella); }, [defaultCartella]);

    const chiedi = async () => {
        if (!domanda.trim()) { toast.error("Scrivi una domanda"); return; }
        setLoading(true); setRisposta(null);
        try {
            const r = await api.post("/biblioteca-previdenza/consulta-ai", { cartella, domanda, sezione });
            setRisposta(r.data);
        } catch (e) {
            toast.error(e.response?.data?.detail || e.message);
        } finally { setLoading(false); }
    };

    const placeholder = sezione === "previdenza"
        ? "Es: quali sono i requisiti e la formula di calcolo della pensione di invalidità per un dipendente pubblico?"
        : "Es: cosa copre la garanzia cristalli nella polizza auto di questa compagnia? Quali sono le franchigie?";

    return (
        <Card className="p-5 border-violet-200 bg-violet-50/40" data-testid="consulta-ai-card">
            <div className="text-sm font-semibold text-violet-900 mb-2 flex items-center gap-2">
                <Sparkles size={15} /> Chiedi all'AI (usa i documenti della biblioteca come fonte)
            </div>
            <div className="flex flex-col md:flex-row gap-2 mb-2">
                <Select value={cartella} onValueChange={setCartella}>
                    <SelectTrigger className="w-full md:w-64 h-9 text-xs bg-white" data-testid="consulta-ai-cartella">
                        <SelectValue placeholder="Cartella" />
                    </SelectTrigger>
                    <SelectContent>
                        {(cartelle || []).map((c) => (
                            <SelectItem key={c.nome} value={c.nome}>{c.nome} ({c.documenti})</SelectItem>
                        ))}
                    </SelectContent>
                </Select>
                <Textarea value={domanda} onChange={(e) => setDomanda(e.target.value)}
                          placeholder={placeholder}
                          className="flex-1 text-xs bg-white min-h-[38px]" rows={2}
                          data-testid="consulta-ai-domanda" />
                <Button onClick={chiedi} disabled={loading} className="bg-violet-700 hover:bg-violet-800"
                        data-testid="consulta-ai-btn">
                    {loading ? <Loader2 size={14} className="animate-spin mr-1" /> : <Sparkles size={14} className="mr-1" />}
                    Chiedi
                </Button>
            </div>
            {risposta && (
                <div className="bg-white border border-violet-200 rounded p-3 text-xs text-slate-800 whitespace-pre-wrap"
                     data-testid="consulta-ai-risposta">
                    {risposta.risposta}
                    <div className="mt-2 pt-2 border-t border-slate-100 text-[10px] text-slate-500">
                        Fonti: {(risposta.fonti || []).join(" · ") || "—"}
                    </div>
                </div>
            )}
        </Card>
    );
}

// ─────────────────────────────────────────────────────────────
// SCHEDE DI CALCOLO — generate dall'AI, verifica annuale
// ─────────────────────────────────────────────────────────────
function SchedeCalcoloTab() {
    const [cartelle, setCartelle] = useState([]);
    const [schede, setSchede] = useState(null);
    const [generating, setGenerating] = useState(null);
    const [aperta, setAperta] = useState(null);

    const load = async () => {
        const [c, s] = await Promise.all([
            api.get("/biblioteca-previdenza/cartelle", { params: { sezione: "previdenza" } }),
            api.get("/biblioteca-previdenza/schede-calcolo"),
        ]);
        setCartelle(c.data.filter((x) => x.documenti > 0));
        setSchede(s.data);
    };
    useEffect(() => { load().catch((e) => toast.error(e.message)); }, []);

    const genera = async (categoria) => {
        setGenerating(categoria);
        try {
            const r = await api.post("/biblioteca-previdenza/schede-calcolo/genera", { cartella: categoria });
            const jid = r.data?.job_id;
            if (!jid) throw new Error("Job non avviato");
            toast.info(`Generazione ${categoria} avviata (potrebbe richiedere 1-2 minuti)…`, { duration: 4000 });
            // POLLING del job (max 5 min)
            const scheda = await pollJob(jid, categoria);
            if (scheda) {
                const stato = scheda.stato_verifica;
                toast.success(
                    `Scheda ${categoria}: ${stato === "invariata"
                        ? "verificata, criteri INVARIATI"
                        : stato === "cambiata"
                            ? "ATTENZIONE: criteri CAMBIATI"
                            : "generata"}`,
                    { duration: 7000 });
                await load();
                setAperta(categoria);
            }
        } catch (e) {
            toast.error(e.response?.data?.detail || e.message || "Errore generazione");
        } finally { setGenerating(null); }
    };

    // Polling job: fino a 5 minuti, 1 chiamata ogni 2s
    const pollJob = async (jid, categoria) => {
        for (let i = 0; i < 150; i++) {
            await new Promise((r) => setTimeout(r, 2000));
            try {
                const r = await api.get(`/biblioteca-previdenza/jobs/${jid}`);
                const j = r.data;
                if (j.stato === "done") return j.risultato;
                if (j.stato === "error") throw new Error(j.errore || "Errore generazione");
            } catch (e) {
                if (e.response?.status === 404) throw new Error("Job non trovato");
                if (i > 5) throw e;
            }
        }
        throw new Error(`Timeout: la generazione di ${categoria} sta impiegando troppo tempo. Ritenta più tardi.`);
    };

    if (!schede) return <Loading />;
    const schedaDi = (cat) => schede.find((s) => s.categoria === cat);

    return (
        <div className="space-y-3" data-testid="schede-calcolo-tab">
            <Card className="p-4 border-sky-200 bg-sky-50/50 text-xs text-slate-700">
                L'AI legge i PDF della categoria, estrae <strong>requisiti, formule e parametri</strong> di calcolo
                (invalidità, inabilità, superstiti), li <strong>confronta con i criteri del CRM</strong> segnalando le
                discrepanze e produce una scheda da <strong>riverificare ogni anno</strong>: rigenerandola, ti dice se i
                criteri sono cambiati rispetto alla versione precedente.
            </Card>
            {cartelle.map((c) => {
                const s = schedaDi(c.nome);
                const isOpen = aperta === c.nome;
                return (
                    <Card key={c.nome} className="p-4 border-slate-200" data-testid={`scheda-card-${c.nome.toLowerCase().replace(/ /g, "-")}`}>
                        <div className="flex items-center gap-3 flex-wrap">
                            <button className="flex items-center gap-2 font-semibold text-sm text-slate-800"
                                    onClick={() => setAperta(isOpen ? null : c.nome)}>
                                <Calculator size={15} className="text-sky-700" /> {c.nome}
                                <span className="text-[10px] text-slate-400 font-normal">({c.documenti} PDF)</span>
                            </button>
                            {s && <StatoBadge stato={s.stato_verifica} />}
                            {s && <span className="text-[10px] text-slate-400">ultima verifica: {(s.generated_at || "").slice(0, 10)} (anno {s.anno})</span>}
                            {s?.stato_verifica === "cambiata" && s?.spiegazione_modifiche && !isOpen && (
                                <span className="text-[10px] text-rose-600 font-medium basis-full md:basis-auto truncate max-w-md">
                                    → {s.spiegazione_modifiche.slice(0, 120)}{s.spiegazione_modifiche.length > 120 ? "…" : ""}
                                </span>
                            )}
                            <div className="flex-1" />
                            {s && (
                                <a href={`${process.env.REACT_APP_BACKEND_URL}/api/biblioteca-previdenza/schede-calcolo/${encodeURIComponent(c.nome)}/pdf`}
                                   target="_blank" rel="noreferrer"
                                   className="inline-flex items-center gap-1 h-7 text-xs border border-slate-300 rounded px-2 hover:bg-slate-100 text-slate-700 font-medium"
                                   title="Scarica il PDF con requisiti, formule, parametri, discrepanze e esempio di calcolo passo-passo"
                                   data-testid={`pdf-scheda-${c.nome.toLowerCase().replace(/ /g, "-")}`}>
                                    <FileText size={12} /> PDF calcolo
                                </a>
                            )}
                            <Button size="sm" variant="outline" className="h-7 text-xs"
                                    disabled={generating === c.nome}
                                    onClick={() => genera(c.nome)}
                                    data-testid={`genera-scheda-${c.nome.toLowerCase().replace(/ /g, "-")}`}>
                                {generating === c.nome
                                    ? <Loader2 size={12} className="animate-spin mr-1" />
                                    : <RefreshCw size={12} className="mr-1" />}
                                {s ? "Verifica annuale (rigenera)" : "Genera scheda"}
                            </Button>
                        </div>
                        {isOpen && s && <SchedaDettaglio scheda={s} />}
                        {isOpen && !s && <div className="mt-2 text-xs text-slate-400 italic">Nessuna scheda ancora generata per questa categoria.</div>}
                    </Card>
                );
            })}
        </div>
    );
}

function StatoBadge({ stato }) {
    const map = {
        nuova: ["bg-sky-100 text-sky-700 border-sky-300", "NUOVA"],
        invariata: ["bg-emerald-100 text-emerald-700 border-emerald-300", "CRITERI INVARIATI"],
        cambiata: ["bg-rose-100 text-rose-700 border-rose-300", "CRITERI CAMBIATI"],
    };
    const [cls, label] = map[stato] || map.nuova;
    return <span className={`text-[9px] border rounded px-1.5 py-0.5 font-bold ${cls}`}>{label}</span>;
}

function SchedaDettaglio({ scheda }) {
    const c = scheda.contenuto || {};
    return (
        <div className="mt-3 pt-3 border-t border-slate-100 space-y-3 text-xs" data-testid="scheda-dettaglio">
            {/* COSA È CAMBIATO — sempre in evidenza quando i criteri cambiano */}
            {scheda.stato_verifica === "cambiata" && (
                <div className="bg-rose-50 border-2 border-rose-300 rounded-lg p-3" data-testid="scheda-modifiche">
                    <div className="font-bold text-rose-800 mb-1 flex items-center gap-2 text-sm">
                        <AlertTriangle size={15} /> Cosa è cambiato rispetto alla verifica precedente
                    </div>
                    {scheda.spiegazione_modifiche && (
                        <p className="text-rose-900 mb-2">{scheda.spiegazione_modifiche}</p>
                    )}
                    {(scheda.modifiche || []).length > 0 ? (
                        <table className="w-full bg-white border border-rose-200 rounded">
                            <thead className="bg-rose-100 text-rose-800">
                                <tr>{["Sezione", "Criterio", "Prima", "Ora (nuovo calcolo)", "Impatto sul calcolo"].map((h) => (
                                    <th key={h} className="text-left px-2 py-1 font-semibold">{h}</th>))}</tr>
                            </thead>
                            <tbody>
                                {scheda.modifiche.map((m, i) => (
                                    <tr key={i} className="border-t border-rose-100 align-top">
                                        <td className="px-2 py-1 uppercase text-[9px] font-bold text-rose-700">{m.sezione}</td>
                                        <td className="px-2 py-1 font-medium">{m.criterio}</td>
                                        <td className="px-2 py-1 line-through text-slate-500">{m.prima}</td>
                                        <td className="px-2 py-1 font-semibold text-emerald-700">{m.dopo}</td>
                                        <td className="px-2 py-1">{m.impatto_sul_calcolo}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    ) : (
                        scheda.diff_note && <div className="text-rose-700">{scheda.diff_note}</div>
                    )}
                </div>
            )}
            {scheda.stato_verifica === "invariata" && scheda.diff_note && (
                <div className="text-emerald-700 bg-emerald-50 border border-emerald-200 rounded p-2 flex items-center gap-2">
                    <CheckCircle2 size={13} /> {scheda.diff_note}
                </div>
            )}
            {c.sintesi && <p className="text-slate-700">{c.sintesi}</p>}
            {(c.requisiti || []).length > 0 && (
                <TabellaScheda titolo="Requisiti" rows={c.requisiti} cols={["prestazione", "requisito"]} />
            )}
            {(c.formule || []).length > 0 && (
                <TabellaScheda titolo="Formule di calcolo" rows={c.formule} cols={["prestazione", "formula"]} />
            )}
            {(c.parametri || []).length > 0 && (
                <TabellaScheda titolo="Parametri chiave" rows={c.parametri} cols={["nome", "valore", "fonte"]} />
            )}
            {(c.discrepanze_crm || []).length > 0 ? (
                <div>
                    <div className="font-semibold text-rose-700 mb-1 flex items-center gap-1">
                        <AlertTriangle size={12} /> Discrepanze con i criteri del CRM
                    </div>
                    <table className="w-full border border-rose-200">
                        <thead className="bg-rose-50 text-rose-800">
                            <tr>{["Parametro", "Valore CRM", "Valore documenti", "Gravità", "Correzione"].map((h) => (
                                <th key={h} className="text-left px-2 py-1 font-semibold">{h}</th>))}</tr>
                        </thead>
                        <tbody>
                            {c.discrepanze_crm.map((d, i) => (
                                <tr key={i} className="border-t border-rose-100">
                                    <td className="px-2 py-1 font-medium">{d.parametro}</td>
                                    <td className="px-2 py-1">{d.valore_crm}</td>
                                    <td className="px-2 py-1">{d.valore_documenti}</td>
                                    <td className="px-2 py-1 uppercase font-bold text-[9px]">{d.gravita}</td>
                                    <td className="px-2 py-1">{d.correzione_suggerita}</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            ) : (
                <div className="text-emerald-700 flex items-center gap-1">
                    <CheckCircle2 size={13} /> Nessuna discrepanza rilevata con i criteri di calcolo del CRM.
                </div>
            )}
            {c.note_verifica_annuale && (
                <div className="text-slate-500 italic">Verifica annuale: {c.note_verifica_annuale}</div>
            )}
            <div className="text-[10px] text-slate-400">
                Fonti: {(scheda.fonti || []).slice(0, 10).join(" · ")}{(scheda.fonti || []).length > 10 ? ` +${scheda.fonti.length - 10}` : ""}
            </div>
        </div>
    );
}

function TabellaScheda({ titolo, rows, cols }) {
    return (
        <div>
            <div className="font-semibold text-slate-700 mb-1">{titolo}</div>
            <table className="w-full border border-slate-200">
                <tbody>
                    {rows.map((r, i) => (
                        <tr key={i} className={i % 2 ? "bg-slate-50/60" : ""}>
                            {cols.map((k) => (
                                <td key={k} className="px-2 py-1 border-t border-slate-100 align-top">{r[k]}</td>
                            ))}
                        </tr>
                    ))}
                </tbody>
            </table>
        </div>
    );
}

// ─────────────────────────────────────────────────────────────
// CERCA CONDIZIONI DAL WEB — pulsante manuale + job bulk
// ─────────────────────────────────────────────────────────────
function CercaCondizioniButtons({ onImported }) {
    const [openManuale, setOpenManuale] = useState(false);
    const [compagnia, setCompagnia] = useState("");
    const [prodotto, setProdotto] = useState("");
    const [ramo, setRamo] = useState("");
    const [busy, setBusy] = useState(false);
    const [bulkJobId, setBulkJobId] = useState(null);
    const [bulkProgress, setBulkProgress] = useState(null);

    const cercaManuale = async () => {
        if (!compagnia.trim()) { toast.error("Indica almeno la compagnia"); return; }
        setBusy(true);
        try {
            const r = await api.post("/biblioteca-previdenza/cerca-condizioni",
                { compagnia, prodotto, ramo });
            const n = (r.data?.importati || []).length;
            if (n > 0) toast.success(`Importati ${n} PDF di condizioni dal web`, { duration: 6000 });
            else toast.info(r.data?.messaggio || "Nessun PDF trovato", { duration: 6000 });
            if (n > 0 && onImported) await onImported();
            setOpenManuale(false);
            setCompagnia(""); setProdotto(""); setRamo("");
        } catch (e) {
            toast.error(e.response?.data?.detail || e.message);
        } finally { setBusy(false); }
    };

    const cercaBulk = async () => {
        if (!window.confirm("Vuoi cercare le condizioni per TUTTE le compagnie del CRM che non hanno ancora documenti? "
                             + "Il job può richiedere diversi minuti.")) return;
        setBusy(true);
        try {
            const r = await api.post("/biblioteca-previdenza/cerca-condizioni-bulk",
                { solo_mancanti: true });
            const jid = r.data?.job_id;
            if (!jid) throw new Error("Job non avviato");
            setBulkJobId(jid);
            toast.info(`Job avviato su ${r.data?.totale_compagnie || 0} compagnie…`, { duration: 5000 });
            pollBulk(jid);
        } catch (e) {
            toast.error(e.response?.data?.detail || e.message);
            setBusy(false);
        }
    };

    const pollBulk = async (jid) => {
        for (let i = 0; i < 300; i++) {
            await new Promise((r) => setTimeout(r, 3000));
            try {
                const r = await api.get(`/biblioteca-previdenza/jobs/${jid}`);
                const j = r.data;
                setBulkProgress(j.progress);
                if (j.stato === "done") {
                    toast.success(`Job completato: ${j.risultato?.importati_totali || 0} PDF importati`,
                        { duration: 8000 });
                    if (onImported) await onImported();
                    setBusy(false); setBulkJobId(null); setBulkProgress(null);
                    return;
                }
                if (j.stato === "error") {
                    toast.error(`Job fallito: ${j.errore}`);
                    setBusy(false); setBulkJobId(null); setBulkProgress(null);
                    return;
                }
            } catch (e) {
                if (e.response?.status === 404) break;
            }
        }
        setBusy(false); setBulkJobId(null); setBulkProgress(null);
    };

    return (
        <>
            <Button size="sm" variant="outline" onClick={() => setOpenManuale(true)}
                    disabled={busy}
                    className="border-emerald-400 text-emerald-700 hover:bg-emerald-50"
                    data-testid="cerca-condizioni-manuale-btn">
                <Sparkles size={14} className="mr-1" /> Cerca dal Web (manuale)
            </Button>
            <Button size="sm" variant="outline" onClick={cercaBulk} disabled={busy}
                    className="border-violet-400 text-violet-700 hover:bg-violet-50"
                    data-testid="cerca-condizioni-bulk-btn">
                {busy && bulkJobId
                    ? <Loader2 size={14} className="animate-spin mr-1" />
                    : <Sparkles size={14} className="mr-1" />}
                Cerca dal Web (bulk tutte compagnie)
            </Button>

            {bulkProgress && (
                <div className="basis-full text-[11px] text-violet-700 mt-1 text-center">
                    {bulkProgress.corrente ? `Corrente: ${bulkProgress.corrente} · ` : ""}
                    Processate {bulkProgress.processate || 0}/{bulkProgress.totale || "?"} ·
                    Importate {bulkProgress.importati || 0}
                </div>
            )}

            {openManuale && (
                <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4"
                     onClick={() => !busy && setOpenManuale(false)}
                     data-testid="cerca-condizioni-dialog">
                    <Card className="max-w-md w-full p-5 space-y-3" onClick={(e) => e.stopPropagation()}>
                        <div className="font-semibold text-sm text-slate-800 flex items-center gap-2">
                            <Sparkles size={15} className="text-emerald-600" />
                            Cerca condizioni di polizza dal Web
                        </div>
                        <div className="text-[11px] text-slate-600">
                            L&apos;AI suggerisce fino a 5 URL pubblici del Fascicolo Informativo / Condizioni Generali,
                            il sistema tenta il download e valida il contenuto prima di salvarlo.
                        </div>
                        <div className="space-y-2">
                            <div>
                                <label className="text-[10px] font-semibold text-slate-500 uppercase">Compagnia *</label>
                                <Input value={compagnia} onChange={(e) => setCompagnia(e.target.value)}
                                       placeholder="Es: Generali, UnipolSai, Reale Mutua..."
                                       className="h-8 text-xs" data-testid="cerca-cond-compagnia" />
                            </div>
                            <div>
                                <label className="text-[10px] font-semibold text-slate-500 uppercase">Prodotto (opzionale)</label>
                                <Input value={prodotto} onChange={(e) => setProdotto(e.target.value)}
                                       placeholder="Es: Global 3.0, AutoPiù, Multirischi Casa..."
                                       className="h-8 text-xs" data-testid="cerca-cond-prodotto" />
                            </div>
                            <div>
                                <label className="text-[10px] font-semibold text-slate-500 uppercase">Ramo (opzionale)</label>
                                <Input value={ramo} onChange={(e) => setRamo(e.target.value)}
                                       placeholder="Es: Auto, Casa, Vita, Salute..."
                                       className="h-8 text-xs" data-testid="cerca-cond-ramo" />
                            </div>
                        </div>
                        <div className="flex justify-end gap-2 pt-2">
                            <Button size="sm" variant="outline" onClick={() => setOpenManuale(false)}
                                    disabled={busy}>Annulla</Button>
                            <Button size="sm" onClick={cercaManuale} disabled={busy || !compagnia.trim()}
                                    className="bg-emerald-600 hover:bg-emerald-700"
                                    data-testid="cerca-cond-submit">
                                {busy ? <Loader2 size={12} className="animate-spin mr-1" /> : <Sparkles size={12} className="mr-1" />}
                                Cerca
                            </Button>
                        </div>
                    </Card>
                </div>
            )}
        </>
    );
}
