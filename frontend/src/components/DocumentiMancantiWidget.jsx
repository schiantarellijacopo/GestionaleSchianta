/**
 * DocumentiMancantiWidget — mostra polizze senza PDF, veicoli senza libretto,
 * anagrafiche senza C.I. Filtrabile per collaboratore. Ogni riga permette:
 *  - Andare alla scheda
 *  - Allegare rapidamente un documento inline
 *  - Salvare una nota/sollecito
 */
import { useEffect, useState, useRef } from "react";
import { Link } from "react-router-dom";
import { api } from "@/lib/api";
import { Card } from "@/components/ui/card";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { FileWarning, FileText, IdCard, Car, X, ChevronRight, AlertTriangle, Printer, FileSpreadsheet, Paperclip, StickyNote, CheckCircle2, Loader2 } from "lucide-react";
import { toast } from "sonner";

export default function DocumentiMancantiWidget() {
    const [data, setData] = useState(null);
    const [open, setOpen] = useState(null);
    const [collabId, setCollabId] = useState("");
    const [collaboratori, setCollaboratori] = useState([]);
    const [note, setNote] = useState({});  // { entita_id: nota_str }

    const reload = () => {
        const params = collabId ? { collaboratore_id: collabId } : {};
        api.get("/insights/documenti-mancanti", { params })
            .then((r) => setData(r.data)).catch(() => setData({}));
    };

    useEffect(() => {
        api.get("/utenti").then((r) => setCollaboratori(
            (r.data || []).filter((u) => ["admin", "collaboratore", "dipendente"].includes(u.role))
        )).catch(() => setCollaboratori([]));
        api.get("/insights/documenti-mancanti/note").then((r) => {
            const map = {};
            (r.data || []).forEach((n) => { map[n.entita_id] = n.nota || ""; });
            setNote(map);
        }).catch(() => {});
    }, []);

    // eslint-disable-next-line react-hooks/exhaustive-deps
    useEffect(reload, [collabId]);

    if (!data || !data.totali) return null;
    const { polizze, veicoli, anagrafiche } = data.totali;
    const totale = polizze + veicoli + anagrafiche;
    const collNome = collaboratori.find((c) => c.id === collabId)?.name;

    return (
        <Card className="p-4 bg-gradient-to-br from-amber-50 via-white to-rose-50 border-amber-300" data-testid="docs-missing-widget">
            <div className="flex items-center gap-2 mb-3 flex-wrap">
                <AlertTriangle className="text-amber-600" size={18} />
                <h3 className="font-semibold text-amber-900 text-sm flex-1">
                    Documenti mancanti
                    {totale > 0 && <span className="ml-2 text-[11px] bg-amber-200 text-amber-900 px-2 py-0.5 rounded-full font-mono">{totale}</span>}
                </h3>
                <select value={collabId} onChange={(e) => setCollabId(e.target.value)}
                    className="text-xs border border-amber-300 rounded px-2 py-1 bg-white" data-testid="docs-missing-collab-filter">
                    <option value="">Tutti i collaboratori</option>
                    {collaboratori.map((c) => (
                        <option key={c.id} value={c.id}>{c.name || c.email}</option>
                    ))}
                </select>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
                <CardMissing label="Polizze senza PDF" count={polizze} icon={FileText} color="rose"
                    onClick={() => polizze > 0 && setOpen("polizze")} testid="missing-polizze-card" />
                <CardMissing label="Veicoli senza libretto" count={veicoli} icon={Car} color="amber"
                    onClick={() => veicoli > 0 && setOpen("veicoli")} testid="missing-veicoli-card" />
                <CardMissing label="Anagrafiche senza C.I." count={anagrafiche} icon={IdCard} color="orange"
                    onClick={() => anagrafiche > 0 && setOpen("anagrafiche")} testid="missing-anagrafiche-card" />
            </div>
            {open && (
                <ListaMancantiDialog
                    tipo={open} data={data} collNome={collNome}
                    note={note} setNote={setNote} onReload={reload}
                    onClose={() => setOpen(null)}
                />
            )}
        </Card>
    );
}

