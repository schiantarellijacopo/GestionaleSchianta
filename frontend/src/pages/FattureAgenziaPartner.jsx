/**
 * Fatture Agenzie Partner — gestione fatture provvigioni emesse verso l'agenzia
 * partner per compagnie a mandato di collaborazione. Visualizza partite aperte
 * (provvigioni maturate vs già fatturate) e permette di registrare i pagamenti.
 */
import { useEffect, useMemo, useState } from "react";
import { api, fmtEur, fmtDate } from "@/lib/api";
import { PageHeader, Loading, Empty } from "@/components/Shared";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import {
    Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
    Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogTrigger,
} from "@/components/ui/dialog";
import { Handshake, Plus, FileSpreadsheet, Wallet, Trash2 } from "lucide-react";
import { toast } from "sonner";

export default function FattureAgenziaPartner() {
    const [partite, setPartite] = useState(null);
    const [fatture, setFatture] = useState(null);
    const [compagnie, setCompagnie] = useState([]);
    const [agenzie, setAgenzie] = useState([]);
    const [dialogOpen, setDialogOpen] = useState(false);
    const [precompila, setPrecompila] = useState(null);

    const load = () => {
        api.get("/partite-agenzia-partner").then((r) => setPartite(r.data));
        api.get("/fatture-agenzia-partner").then((r) => setFatture(r.data));
    };
    useEffect(() => {
        load();
        api.get("/compagnie").then((r) =>
            setCompagnie((r.data || []).filter((c) => c.tipo_mandato === "collaborazione")));
        api.get("/agenzie").then((r) => setAgenzie(r.data));
    }, []);

    const registraPagamento = async (f) => {
        if (!window.confirm(`Registrare il pagamento di ${fmtEur(f.importo)} ricevuto dall'agenzia ${f.agenzia_partner_nome}?\nVerrà registrata un'entrata in Prima Nota.`)) return;
        try {
            await api.post(`/fatture-agenzia-partner/${f.id}/registra-pagamento`, {
                data_pagamento: new Date().toISOString().slice(0, 10), importo: f.importo,
            });
            toast.success("Pagamento registrato in Prima Nota"); load();
        } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
    };

    const elimina = async (f) => {
        if (!window.confirm("Eliminare la fattura?")) return;
        try { await api.delete(`/fatture-agenzia-partner/${f.id}`); toast.success("Eliminata"); load(); }
        catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
    };

    const totMaturate = useMemo(() => (partite || []).reduce((s, p) => s + (p.provvigioni_maturate || 0), 0), [partite]);
    const totAperte = useMemo(() => (partite || []).reduce((s, p) => s + (p.partita_aperta || 0), 0), [partite]);

    return (
        <div className="p-6 space-y-5" data-testid="fatture-partner-page">
            <PageHeader
                title={<span className="flex items-center gap-2"><Handshake className="text-amber-600" /> Fatture Agenzie Partner</span>}
                subtitle="Gestione provvigioni fatturate alle agenzie partner (mandato di collaborazione)"
                actions={
                    <Dialog open={dialogOpen} onOpenChange={(o) => { if (!o) setPrecompila(null); setDialogOpen(o); }}>
                        <DialogTrigger asChild>
                            <Button className="bg-amber-700 hover:bg-amber-800" onClick={() => setPrecompila(null)} data-testid="fat-new">
                                <Plus size={14} className="mr-1" /> Nuova fattura
                            </Button>
                        </DialogTrigger>
                        <FatturaDialog compagnie={compagnie} agenzie={agenzie} precompila={precompila}
                            onClose={() => { setDialogOpen(false); setPrecompila(null); load(); }} />
                    </Dialog>
                }
            />

            {/* KPI */}
            <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                <Card className="p-3 border-l-4 border-violet-400 bg-white">
                    <div className="text-[10px] uppercase tracking-wider text-slate-500">Provv. maturate</div>
                    <div className="text-xl font-bold font-mono">{fmtEur(totMaturate)}</div>
                </Card>
                <Card className="p-3 border-l-4 border-amber-400 bg-white">
                    <div className="text-[10px] uppercase tracking-wider text-slate-500">Partita aperta</div>
                    <div className="text-xl font-bold font-mono text-amber-700">{fmtEur(totAperte)}</div>
                </Card>
                <Card className="p-3 border-l-4 border-emerald-400 bg-white">
                    <div className="text-[10px] uppercase tracking-wider text-slate-500">Fatture registrate</div>
                    <div className="text-xl font-bold">{(fatture || []).length}</div>
                </Card>
            </div>

            {/* PARTITE APERTE */}
            <Card className="p-4">
                <div className="flex items-center gap-2 mb-3">
                    <FileSpreadsheet size={16} className="text-amber-600" />
                    <h2 className="text-sm font-semibold text-slate-800 uppercase tracking-wider">
                        Partite aperte per compagnia (mandato collaborazione)
                    </h2>
                </div>
                {partite === null ? <Loading /> : partite.length === 0 ? <Empty message="Nessuna compagnia a mandato di collaborazione" /> : (
                    <table className="tbl-compact w-full text-xs">
                        <thead><tr>
                            <th>Compagnia</th><th>Agenzia partner</th>
                            <th className="text-right">Provv. maturate</th>
                            <th className="text-right">Fatturato</th>
                            <th className="text-right">Pagato</th>
                            <th className="text-right">Partita aperta</th>
                            <th className="w-32"></th>
                        </tr></thead>
                        <tbody>
                            {partite.map((p) => {
                                const partnerName = agenzie.find((a) => a.id === p.agenzia_partner_id)?.ragione_sociale;
                                return (
                                    <tr key={p.compagnia_id} data-testid={`partita-${p.compagnia_id}`}>
                                        <td className="font-medium">{p.compagnia_nome}</td>
                                        <td>{partnerName || "—"}</td>
                                        <td className="text-right font-mono">{fmtEur(p.provvigioni_maturate)}</td>
                                        <td className="text-right font-mono">{fmtEur(p.totale_fatturato)}</td>
                                        <td className="text-right font-mono text-emerald-700">{fmtEur(p.totale_pagato)}</td>
                                        <td className={`text-right font-mono font-bold ${p.partita_aperta > 0 ? "text-amber-700" : "text-slate-400"}`}>{fmtEur(p.partita_aperta)}</td>
                                        <td className="text-right">
                                            {p.partita_aperta > 0.01 && (
                                                <Button size="sm" variant="outline" data-testid={`fat-da-partita-${p.compagnia_id}`}
                                                    onClick={() => {
                                                        setPrecompila({
                                                            compagnia_id: p.compagnia_id,
                                                            agenzia_partner_id: p.agenzia_partner_id,
                                                            importo: p.partita_aperta,
                                                        });
                                                        setDialogOpen(true);
                                                    }}>
                                                    Crea fattura
                                                </Button>
                                            )}
                                        </td>
                                    </tr>
                                );
                            })}
                        </tbody>
                    </table>
                )}
            </Card>

            {/* FATTURE REGISTRATE */}
            <Card className="p-4">
                <h2 className="text-sm font-semibold text-slate-800 uppercase tracking-wider mb-3">
                    Fatture provvigioni partner
                </h2>
                {fatture === null ? <Loading /> : fatture.length === 0 ? <Empty message="Nessuna fattura registrata" /> : (
                    <table className="tbl-compact w-full text-xs">
                        <thead><tr>
                            <th>Data</th><th>N. fattura</th>
                            <th>Compagnia</th><th>Agenzia partner</th>
                            <th className="text-right">Importo €</th>
                            <th>Stato</th>
                            <th className="w-28"></th>
                        </tr></thead>
                        <tbody>
                            {fatture.map((f) => (
                                <tr key={f.id} data-testid={`fat-row-${f.id}`}>
                                    <td className="num">{fmtDate(f.data)}</td>
                                    <td className="font-mono">{f.numero_fattura || "—"}</td>
                                    <td>{f.compagnia_nome}</td>
                                    <td>{f.agenzia_partner_nome}</td>
                                    <td className="text-right font-mono font-semibold">{fmtEur(f.importo)}</td>
                                    <td>
                                        {f.stato === "pagata" ? <span className="badge badge-success">pagata {f.data_pagamento ? `il ${fmtDate(f.data_pagamento)}` : ""}</span>
                                            : <span className="badge badge-warning">da pagare</span>}
                                    </td>
                                    <td className="text-right whitespace-nowrap">
                                        {f.stato !== "pagata" && (
                                            <button onClick={() => registraPagamento(f)}
                                                className="inline-flex items-center justify-center h-7 w-7 rounded border border-emerald-300 hover:bg-emerald-50 text-emerald-700 mr-1"
                                                title="Registra pagamento" data-testid={`fat-paga-${f.id}`}>
                                                <Wallet size={12} />
                                            </button>
                                        )}
                                        <button onClick={() => elimina(f)} className="inline-flex items-center justify-center h-7 w-7 rounded border border-rose-200 hover:bg-rose-50 text-rose-600">
                                            <Trash2 size={12} />
                                        </button>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                )}
            </Card>
        </div>
    );
}

function FatturaDialog({ compagnie, agenzie, precompila, onClose }) {
    const [f, setF] = useState({
        agenzia_partner_id: precompila?.agenzia_partner_id || "",
        compagnie_ids: precompila?.compagnia_id ? [precompila.compagnia_id] : [],
        data: new Date().toISOString().slice(0, 10),
        importo: precompila?.importo || "",
        perc_ritenuta: 0,
        numero_fattura: "",
        descrizione: "",
        note: "",
    });
    const set = (k, v) => setF((p) => ({ ...p, [k]: v }));
    const agenziaSel = agenzie.find((a) => a.id === f.agenzia_partner_id);
    const compagnieAgenzia = compagnie.filter((c) => c.agenzia_partner_id === f.agenzia_partner_id);

    // Auto-compila ritenuta quando si seleziona agenzia partner
    useEffect(() => {
        if (agenziaSel) set("perc_ritenuta", agenziaSel.perc_ritenuta_acconto || 0);
    // eslint-disable-next-line
    }, [f.agenzia_partner_id]);

    const importoNum = parseFloat(f.importo) || 0;
    const percRit = parseFloat(f.perc_ritenuta) || 0;
    const ritenuta = Math.round(importoNum * percRit) / 100;
    const netto = Math.round((importoNum - ritenuta) * 100) / 100;

    const toggleComp = (cid) => set("compagnie_ids", f.compagnie_ids.includes(cid)
        ? f.compagnie_ids.filter((x) => x !== cid)
        : [...f.compagnie_ids, cid]);

    const save = async () => {
        if (!f.agenzia_partner_id) { toast.error("Seleziona prima l'agenzia partner"); return; }
        if (!f.compagnie_ids.length) { toast.error("Seleziona almeno una compagnia"); return; }
        if (!importoNum || importoNum <= 0) { toast.error("Importo deve essere positivo"); return; }
        try {
            await api.post("/fatture-agenzia-partner", {
                agenzia_partner_id: f.agenzia_partner_id,
                compagnie_ids: f.compagnie_ids,
                data: f.data, importo: importoNum,
                perc_ritenuta: percRit,
                numero_fattura: f.numero_fattura, descrizione: f.descrizione, note: f.note,
            });
            toast.success("Fattura creata"); onClose();
        } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
    };

    return (
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
            <DialogHeader><DialogTitle>Nuova fattura agenzia partner</DialogTitle></DialogHeader>
            <div className="space-y-3 py-2">
                {/* STEP 1: AGENZIA */}
                <div>
                    <Label className="text-sm">1️⃣ Agenzia partner *</Label>
                    <Select value={f.agenzia_partner_id} onValueChange={(v) => { set("agenzia_partner_id", v); set("compagnie_ids", []); }}>
                        <SelectTrigger data-testid="fat-age"><SelectValue placeholder="Seleziona agenzia partner" /></SelectTrigger>
                        <SelectContent>
                            {agenzie.filter((a) => a.tipo === "partner").map((a) => (
                                <SelectItem key={a.id} value={a.id}>{a.ragione_sociale} {a.perc_ritenuta_acconto ? `(rit. ${a.perc_ritenuta_acconto}%)` : ""}</SelectItem>
                            ))}
                        </SelectContent>
                    </Select>
                </div>

                {/* STEP 2: COMPAGNIE multi-select */}
                {f.agenzia_partner_id && (
                    <div>
                        <Label className="text-sm">2️⃣ Compagnie (multipla) *</Label>
                        {compagnieAgenzia.length === 0 ? (
                            <div className="text-xs text-amber-700 bg-amber-50 border border-amber-200 p-2 rounded">
                                Nessuna compagnia con mandato di collaborazione collegata a questa agenzia. Censiscile prima
                                impostando "tipo_mandato = collaborazione" e selezionando l'agenzia partner.
                            </div>
                        ) : (
                            <div className="grid grid-cols-2 gap-2 mt-1">
                                {compagnieAgenzia.map((c) => (
                                    <label key={c.id} className={`flex items-center gap-2 p-2 border rounded cursor-pointer
                                        ${f.compagnie_ids.includes(c.id) ? "bg-sky-50 border-sky-400" : "border-slate-200"}`}>
                                        <Checkbox checked={f.compagnie_ids.includes(c.id)} onCheckedChange={() => toggleComp(c.id)} />
                                        <span className="text-sm">{c.ragione_sociale}</span>
                                    </label>
                                ))}
                            </div>
                        )}
                    </div>
                )}

                {/* STEP 3: IMPORTO + RITENUTA + NETTO */}
                {f.compagnie_ids.length > 0 && (
                    <div className="bg-slate-50 p-3 rounded space-y-3">
                        <div className="grid grid-cols-2 gap-3">
                            <div><Label>Data fattura *</Label>
                                <Input type="date" value={f.data} onChange={(e) => set("data", e.target.value)} data-testid="fat-data" /></div>
                            <div><Label>N° fattura</Label>
                                <Input value={f.numero_fattura} onChange={(e) => set("numero_fattura", e.target.value)} /></div>
                        </div>
                        <div className="grid grid-cols-3 gap-3">
                            <div><Label>3️⃣ Importo lordo € *</Label>
                                <Input type="number" step="0.01" value={f.importo}
                                    onChange={(e) => set("importo", e.target.value)} data-testid="fat-importo" /></div>
                            <div>
                                <Label>Ritenuta % (auto da agenzia)</Label>
                                <Input type="number" step="0.01" value={f.perc_ritenuta}
                                    onChange={(e) => set("perc_ritenuta", e.target.value)} data-testid="fat-rit" />
                            </div>
                            <div>
                                <Label>Importo definitivo netto €</Label>
                                <div className="bg-emerald-50 border border-emerald-300 rounded px-3 py-2 text-emerald-900 font-bold text-lg font-mono" data-testid="fat-netto">
                                    {netto.toFixed(2)}
                                </div>
                            </div>
                        </div>
                        {ritenuta > 0 && (
                            <div className="text-xs text-slate-600 font-mono">
                                Importo lordo: {importoNum.toFixed(2)} − Ritenuta {percRit}%: {ritenuta.toFixed(2)} = <strong>Netto: {netto.toFixed(2)} €</strong>
                            </div>
                        )}
                    </div>
                )}

                <div><Label>Descrizione</Label>
                    <Input value={f.descrizione} onChange={(e) => set("descrizione", e.target.value)} /></div>
                <div><Label>Note</Label>
                    <Input value={f.note} onChange={(e) => set("note", e.target.value)} /></div>
            </div>
            <DialogFooter>
                <Button onClick={save} className="bg-amber-700 hover:bg-amber-800" data-testid="fat-save">Crea fattura</Button>
            </DialogFooter>
        </DialogContent>
    );
}
