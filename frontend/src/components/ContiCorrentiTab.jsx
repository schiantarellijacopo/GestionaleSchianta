/**
 * ContiCorrentiTab — gestione multi-IBAN per un'anagrafica.
 * Per ogni IBAN inserito il backend risolve automaticamente banca (ABI/CAB/BIC)
 * tramite `/api/lookup/iban`.
 */
import { useState } from "react";
import { api } from "@/lib/api";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Landmark, Plus, Star, Trash2, Search, Loader2, CheckCircle2, XCircle } from "lucide-react";
import { toast } from "sonner";

export default function ContiCorrentiTab({ ana, canEdit, onReload }) {
    const conti = ana.conti_correnti || [];
    const [adding, setAdding] = useState(false);

    const setPrincipale = async (idx) => {
        const updated = conti.map((c, i) => ({ ...c, principale: i === idx }));
        try {
            await api.put(`/anagrafiche/${ana.id}`, { conti_correnti: updated });
            toast.success("Conto principale aggiornato");
            onReload?.();
        } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
    };

    const elimina = async (idx) => {
        if (!window.confirm("Rimuovere questo IBAN?")) return;
        const updated = conti.filter((_, i) => i !== idx);
        try {
            await api.put(`/anagrafiche/${ana.id}`, { conti_correnti: updated });
            toast.success("IBAN rimosso");
            onReload?.();
        } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
    };

    const aggiungi = async (nuovo) => {
        const updated = [...conti];
        // se principale: sbianca gli altri
        if (nuovo.principale) updated.forEach((c) => { c.principale = false; });
        // se è il primo, forzalo principale
        if (updated.length === 0) nuovo.principale = true;
        updated.push(nuovo);
        try {
            await api.put(`/anagrafiche/${ana.id}`, { conti_correnti: updated });
            toast.success("IBAN aggiunto");
            setAdding(false);
            onReload?.();
        } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
    };

    return (
        <div className="space-y-4 mt-4" data-testid="conti-correnti-tab">
            <Card className="p-6 border-slate-200">
                <div className="flex items-center justify-between mb-4">
                    <div className="flex items-center gap-2">
                        <Landmark size={18} className="text-sky-700" />
                        <h3 className="font-medium">Conti correnti / IBAN ({conti.length})</h3>
                    </div>
                    {canEdit && !adding && (
                        <Button size="sm" onClick={() => setAdding(true)} className="bg-sky-700 hover:bg-sky-800" data-testid="cc-add-btn">
                            <Plus size={14} className="mr-1" /> Aggiungi IBAN
                        </Button>
                    )}
                </div>

                {adding && (
                    <AddIbanForm onCancel={() => setAdding(false)} onSave={aggiungi} defaultIntestazione={ana.ragione_sociale} />
                )}

                {conti.length === 0 && !adding ? (
                    <div className="text-center py-10 text-sm text-slate-500 border border-dashed border-slate-200 rounded-md">
                        <Landmark size={28} className="mx-auto text-slate-300 mb-2" />
                        Nessun IBAN registrato. Premi &quot;Aggiungi IBAN&quot; per inserire il primo conto.
                    </div>
                ) : (
                    <div className="space-y-2 mt-3">
                        {conti.map((c, i) => (
                            <div key={i} className={`border rounded-md p-3 ${c.principale ? "border-amber-300 bg-amber-50/40" : "border-slate-200 bg-white"}`} data-testid={`cc-item-${i}`}>
                                <div className="flex items-start justify-between gap-3">
                                    <div className="flex-1 min-w-0">
                                        <div className="flex items-center gap-2 flex-wrap">
                                            <span className="font-mono text-sm font-semibold text-slate-900">{c.iban}</span>
                                            {c.principale && (
                                                <span className="text-[10px] uppercase tracking-widest bg-amber-100 text-amber-800 px-2 py-0.5 rounded-full flex items-center gap-1">
                                                    <Star size={9} /> Principale
                                                </span>
                                            )}
                                        </div>
                                        <div className="text-sm text-slate-700 mt-1">{c.banca_ragione_sociale || "—"}</div>
                                        <div className="text-[11px] text-slate-500 num mt-0.5">
                                            {c.banca_abi && `ABI ${c.banca_abi}`}
                                            {c.banca_cab && ` · CAB ${c.banca_cab}`}
                                            {c.banca_bic && ` · BIC ${c.banca_bic}`}
                                        </div>
                                        {c.intestazione && <div className="text-xs text-slate-600 mt-1">Intestato a: {c.intestazione}</div>}
                                        {c.note && <div className="text-xs italic text-slate-500 mt-1">{c.note}</div>}
                                    </div>
                                    {canEdit && (
                                        <div className="flex gap-1 shrink-0">
                                            {!c.principale && (
                                                <button
                                                    onClick={() => setPrincipale(i)}
                                                    className="text-[11px] px-2 py-1 rounded border border-amber-300 text-amber-700 bg-white hover:bg-amber-50"
                                                    data-testid={`cc-set-principale-${i}`}
                                                    title="Imposta come principale"
                                                >
                                                    <Star size={11} className="inline" /> Principale
                                                </button>
                                            )}
                                            <button
                                                onClick={() => elimina(i)}
                                                className="text-[11px] px-2 py-1 rounded border border-rose-300 text-rose-600 bg-white hover:bg-rose-50"
                                                data-testid={`cc-delete-${i}`}
                                            >
                                                <Trash2 size={11} className="inline" />
                                            </button>
                                        </div>
                                    )}
                                </div>
                            </div>
                        ))}
                    </div>
                )}
            </Card>
        </div>
    );
}

