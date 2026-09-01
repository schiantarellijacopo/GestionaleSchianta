/**
 * Notebook AI — elenco dei notebook (stile NotebookLM).
 */
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, formatError } from "@/lib/api";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Loading, PageHeader } from "@/components/Shared";
import { Sparkles, Plus, FileText, Trash2, ChevronRight } from "lucide-react";
import { toast } from "sonner";

export default function NotebookAI() {
    const navigate = useNavigate();
    const [items, setItems] = useState(null);
    const [open, setOpen] = useState(false);
    const [titolo, setTitolo] = useState("");
    const [descrizione, setDescrizione] = useState("");
    const [creating, setCreating] = useState(false);

    const load = () => api.get("/notebooklm/notebooks").then((r) => setItems(r.data || []));
    useEffect(() => { load(); }, []);

    const crea = async () => {
        if (!titolo.trim()) return;
        setCreating(true);
        try {
            const r = await api.post("/notebooklm/notebooks", { titolo, descrizione });
            setOpen(false); setTitolo(""); setDescrizione("");
            navigate(`/notebook-ai/${r.data.id}`);
        } catch (e) { toast.error(formatError(e)); }
        finally { setCreating(false); }
    };

    const elimina = async (nb, e) => {
        e.stopPropagation();
        if (!window.confirm(`Eliminare il notebook "${nb.titolo}" con tutte le fonti e gli output?`)) return;
        try {
            await api.delete(`/notebooklm/notebooks/${nb.id}`);
            toast.success("Notebook eliminato");
            load();
        } catch (e2) { toast.error(formatError(e2)); }
    };

    if (items === null) return <Loading />;

    return (
        <div data-testid="notebook-ai-page" className="space-y-4">
            <PageHeader
                title={<span className="flex items-center gap-2"><Sparkles className="text-teal-600" /> Notebook AI</span>}
                subtitle="Carica condizioni di polizza, preventivi e normative — chatta con i documenti, genera riassunti e podcast"
                actions={
                    <Button onClick={() => setOpen(true)} className="bg-teal-600 hover:bg-teal-700" data-testid="nb-create-btn">
                        <Plus size={14} className="mr-1" /> Nuovo notebook
                    </Button>
                }
            />

            {items.length === 0 ? (
                <Card className="p-12 text-center" data-testid="nb-empty-state">
                    <Sparkles size={48} className="mx-auto text-teal-300 mb-3" />
                    <div className="font-semibold text-slate-700 mb-1">Nessun notebook ancora</div>
                    <div className="text-sm text-slate-500 mb-4">
                        Crea un notebook tematico (es. "RC Auto 2026", "Confronto polizze casa") e carica i documenti.
                    </div>
                    <Button onClick={() => setOpen(true)} variant="outline" data-testid="nb-empty-create-btn">
                        <Plus size={14} className="mr-1" /> Crea il primo notebook
                    </Button>
                </Card>
            ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                    {items.map((nb) => (
                        <Card key={nb.id}
                              onClick={() => navigate(`/notebook-ai/${nb.id}`)}
                              className="p-4 cursor-pointer hover:shadow-md hover:border-teal-300 transition-all group"
                              data-testid={`nb-card-${nb.id}`}>
                            <div className="flex items-start justify-between gap-2">
                                <div className="w-9 h-9 rounded-lg bg-teal-50 border border-teal-200 flex items-center justify-center shrink-0">
                                    <Sparkles size={16} className="text-teal-600" />
                                </div>
                                <button onClick={(e) => elimina(nb, e)}
                                        className="opacity-0 group-hover:opacity-100 text-slate-400 hover:text-rose-600 transition-opacity"
                                        data-testid={`nb-del-${nb.id}`}>
                                    <Trash2 size={14} />
                                </button>
                            </div>
                            <div className="font-semibold text-slate-800 mt-2 truncate">{nb.titolo}</div>
                            {nb.descrizione && <div className="text-xs text-slate-500 mt-0.5 line-clamp-2">{nb.descrizione}</div>}
                            <div className="flex items-center justify-between mt-3 text-[11px] text-slate-500">
                                <span className="flex items-center gap-1">
                                    <FileText size={11} /> {nb.n_fonti} font{nb.n_fonti === 1 ? "e" : "i"}
                                </span>
                                <span className="flex items-center gap-0.5 text-teal-600 font-medium">
                                    Apri <ChevronRight size={12} />
                                </span>
                            </div>
                        </Card>
                    ))}
                </div>
            )}

            <Dialog open={open} onOpenChange={setOpen}>
                <DialogContent data-testid="nb-create-dialog">
                    <DialogHeader><DialogTitle>Nuovo notebook</DialogTitle></DialogHeader>
                    <div className="space-y-3">
                        <Input value={titolo} onChange={(e) => setTitolo(e.target.value)}
                               placeholder='Titolo — es. "Confronto RC Auto 2026"' autoFocus
                               data-testid="nb-titolo-input" />
                        <Textarea value={descrizione} onChange={(e) => setDescrizione(e.target.value)}
                                  placeholder="Descrizione (opzionale)" rows={2}
                                  data-testid="nb-descrizione-input" />
                        <div className="flex justify-end gap-2">
                            <Button variant="outline" onClick={() => setOpen(false)}>Annulla</Button>
                            <Button onClick={crea} disabled={creating || !titolo.trim()}
                                    className="bg-teal-600 hover:bg-teal-700" data-testid="nb-create-confirm">
                                {creating ? "Creazione…" : "Crea"}
                            </Button>
                        </div>
                    </div>
                </DialogContent>
            </Dialog>
        </div>
    );
}
