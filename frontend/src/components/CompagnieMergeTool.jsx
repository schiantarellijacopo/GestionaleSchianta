import { useState } from "react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import {
    Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogTrigger,
} from "@/components/ui/dialog";
import { toast } from "sonner";
import { Merge, Image as ImageIcon } from "lucide-react";

/**
 * Strumento per UNIRE compagnie duplicate (es. le UCA create in automatico dall'OCR).
 * Tutte le polizze/titoli/movimenti/schemi provvigionali delle compagnie selezionate
 * vengono riassegnate alla compagnia di destinazione; le duplicate vengono eliminate.
 */
export default function CompagnieMergeTool({ list = [] }) {
    const [open, setOpen] = useState(false);
    const [targetId, setTargetId] = useState("");
    const [sources, setSources] = useState(new Set());
    const [busy, setBusy] = useState(false);
    const [migrando, setMigrando] = useState(false);

    const migraLoghi = async () => {
        setMigrando(true);
        try {
            const r = await api.post("/compagnie/migra-loghi");
            const d = r.data || {};
            toast.success(`Loghi: ${d.migrati} recuperati · ${d.gia_nel_db} già ok · ${d.falliti} non recuperabili`);
            if (d.migrati > 0) setTimeout(() => window.location.reload(), 1000);
            else if (d.falliti > 0) toast.message("I loghi non recuperabili vanno ricaricati manualmente.");
        } catch (e) {
            toast.error(e.response?.data?.detail || "Errore migrazione loghi");
        } finally {
            setMigrando(false);
        }
    };

    const toggleSource = (id) => {
        setSources((prev) => {
            const n = new Set(prev);
            n.has(id) ? n.delete(id) : n.add(id);
            return n;
        });
    };

    const sorted = [...list].sort((a, b) =>
        (a.ragione_sociale || "").localeCompare(b.ragione_sociale || ""));

    const doMerge = async () => {
        const src = [...sources].filter((s) => s !== targetId);
        if (!targetId) { toast.error("Seleziona la compagnia da MANTENERE"); return; }
        if (src.length === 0) { toast.error("Seleziona almeno una compagnia duplicata da unire"); return; }
        const tgtName = list.find((c) => c.id === targetId)?.ragione_sociale;
        if (!window.confirm(`Unire ${src.length} compagnia/e in "${tgtName}"? Tutte le polizze e i movimenti verranno spostati su questa compagnia e le duplicate eliminate. Operazione non reversibile.`)) return;
        setBusy(true);
        try {
            const r = await api.post("/compagnie/unisci", { source_ids: src, target_id: targetId });
            const tot = Object.values(r.data?.riassegnati || {}).reduce((s, n) => s + n, 0);
            toast.success(`Unite ${r.data?.unite} compagnie · ${tot} riferimenti riassegnati`);
            setTimeout(() => window.location.reload(), 900);
        } catch (e) {
            toast.error(e.response?.data?.detail || "Errore nell'unione");
            setBusy(false);
        }
    };

    return (
        <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" className="gap-1" onClick={migraLoghi} disabled={migrando} data-testid="compagnie-migra-loghi">
                <ImageIcon size={14} /> {migrando ? "Migrazione…" : "Migra loghi"}
            </Button>
            <Dialog open={open} onOpenChange={(o) => { setOpen(o); if (!o) { setSources(new Set()); setTargetId(""); } }}>
            <DialogTrigger asChild>
                <Button variant="outline" size="sm" className="gap-1" data-testid="compagnie-merge-open">
                    <Merge size={14} /> Unisci duplicati
                </Button>
            </DialogTrigger>
            <DialogContent className="max-w-2xl max-h-[88vh] overflow-y-auto" data-testid="compagnie-merge-dialog">
                <DialogHeader>
                    <DialogTitle>Unisci compagnie duplicate</DialogTitle>
                </DialogHeader>
                <p className="text-xs text-slate-500 -mt-1">
                    Seleziona la compagnia da <strong>mantenere</strong> (pallino) e spunta le
                    <strong> duplicate</strong> da unirvi. Polizze, titoli, movimenti e schemi
                    provvigionali verranno spostati sulla compagnia mantenuta.
                </p>
                <div className="border border-slate-200 rounded-md divide-y max-h-[55vh] overflow-y-auto">
                    {sorted.map((c) => (
                        <div key={c.id} className="flex items-center gap-3 px-3 py-2 text-sm" data-testid={`merge-row-${c.id}`}>
                            <label className="flex items-center gap-1 cursor-pointer" title="Mantieni questa">
                                <input type="radio" name="merge-target" checked={targetId === c.id}
                                    onChange={() => setTargetId(c.id)} data-testid={`merge-target-${c.id}`} />
                                <span className="text-[10px] uppercase text-emerald-700 font-bold">tieni</span>
                            </label>
                            <label className="flex items-center gap-1 cursor-pointer ml-2" title="Unisci (duplicata)">
                                <input type="checkbox" checked={sources.has(c.id)} disabled={targetId === c.id}
                                    onChange={() => toggleSource(c.id)} data-testid={`merge-source-${c.id}`} />
                                <span className="text-[10px] uppercase text-rose-600 font-bold">unisci</span>
                            </label>
                            <span className="num text-xs text-slate-400 w-24 shrink-0">{c.codice}</span>
                            <span className="flex-1 font-medium text-slate-800">{c.ragione_sociale}</span>
                            {!c.attiva && <span className="badge badge-neutral text-[10px]">inattiva</span>}
                        </div>
                    ))}
                </div>
                <DialogFooter>
                    <Button variant="outline" onClick={() => setOpen(false)} disabled={busy}>Annulla</Button>
                    <Button onClick={doMerge} disabled={busy} className="bg-sky-700 hover:bg-sky-800" data-testid="compagnie-merge-confirm">
                        {busy ? "Unione…" : "Unisci selezionate"}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
        </div>
    );
}
