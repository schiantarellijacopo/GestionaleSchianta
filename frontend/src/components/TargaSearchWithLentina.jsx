/**
 * TargaSearchWithLentina — Ricerca targa con autocomplete + creazione al volo.
 *
 * Props:
 *  value            targa corrente (string)
 *  onChange(targa, veicolo, polizze_collegate)   callback al select/create
 *  showVehicleData  bool - se false ritorna null (rispetta flag prodotto)
 *
 * Comportamento:
 *  - Digita >=2 caratteri: cerca in /veicoli?q=... e mostra dropdown
 *  - Click su una targa: seleziona e ritorna veicolo completo (con libretto)
 *  - Se non trova: pulsante "+ Crea Nuova Targa" apre dialog inline
 *  - Alert se la targa è già presente su altre polizze (Infortuni, Kasko, ecc.)
 */
import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import {
    Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from "@/components/ui/dialog";
import { Search, Plus, Car, X, AlertTriangle, FileText } from "lucide-react";
import { toast } from "sonner";

export default function TargaSearchWithLentina({ value, onChange, showVehicleData = true }) {
    const [q, setQ] = useState(value || "");
    const [results, setResults] = useState([]);
    const [showList, setShowList] = useState(false);
    const [loading, setLoading] = useState(false);
    const [showCreate, setShowCreate] = useState(false);
    const [linkedVeicolo, setLinkedVeicolo] = useState(null);
    const [otherPolizze, setOtherPolizze] = useState([]);
    const debounceRef = useRef(null);

    useEffect(() => { setQ(value || ""); }, [value]);

    useEffect(() => {
        if (!showVehicleData) return;
        if (debounceRef.current) clearTimeout(debounceRef.current);
        if (!q || q.length < 2) { setResults([]); return; }
        debounceRef.current = setTimeout(async () => {
            setLoading(true);
            try {
                const r = await api.get("/veicoli", { params: { q: q.toUpperCase(), limit: 8 } });
                setResults(r.data || []);
            } catch { setResults([]); }
            finally { setLoading(false); }
        }, 300);
        return () => debounceRef.current && clearTimeout(debounceRef.current);
    }, [q, showVehicleData]);

    if (!showVehicleData) return null;

    const selezionaVeicolo = async (v) => {
        try {
            const r = await api.get(`/veicoli/by-targa/${encodeURIComponent(v.targa)}`);
            const polizzeOther = r.data.polizze_collegate || [];
            setLinkedVeicolo(v);
            setOtherPolizze(polizzeOther);
            setQ(v.targa);
            setShowList(false);
            onChange(v.targa, v, polizzeOther);
            if (polizzeOther.length > 0) {
                toast.info(`Targa ${v.targa} già presente su altre ${polizzeOther.length} polizze — verifica coerenza`);
            } else {
                toast.success(`Veicolo ${v.targa} agganciato`);
            }
        } catch (e) {
            toast.error("Errore recupero veicolo");
        }
    };

    const onCreated = (nuovoVeicolo) => {
        setLinkedVeicolo(nuovoVeicolo);
        setQ(nuovoVeicolo.targa);
        setShowCreate(false);
        onChange(nuovoVeicolo.targa, nuovoVeicolo, []);
        toast.success(`Targa ${nuovoVeicolo.targa} creata e agganciata`);
    };

    return (
        <div className="relative">
            <Label>Targa <span className="text-rose-600">*</span></Label>
            <div className="relative">
                <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-400" size={14} />
                <Input
                    value={q}
                    onChange={(e) => { setQ(e.target.value.toUpperCase()); setShowList(true); if (linkedVeicolo) { setLinkedVeicolo(null); onChange(e.target.value.toUpperCase(), null, []); } }}
                    onFocus={() => setShowList(true)}
                    onBlur={() => setTimeout(() => setShowList(false), 200)}
                    placeholder="Cerca targa esistente o creane una nuova…"
                    className={`pl-8 font-mono uppercase ${linkedVeicolo ? "border-emerald-400" : ""}`}
                    data-testid="targa-search-input"
                />
                {linkedVeicolo && (
                    <span className="absolute right-2 top-1/2 -translate-y-1/2 text-[10px] bg-emerald-100 text-emerald-700 px-1.5 py-0.5 rounded">
                        🔗 in archivio
                    </span>
                )}
            </div>
            {linkedVeicolo && (
                <div className="mt-1 text-[11px] text-slate-600 flex flex-wrap gap-2 items-center">
                    <Car size={12} className="text-slate-500" />
                    <span>{[linkedVeicolo.marca, linkedVeicolo.modello, linkedVeicolo.telaio && `Telaio ${linkedVeicolo.telaio}`].filter(Boolean).join(" · ") || "veicolo in archivio"}</span>
                    {linkedVeicolo.libretto_allegato_id && (
                        <span className="inline-flex items-center gap-1 text-emerald-700"><FileText size={11} /> Libretto già caricato</span>
                    )}
                    {otherPolizze.length > 0 && (
                        <span className="inline-flex items-center gap-1 text-amber-700">
                            <AlertTriangle size={11} /> presente su altre {otherPolizze.length} polizze
                        </span>
                    )}
                </div>
            )}
            {showList && q.length >= 2 && (
                <div className="absolute z-30 top-full left-0 right-0 mt-1 bg-white border border-slate-200 rounded shadow-lg max-h-72 overflow-y-auto">
                    {loading && <div className="p-2 text-xs text-slate-400">Cerco…</div>}
                    {!loading && results.length === 0 && (
                        <div className="p-2">
                            <div className="text-xs text-slate-500 mb-1">Nessuna targa trovata per <b>{q}</b></div>
                            <button onMouseDown={(e) => { e.preventDefault(); setShowCreate(true); }}
                                    className="w-full text-[11px] px-2 py-1.5 rounded bg-emerald-600 text-white hover:bg-emerald-700"
                                    data-testid="targa-create-new-btn">
                                <Plus size={11} className="inline mr-1" /> + Crea Nuova Targa {q}
                            </button>
                        </div>
                    )}
                    {!loading && results.map((v) => (
                        <button key={v.id}
                                onMouseDown={(e) => { e.preventDefault(); selezionaVeicolo(v); }}
                                className="w-full text-left px-2 py-1.5 hover:bg-sky-50 border-b border-slate-100 text-xs"
                                data-testid={`targa-result-${v.targa}`}>
                            <div className="font-mono font-semibold">{v.targa}
                                {v.libretto_allegato_id && <span className="ml-2 text-[10px] text-emerald-700">📎 libretto</span>}
                            </div>
                            <div className="text-[10px] text-slate-500">
                                {[v.marca, v.modello, v.proprietario].filter(Boolean).join(" · ") || "senza dati"}
                            </div>
                        </button>
                    ))}
                    {!loading && results.length > 0 && (
                        <button onMouseDown={(e) => { e.preventDefault(); setShowCreate(true); }}
                                className="w-full text-left px-2 py-1.5 text-[11px] bg-emerald-50 text-emerald-700 hover:bg-emerald-100">
                            <Plus size={11} className="inline mr-1" /> + Crea nuova targa &quot;{q}&quot;
                        </button>
                    )}
                </div>
            )}
            {showCreate && (
                <CreaVeicoloAlVoloDialog
                    targaSuggerita={q}
                    onCreated={onCreated}
                    onClose={() => setShowCreate(false)}
                />
            )}
        </div>
    );
}


function CreaVeicoloAlVoloDialog({ targaSuggerita, onCreated, onClose }) {
    const [form, setForm] = useState({
        targa: (targaSuggerita || "").toUpperCase(),
        marca: "",
        modello: "",
        telaio: "",
        proprietario: "",
        anno_immatricolazione: "",
    });
    const [busy, setBusy] = useState(false);
    const [libretto, setLibretto] = useState(null);

    const submit = async () => {
        if (!form.targa || form.targa.length < 4) {
            toast.error("Targa non valida"); return;
        }
        setBusy(true);
        try {
            const r = await api.post("/veicoli", form);
            const veicolo = r.data;
            // Upload libretto se fornito
            if (libretto && veicolo?.id) {
                const fd = new FormData();
                fd.append("file", libretto);
                fd.append("categoria", "libretto_circolazione");
                fd.append("entita_tipo", "veicolo");
                fd.append("entita_id", veicolo.id);
                fd.append("descrizione", `Libretto ${veicolo.targa}`);
                fd.append("visibile_cliente", "true");
                try {
                    await api.post("/allegati", fd, { headers: { "Content-Type": "multipart/form-data" } });
                    toast.success("Libretto caricato");
                } catch (e) { toast.warning("Veicolo creato ma libretto non caricato"); }
            }
            onCreated(veicolo);
        } catch (e) {
            toast.error(e.response?.data?.detail || "Errore creazione veicolo");
        } finally { setBusy(false); }
    };

    return (
        <Dialog open onOpenChange={(o) => !o && onClose()}>
            <DialogContent className="max-w-lg" data-testid="crea-veicolo-dialog">
                <DialogHeader>
                    <DialogTitle className="flex items-center gap-2">
                        <Car className="text-emerald-600" size={18} /> Crea Nuova Targa
                    </DialogTitle>
                </DialogHeader>
                <div className="grid grid-cols-2 gap-3">
                    <div><Label>Targa *</Label><Input value={form.targa} onChange={(e) => setForm({...form, targa: e.target.value.toUpperCase()})} className="font-mono uppercase" data-testid="crea-targa-input" /></div>
                    <div><Label>Anno Immatr.</Label><Input value={form.anno_immatricolazione} onChange={(e) => setForm({...form, anno_immatricolazione: e.target.value})} placeholder="2024" /></div>
                    <div><Label>Marca</Label><Input value={form.marca} onChange={(e) => setForm({...form, marca: e.target.value})} placeholder="Fiat" /></div>
                    <div><Label>Modello</Label><Input value={form.modello} onChange={(e) => setForm({...form, modello: e.target.value})} placeholder="Panda" /></div>
                    <div className="col-span-2"><Label>Telaio</Label><Input value={form.telaio} onChange={(e) => setForm({...form, telaio: e.target.value.toUpperCase()})} placeholder="Numero telaio" className="font-mono" /></div>
                    <div className="col-span-2"><Label>Proprietario</Label><Input value={form.proprietario} onChange={(e) => setForm({...form, proprietario: e.target.value})} placeholder="Nome intestatario" /></div>
                    <div className="col-span-2">
                        <Label>Libretto di Circolazione (facoltativo, ma consigliato)</Label>
                        <input type="file" accept="application/pdf,image/*"
                               onChange={(e) => setLibretto(e.target.files?.[0] || null)}
                               className="text-xs w-full border border-slate-200 rounded p-2"
                               data-testid="crea-libretto-file" />
                        {libretto && (
                            <div className="text-[10px] text-slate-500 mt-1">
                                📄 {libretto.name} · {(libretto.size / 1024).toFixed(0)} KB
                            </div>
                        )}
                    </div>
                </div>
                <DialogFooter>
                    <Button variant="outline" onClick={onClose}>Annulla</Button>
                    <Button onClick={submit} disabled={busy}
                            className="bg-emerald-600 hover:bg-emerald-700 text-white"
                            data-testid="crea-veicolo-submit">
                        {busy ? "…" : "Crea Targa e Aggancia"}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}
