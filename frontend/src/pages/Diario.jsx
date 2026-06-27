/**
 * Diario collaboratore — feed personale con:
 *  • Comunicazioni inviate dal programma (email/sms/whatsapp) registrate
 *    automaticamente in `storico_avvisi`
 *  • Messaggi di chat inviati dall'utente
 *  • Note personali libere (create manualmente)
 *
 * Filtri: tipo, ricerca testuale.
 */
import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
    Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { Mail, MessageSquare, Phone, FileText, Trash2, Plus, Filter, Search } from "lucide-react";
import { toast } from "sonner";

const TIPI = [
    { v: "all", l: "Tutti", icon: <Filter size={12} /> },
    { v: "nota", l: "Note", icon: <FileText size={12} /> },
    { v: "email", l: "Email", icon: <Mail size={12} /> },
    { v: "sms", l: "SMS", icon: <Phone size={12} /> },
    { v: "whatsapp", l: "WhatsApp", icon: <Phone size={12} /> },
    { v: "chat", l: "Chat", icon: <MessageSquare size={12} /> },
];

const ICONA = {
    nota: <FileText size={14} className="text-amber-600" />,
    email: <Mail size={14} className="text-sky-600" />,
    sms: <Phone size={14} className="text-emerald-600" />,
    whatsapp: <Phone size={14} className="text-emerald-700" />,
    chat: <MessageSquare size={14} className="text-violet-600" />,
};

const fmtDate = (iso) => {
    if (!iso) return "—";
    try {
        const d = new Date(iso);
        return d.toLocaleString("it-IT", { dateStyle: "short", timeStyle: "short" });
    } catch { return iso; }
};

export default function Diario() {
    const [items, setItems] = useState(null);
    const [filtro, setFiltro] = useState("all");
    const [q, setQ] = useState("");
    const [openNew, setOpenNew] = useState(false);

    const load = async () => {
        const params = {};
        if (filtro !== "all") params.tipo = filtro;
        if (q.trim()) params.q = q.trim();
        try {
            const r = await api.get("/diario", { params });
            setItems(r.data || []);
        } catch (e) {
            toast.error(e.response?.data?.detail || "Errore caricamento");
        }
    };
    useEffect(() => { load(); /* eslint-disable-next-line */ }, [filtro]);

    const cerca = (e) => { e?.preventDefault?.(); load(); };

    const elimina = async (it) => {
        if (it.tipo !== "nota") { toast.info("Solo le note libere si possono eliminare dal diario"); return; }
        if (!window.confirm("Eliminare questa nota?")) return;
        try {
            await api.delete(`/diario/${it.id}`);
            toast.success("Nota eliminata");
            load();
        } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
    };

    const totali = useMemo(() => {
        const c = { nota: 0, email: 0, sms: 0, whatsapp: 0, chat: 0 };
        (items || []).forEach((it) => { if (c[it.tipo] != null) c[it.tipo] += 1; });
        return c;
    }, [items]);

    return (
        <div className="space-y-4">
            <div className="flex flex-wrap items-end justify-between gap-3">
                <div>
                    <h1 className="text-2xl font-semibold text-slate-900">Diario personale</h1>
                    <p className="text-sm text-slate-500">
                        Tutte le comunicazioni inviate dal programma, le chat e le tue note. Non perdi nulla.
                    </p>
                </div>
                <Button onClick={() => setOpenNew(true)} className="bg-amber-500 hover:bg-amber-600"
                    data-testid="diario-new-btn">
                    <Plus size={14} className="mr-1" /> Nuova nota
                </Button>
            </div>

            {/* Filtri */}
            <Card className="p-3 border-slate-200 flex flex-wrap items-center gap-2">
                {TIPI.map((t) => (
                    <button
                        key={t.v}
                        onClick={() => setFiltro(t.v)}
                        className={`px-3 py-1.5 text-xs font-medium rounded-md inline-flex items-center gap-1.5 transition-colors ${
                            filtro === t.v ? "bg-sky-700 text-white" : "bg-slate-100 text-slate-700 hover:bg-slate-200"
                        }`}
                        data-testid={`diario-filter-${t.v}`}
                    >
                        {t.icon}
                        {t.l}
                        {t.v !== "all" && totali[t.v] != null && (
                            <span className={`ml-1 px-1.5 rounded text-[10px] font-semibold ${
                                filtro === t.v ? "bg-white/30" : "bg-slate-200"
                            }`}>{totali[t.v]}</span>
                        )}
                    </button>
                ))}
                <form onSubmit={cerca} className="flex items-center gap-2 ml-auto">
                    <div className="relative">
                        <Search size={12} className="absolute left-2 top-1/2 -translate-y-1/2 text-slate-400" />
                        <Input
                            placeholder="Cerca testo, destinatario, contraente…"
                            value={q}
                            onChange={(e) => setQ(e.target.value)}
                            className="pl-7 h-8 w-64 text-xs"
                            data-testid="diario-q"
                        />
                    </div>
                    <Button type="submit" size="sm" variant="outline" data-testid="diario-search-btn">Cerca</Button>
                </form>
            </Card>

            {/* Lista */}
            <Card className="border-slate-200 divide-y divide-slate-100">
                {items === null && <div className="p-6 text-slate-500 text-sm">Caricamento…</div>}
                {items && items.length === 0 && (
                    <div className="p-6 text-slate-500 text-sm text-center">
                        Nessuna voce nel diario. Le comunicazioni che invierai (email, SMS, WhatsApp, chat) appariranno qui automaticamente.
                    </div>
                )}
                {items && items.map((it) => (
                    <div key={`${it.tipo}-${it.id}`}
                        className="p-3 hover:bg-slate-50/60 flex items-start gap-3"
                        data-testid={`diario-item-${it.id}`}>
                        <div className="mt-0.5">{ICONA[it.tipo] || ICONA.nota}</div>
                        <div className="flex-1 min-w-0">
                            <div className="flex items-center justify-between gap-2">
                                <div className="font-medium text-slate-800 text-sm truncate">{it.titolo}</div>
                                <div className="text-[10px] text-slate-400 whitespace-nowrap">{fmtDate(it.at)}</div>
                            </div>
                            {it.contenuto && (
                                <div className="text-xs text-slate-600 mt-0.5 whitespace-pre-wrap line-clamp-3">{it.contenuto}</div>
                            )}
                            {it.tags?.length > 0 && (
                                <div className="mt-1 flex flex-wrap gap-1">
                                    {it.tags.map((t) => (
                                        <span key={t} className="text-[10px] px-1.5 py-0.5 rounded bg-slate-100 text-slate-600">#{t}</span>
                                    ))}
                                </div>
                            )}
                        </div>
                        {it.tipo === "nota" && (
                            <Button size="sm" variant="ghost" onClick={() => elimina(it)}
                                className="text-slate-400 hover:text-rose-600 h-7"
                                data-testid={`diario-del-${it.id}`}>
                                <Trash2 size={12} />
                            </Button>
                        )}
                    </div>
                ))}
            </Card>

            {openNew && <NuovaNotaDialog onClose={() => { setOpenNew(false); load(); }} />}
        </div>
    );
}

