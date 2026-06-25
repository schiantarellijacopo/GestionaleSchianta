import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import { PageHeader, Loading, Empty } from "@/components/Shared";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import {
    Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from "@/components/ui/dialog";
import RowActions from "@/components/RowActions";
import { Plus, Search, BookUser, Mail, Phone, Smartphone, X } from "lucide-react";
import { useAuth } from "@/contexts/AuthContext";
import { toast } from "sonner";

const RUOLI_SUGGERITI = [
    "Direzione", "Ufficio sinistri", "Ufficio incassi", "Ufficio assuntivo",
    "Commerciale", "Ispettore", "Tecnico", "Amministrazione", "Liquidatore", "Altro",
];

export default function RubricaCompagnie() {
    const { user } = useAuth();
    const [list, setList] = useState(null);
    const [compagnie, setCompagnie] = useState([]);
    const [editing, setEditing] = useState(null);
    const [q, setQ] = useState("");
    const [filtroCompagnia, setFiltroCompagnia] = useState("all");
    const canEdit = ["admin", "collaboratore", "dipendente"].includes(user?.role);
    const canDelete = ["admin", "collaboratore"].includes(user?.role);

    const load = () => {
        const params = {};
        if (q) params.q = q;
        if (filtroCompagnia !== "all") params.compagnia_id = filtroCompagnia;
        api.get("/contatti-compagnia", { params }).then((r) => setList(r.data));
    };
    useEffect(() => { load(); /* eslint-disable-next-line */ }, [filtroCompagnia]);

    useEffect(() => {
        api.get("/compagnie").then((r) => setCompagnie(r.data || []));
    }, []);

    // Raggruppa per compagnia (per visualizzazione card)
    const grouped = useMemo(() => {
        if (!list) return [];
        const map = new Map();
        for (const c of list) {
            const k = c.compagnia_id || "altro";
            const cur = map.get(k) || {
                compagnia_id: k,
                compagnia_nome: c.compagnia_nome || "Senza compagnia",
                compagnia_codice: c.compagnia_codice,
                contatti: [],
            };
            cur.contatti.push(c);
            map.set(k, cur);
        }
        return Array.from(map.values()).sort((a, b) =>
            (a.compagnia_nome || "").localeCompare(b.compagnia_nome || ""));
    }, [list]);

    const elimina = async (id) => {
        if (!window.confirm("Eliminare definitivamente questo contatto?")) return;
        try {
            await api.delete(`/contatti-compagnia/${id}`);
            toast.success("Contatto eliminato");
            load();
        } catch (e) {
            toast.error(e.response?.data?.detail || "Errore");
        }
    };

    return (
        <div data-testid="rubrica-compagnie-page">
            <PageHeader
                title={<><BookUser className="inline mr-2 -mt-1" size={20} />Rubrica compagnie</>}
                subtitle="Persone di riferimento delle compagnie · ufficio sinistri, incassi, direzione, ispettorato"
                actions={canEdit && (
                    <Button
                        onClick={() => setEditing({ _new: true, attivo: true })}
                        className="bg-sky-700 hover:bg-sky-800"
                        data-testid="rubrica-new-btn"
                    >
                        <Plus size={16} className="mr-1" /> Nuovo contatto
                    </Button>
                )}
            />

            <div className="flex flex-wrap items-center gap-3 mb-4">
                <div className="relative">
                    <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" size={14} />
                    <Input
                        className="pl-8 w-72"
                        placeholder="Cerca nome, email, ruolo…"
                        value={q}
                        onChange={(e) => setQ(e.target.value)}
                        onKeyDown={(e) => e.key === "Enter" && load()}
                        data-testid="rubrica-search"
                    />
                </div>
                <Select value={filtroCompagnia} onValueChange={setFiltroCompagnia}>
                    <SelectTrigger className="w-64" data-testid="rubrica-filtro-compagnia">
                        <SelectValue placeholder="Compagnia" />
                    </SelectTrigger>
                    <SelectContent>
                        <SelectItem value="all">Tutte le compagnie</SelectItem>
                        {compagnie.map((c) => (
                            <SelectItem key={c.id} value={c.id}>{c.ragione_sociale}</SelectItem>
                        ))}
                    </SelectContent>
                </Select>
                <Button variant="outline" size="sm" onClick={load} data-testid="rubrica-apply-search">
                    Cerca
                </Button>
                {(q || filtroCompagnia !== "all") && (
                    <Button variant="ghost" size="sm" onClick={() => {
                        setQ(""); setFiltroCompagnia("all");
                    }}>
                        <X size={14} className="mr-1" />Reset
                    </Button>
                )}
                <div className="text-xs text-slate-500 ml-auto num">
                    {list ? `${list.length} contatti · ${grouped.length} compagnie` : ""}
                </div>
            </div>

            {list === null ? <Loading /> : list.length === 0 ? <Empty /> : (
                <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
                    {grouped.map((g) => (
                        <Card key={g.compagnia_id} className="border-slate-200 p-4" data-testid={`group-${g.compagnia_id}`}>
                            <div className="flex justify-between items-baseline border-b border-slate-100 pb-2 mb-3">
                                <div className="font-semibold text-sky-900">{g.compagnia_nome}</div>
                                <span className="text-[10px] text-slate-500 num">{g.contatti.length}</span>
                            </div>
                            <div className="space-y-3">
                                {g.contatti.map((c) => (
                                    <ContattoRow
                                        key={c.id}
                                        c={c}
                                        canEdit={canEdit}
                                        canDelete={canDelete}
                                        onEdit={() => setEditing(c)}
                                        onDelete={() => elimina(c.id)}
                                    />
                                ))}
                            </div>
                        </Card>
                    ))}
                </div>
            )}

            {editing && (
                <ContattoDialog
                    contatto={editing}
                    compagnie={compagnie}
                    onClose={() => { setEditing(null); load(); }}
                />
            )}
        </div>
    );
}

function ContattoRow({ c, canEdit, canDelete, onEdit, onDelete }) {
    const fullName = [c.nome, c.cognome].filter(Boolean).join(" ");
    const cell = c.cellulare?.replace(/[^\d+]/g, "");
    const waUrl = cell ? `https://wa.me/${cell}` : null;
    return (
        <div className="border border-slate-100 rounded-md p-2.5 hover:border-sky-200 transition-colors" data-testid={`contatto-${c.id}`}>
            <div className="flex justify-between items-start gap-2">
                <div className="min-w-0">
                    <div className="font-medium text-slate-900 truncate">{fullName || "—"}</div>
                    <div className="text-[11px] text-slate-500 truncate">
                        {c.ruolo || ""}{c.ruolo && c.ufficio ? " · " : ""}{c.ufficio || ""}
                    </div>
                </div>
                {(canEdit || canDelete) && (
                    <RowActions
                        testid={`contatto-actions-${c.id}`}
                        onEdit={canEdit ? onEdit : null}
                        onDelete={canDelete ? onDelete : null}
                        canDelete={canDelete}
                    />
                )}
            </div>
            <div className="mt-2 space-y-0.5 text-[11px]">
                {c.email && (
                    <a href={`mailto:${c.email}`} className="flex items-center gap-1.5 text-sky-700 hover:underline truncate" data-testid={`contatto-email-${c.id}`}>
                        <Mail size={11} /> {c.email}
                    </a>
                )}
                {c.telefono && (
                    <a href={`tel:${c.telefono}`} className="flex items-center gap-1.5 text-slate-700 hover:underline" data-testid={`contatto-tel-${c.id}`}>
                        <Phone size={11} /> {c.telefono}
                        {c.interno && <span className="text-slate-400">·int. {c.interno}</span>}
                    </a>
                )}
                {c.cellulare && (
                    <div className="flex items-center gap-2">
                        <a href={`tel:${c.cellulare}`} className="flex items-center gap-1.5 text-emerald-700 hover:underline" data-testid={`contatto-cell-${c.id}`}>
                            <Smartphone size={11} /> {c.cellulare}
                        </a>
                        {waUrl && (
                            <a href={waUrl} target="_blank" rel="noopener noreferrer" className="text-[10px] text-emerald-700 underline">
                                WhatsApp
                            </a>
                        )}
                    </div>
                )}
                {c.note && (
                    <div className="mt-1 text-[10px] text-slate-500 italic line-clamp-2">{c.note}</div>
                )}
            </div>
        </div>
    );
}

function ContattoDialog({ contatto, compagnie, onClose }) {
    const isNew = contatto._new;
    const [f, setF] = useState({
        compagnia_id: contatto.compagnia_id || "",
        nome: contatto.nome || "",
        cognome: contatto.cognome || "",
        ruolo: contatto.ruolo || "",
        ufficio: contatto.ufficio || "",
        email: contatto.email || "",
        telefono: contatto.telefono || "",
        cellulare: contatto.cellulare || "",
        interno: contatto.interno || "",
        note: contatto.note || "",
        attivo: contatto.attivo !== false,
    });
    const set = (k, v) => setF((p) => ({ ...p, [k]: v }));

    const save = async () => {
        if (!f.compagnia_id || !f.nome) {
            toast.error("Compagnia e Nome obbligatori");
            return;
        }
        try {
            if (isNew) {
                await api.post("/contatti-compagnia", f);
                toast.success("Contatto creato");
            } else {
                await api.put(`/contatti-compagnia/${contatto.id}`, f);
                toast.success("Contatto aggiornato");
            }
            onClose();
        } catch (e) {
            toast.error(e.response?.data?.detail || "Errore");
        }
    };

    return (
        <Dialog open onOpenChange={(o) => !o && onClose()}>
            <DialogContent className="max-w-2xl" data-testid="contatto-edit-dialog">
                <DialogHeader>
                    <DialogTitle>{isNew ? "Nuovo contatto" : "Modifica contatto"}</DialogTitle>
                </DialogHeader>
                <div className="grid grid-cols-2 gap-3 py-2">
                    <div className="col-span-2">
                        <Label>Compagnia *</Label>
                        <Select value={f.compagnia_id} onValueChange={(v) => set("compagnia_id", v)}>
                            <SelectTrigger data-testid="contatto-compagnia-select"><SelectValue placeholder="Seleziona…" /></SelectTrigger>
                            <SelectContent>
                                {compagnie.map((c) => (
                                    <SelectItem key={c.id} value={c.id}>{c.ragione_sociale}</SelectItem>
                                ))}
                            </SelectContent>
                        </Select>
                    </div>
                    <div>
                        <Label>Nome *</Label>
                        <Input value={f.nome} onChange={(e) => set("nome", e.target.value)} data-testid="contatto-nome" />
                    </div>
                    <div>
                        <Label>Cognome</Label>
                        <Input value={f.cognome} onChange={(e) => set("cognome", e.target.value)} data-testid="contatto-cognome" />
                    </div>
                    <div>
                        <Label>Ruolo</Label>
                        <Select value={f.ruolo || "_"} onValueChange={(v) => set("ruolo", v === "_" ? "" : v)}>
                            <SelectTrigger data-testid="contatto-ruolo"><SelectValue placeholder="Seleziona…" /></SelectTrigger>
                            <SelectContent>
                                <SelectItem value="_">—</SelectItem>
                                {RUOLI_SUGGERITI.map((r) => <SelectItem key={r} value={r}>{r}</SelectItem>)}
                            </SelectContent>
                        </Select>
                    </div>
                    <div>
                        <Label>Ufficio</Label>
                        <Input value={f.ufficio} onChange={(e) => set("ufficio", e.target.value)} />
                    </div>
                    <div>
                        <Label>Email</Label>
                        <Input type="email" value={f.email} onChange={(e) => set("email", e.target.value)} data-testid="contatto-email-input" />
                    </div>
                    <div>
                        <Label>Telefono</Label>
                        <Input value={f.telefono} onChange={(e) => set("telefono", e.target.value)} />
                    </div>
                    <div>
                        <Label>Cellulare</Label>
                        <Input value={f.cellulare} onChange={(e) => set("cellulare", e.target.value)} />
                    </div>
                    <div>
                        <Label>Interno</Label>
                        <Input value={f.interno} onChange={(e) => set("interno", e.target.value)} />
                    </div>
                    <div className="col-span-2">
                        <Label>Note</Label>
                        <Textarea value={f.note} onChange={(e) => set("note", e.target.value)} rows={3} />
                    </div>
                </div>
                <DialogFooter>
                    <Button variant="outline" onClick={onClose}>Annulla</Button>
                    <Button onClick={save} className="bg-sky-700 hover:bg-sky-800" data-testid="contatto-save">
                        Salva
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}
