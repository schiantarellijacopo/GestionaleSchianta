import { useEffect, useState } from "react";
import { api, fmtEur, API_BASE } from "@/lib/api";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { Loading } from "@/components/Shared";
import { Printer, RotateCcw, Building2 } from "lucide-react";

export default function DatiCompagnieTab() {
    const [dal, setDal] = useState("");
    const [al, setAl] = useState("");
    const [d, setD] = useState(null);

    const load = () => {
        const params = {};
        if (dal) params.dal = dal;
        if (al) params.al = al;
        api.get("/contabilita/dati-compagnie", { params }).then((r) => setD(r.data));
    };
    useEffect(() => { load(); /* eslint-disable-next-line */ }, [dal, al]);

    const stampa = () => {
        const qs = new URLSearchParams();
        if (dal) qs.append("dal", dal);
        if (al) qs.append("al", al);
        const a = document.createElement("a");
        a.href = `${API_BASE}/contabilita/dati-compagnie/stampa?${qs}`;
        a.target = "_blank";
        document.body.appendChild(a); a.click(); a.remove();
    };

    if (!d) return <div className="mt-4"><Loading /></div>;

    return (
        <div className="mt-4 space-y-4" data-testid="dati-compagnie-tab">
            <Card className="p-4 border-slate-200">
                <div className="flex items-end gap-3 flex-wrap">
                    <div className="text-sm font-semibold text-slate-700 mr-2 flex items-center gap-2">
                        <Building2 size={16} /> Dati Compagnie
                    </div>
                    <div>
                        <Label className="text-[10px]">Dal</Label>
                        <Input type="date" value={dal} onChange={(e) => setDal(e.target.value)} className="w-40" data-testid="dc-dal" />
                    </div>
                    <div>
                        <Label className="text-[10px]">Al</Label>
                        <Input type="date" value={al} onChange={(e) => setAl(e.target.value)} className="w-40" data-testid="dc-al" />
                    </div>
                    <Button variant="outline" size="sm" onClick={() => { setDal(""); setAl(""); }} data-testid="dc-reset">
                        <RotateCcw size={13} className="mr-1" /> Tutto il periodo
                    </Button>
                    <Button variant="outline" size="sm" onClick={stampa} className="ml-auto" data-testid="dc-print">
                        <Printer size={13} className="mr-1" /> Stampa PDF
                    </Button>
                </div>
                <div className="text-[11px] text-slate-500 mt-2">
                    Incassi/Provvigioni/Rimesse: filtrati dal periodo selezionato. <b>Saldo attuale</b>: sempre cumulativo fino a oggi.
                </div>
            </Card>

            <Card className="border-slate-200 overflow-x-auto">
                <table className="tbl w-full text-xs min-w-[900px]">
                    <thead>
                        <tr className="bg-slate-900 text-white">
                            <th className="text-left px-3 py-2">Compagnia</th>
                            <th className="text-center px-3 py-2">Regime</th>
                            <th className="text-right px-3 py-2">Incassi lordi</th>
                            <th className="text-right px-3 py-2">Incassi netti (dovuto)</th>
                            <th className="text-right px-3 py-2">Provvigioni</th>
                            <th className="text-right px-3 py-2">Rimesse pagate</th>
                            <th className="text-right px-3 py-2">Saldo attuale</th>
                        </tr>
                    </thead>
                    <tbody>
                        {d.compagnie.length === 0 && (
                            <tr><td colSpan="7" className="text-center text-slate-400 py-6">Nessuna compagnia con movimenti</td></tr>
                        )}
                        {d.compagnie.map((c) => (
                            <tr key={c.compagnia_id} data-testid={`dc-${c.compagnia_id}`}>
                                <td className="px-3 py-1.5 font-medium">{c.compagnia}</td>
                                <td className="text-center text-[10px]">
                                    {c.trattiene_provvigioni
                                        ? <span className="badge badge-success">Tratteniamo</span>
                                        : <span className="badge badge-warning">No trattenute</span>}
                                </td>
                                <td className="num text-right px-3">{fmtEur(c.incassi_lordi)}</td>
                                <td className="num text-right px-3">{fmtEur(c.incassi_netti)}</td>
                                <td className="num text-right px-3 text-sky-700">{fmtEur(c.provvigioni)}</td>
                                <td className="num text-right px-3 text-violet-700">{fmtEur(c.rimesse_pagate)}</td>
                                <td className={`num text-right px-3 font-bold ${c.saldo_attuale > 0 ? "text-rose-700" : c.saldo_attuale < 0 ? "text-emerald-700" : "text-slate-500"}`}>
                                    {fmtEur(c.saldo_attuale)}
                                </td>
                            </tr>
                        ))}
                        {d.compagnie.length > 0 && (
                            <tr className="bg-slate-100 font-bold border-t-2 border-slate-900">
                                <td className="px-3 py-2">TOTALE</td>
                                <td></td>
                                <td className="num text-right px-3">{fmtEur(d.totali.incassi_lordi)}</td>
                                <td className="num text-right px-3">{fmtEur(d.totali.incassi_netti)}</td>
                                <td className="num text-right px-3 text-sky-700">{fmtEur(d.totali.provvigioni)}</td>
                                <td className="num text-right px-3 text-violet-700">{fmtEur(d.totali.rimesse_pagate)}</td>
                                <td className="num text-right px-3">{fmtEur(d.totali.saldo_attuale)}</td>
                            </tr>
                        )}
                    </tbody>
                </table>
            </Card>
        </div>
    );
}