function NuovaNotaDialog({ onClose }) {
    const [titolo, setTitolo] = useState("");
    const [contenuto, setContenuto] = useState("");
    const [tags, setTags] = useState("");
    const [saving, setSaving] = useState(false);

    const salva = async () => {
        if (!titolo.trim()) { toast.error("Titolo obbligatorio"); return; }
        setSaving(true);
        try {
            await api.post("/diario", {
                titolo, contenuto: contenuto || null,
                tags: tags.split(",").map((s) => s.trim()).filter(Boolean),
            });
            toast.success("Nota salvata");
            onClose();
        } catch (e) {
            toast.error(e.response?.data?.detail || "Errore");
        }
        setSaving(false);
    };

    return (
        <Dialog open onOpenChange={onClose}>
            <DialogContent className="max-w-lg" data-testid="diario-dialog-new">
                <DialogHeader>
                    <DialogTitle>Nuova nota diario</DialogTitle>
                </DialogHeader>
                <div className="space-y-3 py-2">
                    <div>
                        <Label>Titolo *</Label>
                        <Input value={titolo} onChange={(e) => setTitolo(e.target.value)}
                            data-testid="diario-titolo" />
                    </div>
                    <div>
                        <Label>Contenuto</Label>
                        <textarea
                            rows={5}
                            className="w-full border border-slate-300 rounded-md px-3 py-2 text-sm"
                            value={contenuto}
                            onChange={(e) => setContenuto(e.target.value)}
                            data-testid="diario-contenuto"
                        />
                    </div>
                    <div>
                        <Label>Tag (separati da virgola)</Label>
                        <Input placeholder="cliente, scadenza, contatto"
                            value={tags} onChange={(e) => setTags(e.target.value)}
                            data-testid="diario-tags" />
                    </div>
                </div>
                <DialogFooter>
                    <Button variant="outline" onClick={onClose}>Annulla</Button>
                    <Button onClick={salva} disabled={saving} className="bg-amber-500 hover:bg-amber-600"
                        data-testid="diario-salva">
                        {saving ? "Salvataggio…" : "Salva nota"}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}