function AddIbanForm({ onCancel, onSave, defaultIntestazione }) {
    const [iban, setIban] = useState("");
    const [lookup, setLookup] = useState(null); // {ragione_sociale, abi, cab, bic, valid}
    const [busy, setBusy] = useState(false);
    const [intestazione, setIntestazione] = useState(defaultIntestazione || "");
    const [principale, setPrincipale] = useState(false);
    const [note, setNote] = useState("");

    const risolvi = async () => {
        const cleaned = (iban || "").replace(/\s/g, "").toUpperCase();
        if (cleaned.length < 15) {
            toast.error("IBAN troppo corto");
            return;
        }
        setBusy(true);
        try {
            const r = await api.get("/lookup/iban", { params: { iban: cleaned } });
            setLookup(r.data);
            setIban(cleaned);
            if (r.data?.banca?.ragione_sociale) {
                toast.success(`Banca risolta: ${r.data.banca.ragione_sociale}`);
            } else if (r.data?.valid === false) {
                toast.error(r.data?.error || "IBAN non valido");
            } else {
                toast.warning("Banca non presente in tabella locale");
            }
        } catch (e) {
            toast.error(e.response?.data?.detail || "Errore lookup IBAN");
        } finally { setBusy(false); }
    };

    const salva = () => {
        const cleaned = (iban || "").replace(/\s/g, "").toUpperCase();
        if (cleaned.length < 15) { toast.error("IBAN non valido"); return; }
        onSave({
            iban: cleaned,
            banca_ragione_sociale: lookup?.banca?.ragione_sociale || null,
            banca_abi: lookup?.abi || null,
            banca_cab: lookup?.cab || null,
            banca_bic: lookup?.banca?.bic || null,
            intestazione: intestazione || null,
            principale,
            note: note || null,
        });
    };

    const validBadge = lookup?.valid === true
        ? <span className="text-[10px] bg-emerald-100 text-emerald-700 px-2 py-0.5 rounded-full flex items-center gap-1"><CheckCircle2 size={10} /> IBAN valido</span>
        : lookup?.valid === false
        ? <span className="text-[10px] bg-rose-100 text-rose-700 px-2 py-0.5 rounded-full flex items-center gap-1"><XCircle size={10} /> IBAN non valido</span>
        : null;

    return (
        <div className="border border-sky-200 bg-sky-50/40 rounded-md p-4 mb-3 space-y-3" data-testid="cc-add-form">
            <div className="flex items-end gap-2 flex-wrap">
                <div className="flex-1 min-w-[280px]">
                    <Label>IBAN *</Label>
                    <Input
                        value={iban}
                        onChange={(e) => setIban(e.target.value.toUpperCase())}
                        placeholder="IT60X0542811101000000123456"
                        className="font-mono"
                        data-testid="cc-iban-input"
                        autoFocus
                    />
                </div>
                <Button type="button" variant="outline" onClick={risolvi} disabled={busy} data-testid="cc-lookup-btn">
                    {busy ? <Loader2 size={13} className="animate-spin mr-1" /> : <Search size={13} className="mr-1" />}
                    Risolvi banca
                </Button>
                {validBadge}
            </div>
            {lookup?.banca && (
                <div className="bg-white rounded p-2 text-xs border border-slate-200" data-testid="cc-lookup-result">
                    <div className="text-slate-700"><b>{lookup.banca.ragione_sociale}</b></div>
                    <div className="text-slate-500 num">
                        ABI {lookup.abi} · CAB {lookup.cab || "—"} {lookup.banca.bic && `· BIC ${lookup.banca.bic}`}
                    </div>
                </div>
            )}
            <div className="grid grid-cols-2 gap-3">
                <div>
                    <Label>Intestazione</Label>
                    <Input value={intestazione} onChange={(e) => setIntestazione(e.target.value)} data-testid="cc-intestazione-input" />
                </div>
                <div className="flex items-end">
                    <label className="flex items-center gap-2 text-sm cursor-pointer">
                        <input
                            type="checkbox"
                            checked={principale}
                            onChange={(e) => setPrincipale(e.target.checked)}
                            data-testid="cc-principale-checkbox"
                        />
                        Imposta come principale
                    </label>
                </div>
            </div>
            <div>
                <Label>Note</Label>
                <Textarea rows={2} value={note} onChange={(e) => setNote(e.target.value)} placeholder="Es: conto per SDD polizze auto" data-testid="cc-note-input" />
            </div>
            <div className="flex justify-end gap-2 pt-1">
                <Button variant="outline" onClick={onCancel} data-testid="cc-cancel-btn">Annulla</Button>
                <Button onClick={salva} className="bg-sky-700 hover:bg-sky-800" data-testid="cc-save-btn">Salva IBAN</Button>
            </div>
        </div>
    );
}
