import { useEffect, useState, useRef } from "react";
import { api, fmtDate } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
    Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from "@/components/ui/dialog";
import { Plus, Upload, Pencil, Trash2, Users, Search } from "lucide-react";
import { toast } from "sonner";

const EMPTY = { cognome: "", nome: "", ditta: "", data_entrata: "", data_uscita: "", codice_fiscale: "", note: "" };

export default function AssicuratiTab({ polizzaId }) {
    const [rows, setRows] = useState([]);
    const [stats, setStats] = useState(null);
    const [q, setQ] = useState("");
    const [editing, setEditing] = useState(null); // {…} or {new:true}
    const [importing, setImporting] = useState(false);
    const fileRef = useRef(null);

    const load = () => {
        api.get(`/polizze/${polizzaId}/assicurati`).then((r) => setRows(r.data || []));
        api.get(`/polizze/${polizzaId}/assicurati/stats`).then((r) => setStats(r.data));
    };
    useEffect(() => { load(); /* eslint-disable-next-line */ }, [polizzaId]);

    const save = async () => {
        if (!editing.cognome?.trim()) { toast.error("Il cognome è obbligatorio"); return; }
        try {
            if (editing.id) await api.put(`/assicurati/${editing.id}`, editing);
            else await api.post(`/polizze/${polizzaId}/assicurati`, editing);
            toast.success("Salvato");
            setEditing(null); load();
        } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
    };

    const del = async (id) => {
        if (!window.confirm("Eliminare questo assicurato dall'elenco?")) return;
        try { await api.delete(`/assicurati/${id}`); toast.success("Eliminato"); load(); }
        catch { toast.error("Errore"); }
    };

    const doImport = async (e, sostituisci) => {
        const f = e.target.files?.[0];
        if (!f) return;
        setImporting(true);
        try {
            const fd = new FormData();
            fd.append("file", f);
            fd.append("sostituisci", sostituisci ? "true" : "false");
            const r = await api.post(`/polizze/${polizzaId}/assicurati/import`, fd, {
                headers: { "Content-Type": "multipart/form-data" },
            });
            toast.success(`Importati ${r.data.creati} assicurati`);
            load();
        } catch (err) { toast.error(err.response?.data?.detail || "Errore import"); }
        finally { setImporting(false); if (fileRef.current) fileRef.current.value = ""; }
    };

    const filtered = rows.filter((r) => {
        if (!q) return true;
        const s = `${r.cognome} ${r.nome} ${r.ditta || ""} ${r.codice_fiscale || ""}`.toLowerCase();
        return s.includes(q.toLowerCase());
    });

    return (
        <div className="py-3" data-testid="assicurati-tab">
            <div className="flex items-center justify-between flex-wrap gap-2 mb-3">
                <div className="flex items-center gap-3">
                    <div className="flex items-center gap-1.5 text-slate-700 font-semibold"><Users size={16} className="text-teal-600" /> Elenco assicurati</div>
                    {stats && (
                        <div className="flex gap-2 text-xs">
                            <span className="px-2 py-0.5 rounded-full bg-slate-100 text-slate-600">Totale {stats.totale}</span>
                            <span className="px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-700">Attivi {stats.attivi}</span>
                            <span className="px-2 py-0.5 rounded-full bg-slate-200 text-slate-500">Usciti {stats.usciti}</span>
                        </div>
                    )}
                </div>
                <div className="flex items-center gap-2">
                    <div className="relative">
                        <Search size={13} className="absolute left-2 top-1/2 -translate-y-1/2 text-slate-400" />
                        <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Cerca…" className="h-8 pl-7 w-40" data-testid="assicurati-search" />
                    </div>
                    <input ref={fileRef} type="file" accept=".xlsx,.xls,.csv" className="hidden"
                        onChange={(e) => doImport(e, rows.length > 0 && window.confirm("Sostituire l'elenco esistente? (Annulla = aggiungi)"))} />
                    <Button size="sm" variant="outline" disabled={importing} onClick={() => fileRef.current?.click()} data-testid="assicurati-import-btn">
                        <Upload size={14} className="mr-1" /> {importing ? "Import…" : "Importa Excel"}
                    </Button>
                    <Button size="sm" className="bg-teal-700 hover:bg-teal-800" onClick={() => setEditing({ ...EMPTY })} data-testid="assicurati-add-btn">
                        <Plus size={14} className="mr-1" /> Aggiungi
                    </Button>
                </div>
            </div>

            <div className="border border-slate-200 rounded-lg overflow-hidden overflow-x-auto">
                <table className="w-full text-sm">
                    <thead className="bg-slate-50 text-left text-xs text-slate-500 uppercase tracking-wide border-b border-slate-200">
                        <tr>
                            <th className="px-3 py-2 w-12">#</th>
                            <th className="px-3 py-2">Cognome</th>
                            <th className="px-3 py-2">Nome</th>
                            <th className="px-3 py-2">Ditta</th>
                            <th className="px-3 py-2">Entrata</th>
                            <th className="px-3 py-2">Uscita</th>
                            <th className="px-3 py-2">Stato</th>
                            <th className="px-3 py-2 text-right">Azioni</th>
                        </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                        {filtered.length === 0 && (
                            <tr><td colSpan={8} className="px-3 py-8 text-center text-slate-400 italic">Nessun assicurato. Aggiungi manualmente o importa un Excel.</td></tr>
                        )}
                        {filtered.map((r) => (
                            <tr key={r.id} className={r.stato === "uscito" ? "bg-slate-50/60 text-slate-400" : ""} data-testid={`assicurato-row-${r.id}`}>
                                <td className="px-3 py-2 text-slate-400 font-mono text-xs">{r.numero}</td>
                                <td className="px-3 py-2 font-medium text-slate-800">{r.cognome}</td>
                                <td className="px-3 py-2">{r.nome || "—"}</td>
                                <td className="px-3 py-2 text-slate-600">{r.ditta || "—"}</td>
                                <td className="px-3 py-2">{fmtDate(r.data_entrata) || "—"}</td>
                                <td className="px-3 py-2">{fmtDate(r.data_uscita) || "—"}</td>
                                <td className="px-3 py-2">
                                    <span className={`inline-block px-2 py-0.5 rounded-full text-[11px] font-medium ${r.stato === "attivo" ? "bg-emerald-100 text-emerald-700" : "bg-slate-200 text-slate-500"}`}>{r.stato}</span>
                                </td>
                                <td className="px-3 py-2">
                                    <div className="flex items-center justify-end gap-1">
                                        <Button size="sm" variant="ghost" className="h-7 px-2" onClick={() => setEditing({ ...r, data_entrata: r.data_entrata || "", data_uscita: r.data_uscita || "" })} data-testid={`assicurato-edit-${r.id}`}><Pencil size={13} /></Button>
                                        <Button size="sm" variant="ghost" className="h-7 px-2 text-rose-600" onClick={() => del(r.id)} data-testid={`assicurato-del-${r.id}`}><Trash2 size={13} /></Button>
                                    </div>
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>

            {editing && (
                <Dialog open onOpenChange={(o) => !o && setEditing(null)}>
                    <DialogContent className="max-w-lg" data-testid="assicurato-dialog">
                        <DialogHeader><DialogTitle>{editing.id ? "Modifica assicurato" : "Nuovo assicurato"}</DialogTitle></DialogHeader>
                        <div className="grid grid-cols-2 gap-3 py-2">
                            <div><Label className="text-xs">Cognome *</Label><Input value={editing.cognome} onChange={(e) => setEditing({ ...editing, cognome: e.target.value })} data-testid="assicurato-cognome" /></div>
                            <div><Label className="text-xs">Nome</Label><Input value={editing.nome} onChange={(e) => setEditing({ ...editing, nome: e.target.value })} data-testid="assicurato-nome" /></div>
                            <div className="col-span-2"><Label className="text-xs">Ditta</Label><Input value={editing.ditta} onChange={(e) => setEditing({ ...editing, ditta: e.target.value })} data-testid="assicurato-ditta" /></div>
                            <div><Label className="text-xs">Data entrata</Label><Input type="date" value={editing.data_entrata || ""} onChange={(e) => setEditing({ ...editing, data_entrata: e.target.value })} data-testid="assicurato-entrata" /></div>
                            <div><Label className="text-xs">Data uscita</Label><Input type="date" value={editing.data_uscita || ""} onChange={(e) => setEditing({ ...editing, data_uscita: e.target.value })} data-testid="assicurato-uscita" /></div>
                            <div className="col-span-2"><Label className="text-xs">Codice fiscale</Label><Input value={editing.codice_fiscale || ""} onChange={(e) => setEditing({ ...editing, codice_fiscale: e.target.value.toUpperCase() })} data-testid="assicurato-cf" /></div>
                        </div>
                        <DialogFooter>
                            <Button variant="outline" onClick={() => setEditing(null)}>Annulla</Button>
                            <Button className="bg-teal-700 hover:bg-teal-800" onClick={save} data-testid="assicurato-save">Salva</Button>
                        </DialogFooter>
                    </DialogContent>
                </Dialog>
            )}
        </div>
    );
}
