import { useEffect, useState } from "react";
import { api, fmtDate, fmtEur, API_BASE } from "@/lib/api";
import { PageHeader, Loading, Empty } from "@/components/Shared";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import {
    Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from "@/components/ui/dialog";
import { Printer, Wallet, Users } from "lucide-react";
import { toast } from "sonner";

export default function Provvigioni() {
    const [collabs, setCollabs] = useState([]);
    const [sel, setSel] = useState(null);
    const [data, setData] = useState(null);
    const [dal, setDal] = useState("");
    const [al, setAl] = useState("");
    const [conti, setConti] = useState([]);
    const [payOpen, setPayOpen] = useState(false);
    const [selectedTitoli, setSelectedTitoli] = useState(new Set());

    useEffect(() => {
        api.get("/collaboratori").then((r) => setCollabs(r.data));
        api.get("/librerie/conti-cassa", { params: { attivi: true } }).then((r) => setConti(r.data));
    }, []);

    const load = () => {
        if (!sel) return;
        const params = {};
        if (dal) params.dal = dal;
        if (al) params.al = al;
        api.get(`/collaboratori/${sel.id}/estratto-provvigioni`, { params }).then((r) => {
            setData(r.data);
            setSelectedTitoli(new Set());
        });
    };
    useEffect(() => { load(); /* eslint-disable-next-line */ }, [sel, dal, al]);

    const stampa = () => {
        const qs = new URLSearchParams();
        if (dal) qs.append("dal", dal);
        if (al) qs.append("al", al);
        window.open(`${API_BASE}/stampa/provvigioni/${sel.id}?${qs}`, "_blank");
    };

    const toggleTitolo = (id) => {
        setSelectedTitoli((p) => {
            const n = new Set(p); n.has(id) ? n.delete(id) : n.add(id); return n;
        });
    };
    const selectAllUnpaid = () => {
        if (!data) return;
        setSelectedTitoli(new Set(data.righe.filter((r) => !r.gia_pagato).map((r) => r.titolo_id)));
    };

    return (
        <div data-testid="provvigioni-page">
            <PageHeader
                title="Estratto conto provvigioni"
                subtitle="Provvigioni maturate e pagamenti collaboratori"
            />

            <div className="grid grid-cols-12 gap-4">
                <Card className="col-span-3 border-slate-200 p-3">
                    <div className="text-xs uppercase tracking-wider text-slate-500 mb-2 flex items-center gap-1">
                        <Users size={12} /> Collaboratori
                    </div>
                    {collabs.length === 0 ? <Empty /> : (
                        <ul className="space-y-1">
                            {collabs.map((c) => (
                                <li key={c.id}>
                                    <button
                                        data-testid={`collab-${c.id}`}
                                        onClick={() => setSel(c)}
                                        className={`w-full text-left px-3 py-2 rounded-md text-sm transition-colors ${
                                            sel?.id === c.id ? "bg-sky-50 border border-sky-200 font-medium" : "hover:bg-slate-50"
                                        }`}
                                    >
                                        <div className="text-slate-900">{c.name}</div>
                                        <div className="text-[11px] text-slate-500">
                                            {c.role} · Provv {c.perc_provvigione_default || 0}% · Rit {c.perc_ritenuta_acconto || 0}%
                                        </div>
                                    </button>
                                </li>
                            ))}
                        </ul>
                    )}
                </Card>

                <div className="col-span-9 space-y-4">
                    {!sel ? (
                        <Card className="p-12 text-center text-slate-500 border-slate-200">
                            Seleziona un collaboratore per vedere l&apos;estratto conto provvigioni
                        </Card>
                    ) : !data ? <Loading /> : (
                        <>
                            <Card className="p-4 border-slate-200">
                                <div className="flex items-end gap-3 flex-wrap">
                                    <div className="font-medium text-slate-900">
                                        <span className="text-xs text-slate-500 uppercase tracking-wider block">Collaboratore</span>
                                        {data.collaboratore.name}
                                    </div>
                                    <div className="text-xs text-slate-500 num">
                                        <div>Provv. default: <b className="num text-slate-700">{data.collaboratore.perc_provvigione_default || 0}%</b></div>
                                        <div>Rit. acconto: <b className="num text-slate-700">{data.collaboratore.perc_ritenuta_acconto || 0}%</b></div>
                                        <div>Contributi: <b className="num text-slate-700">{data.collaboratore.perc_inps_inarcassa || 0}%</b></div>
                                    </div>
                                    <div className="ml-auto flex gap-2 items-end">
                                        <div>
                                            <Label className="text-[10px]">Dal</Label>
                                            <Input data-testid="prov-dal" type="date" value={dal} onChange={(e) => setDal(e.target.value)} className="w-36" />
                                        </div>
                                        <div>
                                            <Label className="text-[10px]">Al</Label>
                                            <Input data-testid="prov-al" type="date" value={al} onChange={(e) => setAl(e.target.value)} className="w-36" />
                                        </div>
                                        <Button variant="outline" onClick={stampa} data-testid="prov-print">
                                            <Printer size={14} className="mr-1" /> Stampa PDF
                                        </Button>
                                    </div>
                                </div>
                            </Card>

                            {/* Totali */}
                            <div className="grid grid-cols-5 gap-3">
                                <Stat label="Provv. lorde periodo" value={fmtEur(data.totali.provvigioni_lorde_periodo)} />
                                <Stat label="Da pagare" value={fmtEur(data.totali.provvigioni_da_pagare)} accent="amber" />
                                <Stat label="Ritenuta acconto" value={`- ${fmtEur(data.totali.ritenuta_acconto_calcolata)}`} accent="rose" />
                                <Stat label="Contributi" value={`- ${fmtEur(data.totali.contributi_calcolati)}`} accent="rose" />
                                <Stat label="Netto da pagare" value={fmtEur(data.totali.netto_da_pagare)} accent="emerald" />
                            </div>

                            {/* Tabella titoli */}
                            <Card className="border-slate-200 overflow-hidden">
                                <div className="px-4 py-2 bg-slate-50 border-b border-slate-200 flex items-center justify-between">
                                    <div className="text-sm font-medium">Provvigioni maturate ({data.righe.length})</div>
                                    <div className="flex gap-2">
                                        <button onClick={selectAllUnpaid} className="text-xs text-sky-700 hover:underline" data-testid="select-unpaid">
                                            Seleziona da pagare ({data.righe.filter((r) => !r.gia_pagato).length})
                                        </button>
                                        <Button
                                            size="sm"
                                            disabled={selectedTitoli.size === 0}
                                            onClick={() => setPayOpen(true)}
                                            className="bg-emerald-600 hover:bg-emerald-700"
                                            data-testid="paga-button"
                                        >
                                            <Wallet size={14} className="mr-1" />
                                            Paga selezionati ({selectedTitoli.size})
                                        </Button>
                                    </div>
                                </div>
                                {data.righe.length === 0 ? <Empty message="Nessuna provvigione nel periodo" /> : (
                                    <table className="tbl w-full">
                                        <thead>
                                            <tr>
                                                <th className="w-10"></th>
                                                <th>Data</th>
                                                <th>N. polizza</th>
                                                <th>Contraente</th>
                                                <th>Ramo</th>
                                                <th className="text-right">Premio</th>
                                                <th className="text-right">Provvigione</th>
                                                <th>Stato</th>
                                            </tr>
                                        </thead>
                                        <tbody>
                                            {data.righe.map((r) => (
                                                <tr key={r.titolo_id} className={selectedTitoli.has(r.titolo_id) ? "bg-sky-50" : ""}>
                                                    <td>
                                                        <input
                                                            type="checkbox"
                                                            checked={selectedTitoli.has(r.titolo_id)}
                                                            onChange={() => toggleTitolo(r.titolo_id)}
                                                            disabled={r.gia_pagato}
                                                            data-testid={`select-titolo-${r.titolo_id}`}
                                                        />
                                                    </td>
                                                    <td className="num">{fmtDate(r.data_incasso)}</td>
                                                    <td className="num text-xs">{r.numero_polizza || "-"}</td>
                                                    <td>{r.contraente || "-"}</td>
                                                    <td className="text-xs">{r.ramo || "-"}</td>
                                                    <td className="num text-right">{fmtEur(r.importo_lordo)}</td>
                                                    <td className="num text-right font-medium text-emerald-700">{fmtEur(r.provvigione)}</td>
                                                    <td>
                                                        {r.gia_pagato ? <span className="badge badge-success">pagata</span> : <span className="badge badge-warning">da pagare</span>}
                                                    </td>
                                                </tr>
                                            ))}
                                        </tbody>
                                    </table>
                                )}
                            </Card>

                            {/* Storico pagamenti */}
                            {data.pagamenti_periodo.length > 0 && (
                                <Card className="border-slate-200 overflow-hidden">
                                    <div className="px-4 py-2 bg-slate-50 border-b border-slate-200 text-sm font-medium">
                                        Pagamenti effettuati nel periodo
                                    </div>
                                    <table className="tbl w-full">
                                        <thead>
                                            <tr>
                                                <th>Data</th>
                                                <th>Periodo</th>
                                                <th className="text-right">Lordo</th>
                                                <th className="text-right">Rit.</th>
                                                <th className="text-right">Contributi</th>
                                                <th className="text-right">Netto</th>
                                                <th>Mezzo</th>
                                            </tr>
                                        </thead>
                                        <tbody>
                                            {data.pagamenti_periodo.map((p) => (
                                                <tr key={p.id}>
                                                    <td className="num">{fmtDate(p.data_pagamento)}</td>
                                                    <td className="text-xs num">{p.periodo_dal} → {p.periodo_al}</td>
                                                    <td className="num text-right">{fmtEur(p.provvigioni_lorde)}</td>
                                                    <td className="num text-right text-rose-600">-{fmtEur(p.ritenuta_acconto)}</td>
                                                    <td className="num text-right text-rose-600">-{fmtEur(p.contributi)}</td>
                                                    <td className="num text-right font-semibold text-emerald-700">{fmtEur(p.netto_pagato)}</td>
                                                    <td className="text-xs">{p.mezzo_pagamento}</td>
                                                </tr>
                                            ))}
                                        </tbody>
                                    </table>
                                </Card>
                            )}
                        </>
                    )}
                </div>
            </div>

            {payOpen && sel && data && (
                <PagaDialog
                    collab={sel}
                    titoli_ids={Array.from(selectedTitoli)}
                    rows={data.righe.filter((r) => selectedTitoli.has(r.titolo_id))}
                    conti={conti}
                    onClose={() => { setPayOpen(false); setSelectedTitoli(new Set()); load(); }}
                />
            )}
        </div>
    );
}

function Stat({ label, value, accent }) {
    const colors = {
        amber: "border-l-amber-500",
        emerald: "border-l-emerald-500",
        rose: "border-l-rose-500",
    };
    return (
        <Card className={`p-4 border-slate-200 border-l-4 ${colors[accent] || "border-l-slate-300"}`}>
            <div className="text-[11px] uppercase tracking-wider text-slate-500">{label}</div>
            <div className="text-xl font-semibold num text-slate-900 mt-1">{value}</div>
        </Card>
    );
}

function PagaDialog({ collab, titoli_ids, rows, conti, onClose }) {
    const today = new Date().toISOString().slice(0, 10);
    const lordo = rows.reduce((s, r) => s + (r.provvigione || 0), 0);
    const ritPerc = collab.perc_ritenuta_acconto || 0;
    const inpsPerc = collab.perc_inps_inarcassa || 0;
    const [rit, setRit] = useState((lordo * ritPerc / 100).toFixed(2));
    const [contr, setContr] = useState((lordo * inpsPerc / 100).toFixed(2));
    const [conto_id, setContoId] = useState("");
    const [data_pag, setDataPag] = useState(today);
    const [mezzo, setMezzo] = useState("bonifico");
    const [note, setNote] = useState("");

    const netto = lordo - parseFloat(rit || 0) - parseFloat(contr || 0);

    const submit = async () => {
        if (!conto_id) { toast.error("Seleziona il conto/banca da cui paghi"); return; }
        try {
            const r = await api.post(`/collaboratori/${collab.id}/paga-provvigioni`, {
                titoli_ids, conto_cassa_id: conto_id,
                data_pagamento: data_pag, mezzo_pagamento: mezzo, note,
                override_ritenuta: parseFloat(rit) || 0,
                override_contributi: parseFloat(contr) || 0,
            });
            toast.success(`Pagamento di ${fmtEur(r.data.pagamento.netto_pagato)} registrato nel Brogliaccio`);
            onClose();
        } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
    };

    return (
        <Dialog open onOpenChange={(o) => !o && onClose()}>
            <DialogContent className="max-w-xl">
                <DialogHeader><DialogTitle>Paga provvigioni a {collab.name}</DialogTitle></DialogHeader>
                <div className="space-y-3 py-2">
                    <div className="text-sm bg-sky-50 border border-sky-200 rounded p-3">
                        <div>{titoli_ids.length} titoli selezionati</div>
                        <div className="text-xs text-sky-900 mt-1">
                            Verrà creato un movimento contabile USCITA (categoria provvigioni) sul conto selezionato, visibile nel Brogliaccio.
                        </div>
                    </div>
                    <div className="grid grid-cols-3 gap-3">
                        <div>
                            <Label>Provvigioni lorde €</Label>
                            <Input value={lordo.toFixed(2)} disabled className="bg-slate-50 num font-medium" />
                        </div>
                        <div>
                            <Label>Ritenuta acconto €</Label>
                            <Input type="number" step="0.01" value={rit} onChange={(e) => setRit(e.target.value)} data-testid="pay-rit" />
                        </div>
                        <div>
                            <Label>Contributi €</Label>
                            <Input type="number" step="0.01" value={contr} onChange={(e) => setContr(e.target.value)} />
                        </div>
                    </div>
                    <div className="bg-emerald-50 border border-emerald-300 rounded p-3 flex items-center justify-between">
                        <div className="text-xs uppercase tracking-wider text-emerald-700">Netto da pagare</div>
                        <div className="text-2xl font-bold text-emerald-700 num">{fmtEur(netto)}</div>
                    </div>
                    <div className="grid grid-cols-2 gap-3">
                        <div>
                            <Label>Data pagamento</Label>
                            <Input type="date" value={data_pag} onChange={(e) => setDataPag(e.target.value)} />
                        </div>
                        <div>
                            <Label>Mezzo</Label>
                            <Input value={mezzo} onChange={(e) => setMezzo(e.target.value)} />
                        </div>
                    </div>
                    <div>
                        <Label>Conto / Banca (USCITA) *</Label>
                        <Select value={conto_id} onValueChange={setContoId}>
                            <SelectTrigger data-testid="pay-conto"><SelectValue placeholder="Seleziona conto" /></SelectTrigger>
                            <SelectContent>
                                {conti.map((c) => <SelectItem key={c.id} value={c.id}>{c.nome}</SelectItem>)}
                            </SelectContent>
                        </Select>
                    </div>
                    <div>
                        <Label>Note</Label>
                        <Input value={note} onChange={(e) => setNote(e.target.value)} />
                    </div>
                </div>
                <DialogFooter>
                    <Button variant="outline" onClick={onClose}>Annulla</Button>
                    <Button onClick={submit} className="bg-emerald-600 hover:bg-emerald-700" data-testid="pay-confirm">
                        Registra pagamento
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}