const COLORS = {
    rose: { bd: "border-rose-300", bg: "bg-rose-50", tx: "text-rose-700", ic: "text-rose-500" },
    amber: { bd: "border-amber-300", bg: "bg-amber-50", tx: "text-amber-700", ic: "text-amber-500" },
    orange: { bd: "border-orange-300", bg: "bg-orange-50", tx: "text-orange-700", ic: "text-orange-500" },
};

function CardMissing({ label, count, icon: Icon, color, onClick, testid }) {
    const c = COLORS[color];
    const dis = count === 0;
    return (
        <button onClick={onClick} disabled={dis} data-testid={testid}
            className={`text-left p-3 rounded border-2 transition-all w-full ${
                dis ? "border-emerald-200 bg-emerald-50 cursor-default opacity-80"
                    : `${c.bd} ${c.bg} hover:shadow-md cursor-pointer hover:scale-[1.02]`
            }`}>
            <div className="flex items-center justify-between">
                <div>
                    <div className={`text-[10px] uppercase tracking-wider ${dis ? "text-emerald-700" : c.tx}`}>{label}</div>
                    <div className={`text-3xl font-bold font-mono ${dis ? "text-emerald-600" : c.tx}`}>
                        {dis ? "✓" : count}
                    </div>
                    <div className="text-[10px] text-slate-500 mt-0.5">
                        {dis ? "Tutto in regola" : "Clicca per vedere"}
                    </div>
                </div>
                <Icon size={28} className={dis ? "text-emerald-500" : c.ic} />
            </div>
        </button>
    );
}


function ItemRow({ id, tipo, primary, secondary, badge, icon: Icon, colorClass, note, onSaveNote, onAttach, uploading }) {
    const [showNote, setShowNote] = useState(false);
    const [noteVal, setNoteVal] = useState(note || "");
    const fileRef = useRef(null);
    const linkTo = tipo === "anagrafica" ? `/anagrafiche/${id}` : `/polizze/${id}`;

    const handleSave = async () => {
        await onSaveNote(id, tipo === "anagrafica" ? "anagrafica" : "polizza", noteVal);
        setShowNote(false);
    };

    const handleFilePick = (e) => {
        const f = e.target.files?.[0];
        if (f) onAttach(id, tipo, f);
        e.target.value = "";
    };

    return (
        <div className="border-b border-slate-100 last:border-0" data-testid={`missing-item-${id}`}>
            <div className="flex items-center gap-2 p-2 group">
                <Icon size={14} className={`${colorClass} shrink-0`} />
                <Link to={linkTo} className="flex-1 min-w-0 hover:underline">
                    <div className="font-medium text-sm">{primary}</div>
                    <div className="text-[11px] text-slate-500 truncate">{secondary}</div>
                </Link>
                {badge && <span className="text-[10px] font-mono bg-sky-50 text-sky-700 px-1.5 py-0.5 rounded">{badge}</span>}
                <Button
                    size="sm" variant="ghost" className="h-7 px-2 text-xs"
                    onClick={() => fileRef.current?.click()}
                    disabled={uploading}
                    data-testid={`missing-attach-${id}`}
                    title="Allega documento"
                >
                    {uploading ? <Loader2 size={12} className="animate-spin" /> : <Paperclip size={12} />}
                </Button>
                <input type="file" ref={fileRef} onChange={handleFilePick} className="hidden"
                    accept=".pdf,.jpg,.jpeg,.png,.heic,.webp,.doc,.docx" />
                <Button
                    size="sm" variant="ghost" className={`h-7 px-2 text-xs ${note ? "text-amber-700" : "text-slate-500"}`}
                    onClick={() => setShowNote((v) => !v)}
                    data-testid={`missing-note-btn-${id}`}
                    title={note ? "Modifica nota" : "Aggiungi nota"}
                >
                    <StickyNote size={12} />
                </Button>
                <ChevronRight size={14} className="text-slate-300 group-hover:text-slate-600" />
            </div>
            {showNote && (
                <div className="p-2 pl-8 bg-slate-50 border-t border-slate-200 flex gap-2 items-start">
                    <textarea
                        value={noteVal}
                        onChange={(e) => setNoteVal(e.target.value)}
                        placeholder="Nota interna / sollecito (es. Chiamare venerdì, inviato mail 12/07)..."
                        className="flex-1 text-xs border border-slate-300 rounded p-1.5 min-h-[60px]"
                        data-testid={`missing-note-input-${id}`}
                    />
                    <div className="flex flex-col gap-1">
                        <Button size="sm" onClick={handleSave} className="h-7 text-xs bg-amber-600 hover:bg-amber-700"
                            data-testid={`missing-note-save-${id}`}>
                            <CheckCircle2 size={11} className="mr-1" /> Salva
                        </Button>
                        <Button size="sm" variant="outline" onClick={() => setShowNote(false)} className="h-7 text-xs">
                            Annulla
                        </Button>
                    </div>
                </div>
            )}
            {note && !showNote && (
                <div className="px-8 pb-1 text-[10px] text-amber-700 bg-amber-50/50 flex items-start gap-1 border-l-2 border-amber-300 ml-4">
                    <StickyNote size={10} className="shrink-0 mt-0.5" />
                    <span className="italic">{note}</span>
                </div>
            )}
        </div>
    );
}


function ListaMancantiDialog({ tipo, data, collNome, note, setNote, onReload, onClose }) {
    const [q, setQ] = useState("");
    const [uploadingId, setUploadingId] = useState(null);

    // Save nota
    const saveNota = async (entitaId, entitaTipo, nota) => {
        try {
            await api.post("/insights/documenti-mancanti/note", {
                entita_tipo: entitaTipo, entita_id: entitaId, nota,
            });
            setNote((prev) => ({ ...prev, [entitaId]: nota }));
            toast.success("Nota salvata");
        } catch { toast.error("Errore salvataggio nota"); }
    };

    // Upload allegato inline
    const attachFile = async (entitaId, entitaTipo, file) => {
        setUploadingId(entitaId);
        try {
            const fd = new FormData();
            fd.append("file", file);
            const isVeicolo = entitaTipo === "veicoli";
            const categoria = isVeicolo ? "libretto_circolazione"
                : entitaTipo === "anagrafiche" ? "documento_identita"
                : "polizza";
            const et = entitaTipo === "anagrafiche" ? "anagrafica" : "polizza";
            await api.post("/allegati", fd, {
                params: { entita_tipo: et, entita_id: entitaId, categoria,
                    descrizione: `Caricato da widget Documenti Mancanti (${categoria})` },
                headers: { "Content-Type": "multipart/form-data" },
            });
            toast.success(`Documento caricato — ${file.name}`);
            onReload();
        } catch (e) {
            toast.error(e.response?.data?.detail || "Errore upload");
        } finally { setUploadingId(null); }
    };

    let items = [], title = "", renderRow = null, colonneCSV = [];

    if (tipo === "polizze") {
        items = data.polizze_senza_allegato || [];
        title = "Polizze senza PDF/contratto allegato";
        colonneCSV = [
            ["Numero polizza", (p) => p.numero_polizza],
            ["Ramo", (p) => p.ramo], ["Prodotto", (p) => p.prodotto || ""],
            ["Contraente", (p) => p.contraente_nome || ""],
            ["Targa", (p) => p.targa || ""], ["Scadenza", (p) => p.scadenza || ""],
            ["Nota", (p) => note[p.id] || ""],
        ];
        renderRow = (p) => (
            <ItemRow
                key={p.id} id={p.id} tipo="polizze"
                primary={`N. ${p.numero_polizza} · ${p.ramo}${p.prodotto ? ` · ${p.prodotto}` : ""}`}
                secondary={`${p.contraente_nome}${p.targa ? ` · [${p.targa}]` : ""}`}
                badge={p.scadenza}
                icon={FileWarning} colorClass="text-rose-500"
                note={note[p.id]}
                onSaveNote={saveNota} onAttach={attachFile}
                uploading={uploadingId === p.id}
            />
        );
    } else if (tipo === "veicoli") {
        items = data.veicoli_senza_libretto || [];
        title = "Polizze veicolo senza libretto di circolazione";
        colonneCSV = [
            ["Targa", (v) => v.targa], ["Marca", (v) => v.veicolo_marca || ""],
            ["Modello", (v) => v.veicolo_modello || ""],
            ["Numero polizza", (v) => v.numero_polizza],
            ["Contraente", (v) => v.contraente_nome || ""],
            ["Nota", (v) => note[v.id] || ""],
        ];
        renderRow = (v) => (
            <ItemRow
                key={v.id} id={v.id} tipo="veicoli"
                primary={`[${v.targa}] ${v.veicolo_marca || ""} ${v.veicolo_modello || ""}`.trim()}
                secondary={`N. ${v.numero_polizza} · ${v.contraente_nome}`}
                icon={Car} colorClass="text-amber-500"
                note={note[v.id]}
                onSaveNote={saveNota} onAttach={attachFile}
                uploading={uploadingId === v.id}
            />
        );
    } else {
        items = data.anagrafiche_senza_ci || [];
        title = "Anagrafiche senza carta d'identità/patente";
        colonneCSV = [
            ["Cognome/Ragione", (a) => a.cognome || a.ragione_sociale || ""],
            ["Nome", (a) => a.nome || ""],
            ["Cellulare", (a) => a.cellulare || ""],
            ["Email", (a) => a.email || ""],
            ["Nota", (a) => note[a.id] || ""],
        ];
        renderRow = (a) => (
            <ItemRow
                key={a.id} id={a.id} tipo="anagrafiche"
                primary={a.ragione_sociale || `${a.cognome || ""} ${a.nome || ""}`.trim()}
                secondary={[a.cellulare && `📱 ${a.cellulare}`, a.email && `✉ ${a.email}`].filter(Boolean).join(" · ")}
                icon={IdCard} colorClass="text-orange-500"
                note={note[a.id]}
                onSaveNote={saveNota} onAttach={attachFile}
                uploading={uploadingId === a.id}
            />
        );
    }

    const filtered = q.trim()
        ? items.filter((x) => JSON.stringify(x).toLowerCase().includes(q.toLowerCase()))
        : items;

    const stampa = () => window.print();
    const esportaExcel = () => {
        const headers = colonneCSV.map(([h]) => `"${h}"`).join(";");
        const rows = filtered.map((it) =>
            colonneCSV.map(([, f]) => `"${String(f(it) ?? "").replace(/"/g, '""')}"`).join(";")
        );
        const csv = "\ufeff" + [headers, ...rows].join("\n");
        const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
        const a = document.createElement("a");
        a.href = URL.createObjectURL(blob);
        a.download = `documenti-mancanti-${tipo}-${new Date().toISOString().slice(0, 10)}.csv`;
        a.click();
    };

    return (
        <Dialog open onOpenChange={(o) => !o && onClose()}>
            <DialogContent className="max-w-3xl" data-testid={`missing-dialog-${tipo}`}>
                <DialogHeader>
                    <DialogTitle className="flex items-center justify-between">
                        <span>
                            {title} <span className="text-sm text-slate-500 font-normal">({items.length})</span>
                            {collNome && <span className="text-xs text-sky-700 font-normal ml-2">· filtro: {collNome}</span>}
                        </span>
                        <button onClick={onClose}><X size={16} /></button>
                    </DialogTitle>
                </DialogHeader>
                <div className="flex items-center gap-2 print:hidden">
                    <Input value={q} onChange={(e) => setQ(e.target.value)}
                        placeholder="Cerca…" className="flex-1" data-testid="missing-search" />
                    <Button size="sm" variant="outline" onClick={stampa} data-testid="missing-print">
                        <Printer size={13} className="mr-1" /> Stampa
                    </Button>
                    <Button size="sm" variant="outline" onClick={esportaExcel}
                        className="border-emerald-300 text-emerald-700 hover:bg-emerald-50" data-testid="missing-excel">
                        <FileSpreadsheet size={13} className="mr-1" /> Excel
                    </Button>
                </div>
                <div className="border border-slate-200 rounded max-h-[65vh] overflow-y-auto print:max-h-none print:border-none mt-2">
                    {filtered.length === 0 ? (
                        <div className="p-8 text-center text-slate-400 text-sm">Nessun risultato</div>
                    ) : filtered.map(renderRow)}
                </div>
                <div className="text-[11px] text-slate-500 mt-2 print:hidden">
                    💡 <b>Attiva</b>: usa <Paperclip size={11} className="inline" /> per allegare direttamente | <StickyNote size={11} className="inline" /> per annotare uno sollecito
                </div>
            </DialogContent>
        </Dialog>
    );
}
