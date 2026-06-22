import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, fmtDate, fmtEur } from "@/lib/api";
import { PageHeader, StatusBadge, Loading, Empty } from "@/components/Shared";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";

export default function Titoli() {
    const [list, setList] = useState(null);
    const [stato, setStato] = useState("all");

    const load = () => {
        const params = {};
        if (stato !== "all") params.stato = stato;
        api.get("/titoli", { params }).then((r) => setList(r.data));
    };
    useEffect(() => { load(); /* eslint-disable-next-line */ }, [stato]);

    const incassa = async (id) => {
        try {
            await api.post(`/titoli/${id}/incassa`, { mezzo_pagamento: "bonifico" });
            toast.success("Titolo incassato e movimento contabile creato");
            load();
        } catch { toast.error("Errore"); }
    };

    return (
        <div data-testid="titoli-page">
            <PageHeader title="Titoli" subtitle="Quietanze e premi: emessi, incassati, insoluti" />

            <div className="flex items-center gap-3 mb-4">
                <Select value={stato} onValueChange={setStato}>
                    <SelectTrigger className="w-48" data-testid="titoli-stato-filter"><SelectValue /></SelectTrigger>
                    <SelectContent>
                        <SelectItem value="all">Tutti gli stati</SelectItem>
                        <SelectItem value="da_incassare">Da incassare</SelectItem>
                        <SelectItem value="incassato">Incassati</SelectItem>
                        <SelectItem value="insoluto">Insoluti</SelectItem>
                        <SelectItem value="stornato">Stornati</SelectItem>
                    </SelectContent>
                </Select>
                <span className="text-sm text-slate-500 num ml-auto">{list ? `${list.length} titoli` : ""}</span>
            </div>

            <div className="bg-white border border-slate-200 rounded-md overflow-x-auto">
                {list === null ? <Loading /> : list.length === 0 ? <Empty /> : (
                    <table className="tbl w-full min-w-[900px]">
                        <thead>
                            <tr>
                                <th>Polizza</th>
                                <th>Tipo</th>
                                <th>Effetto</th>
                                <th>Scadenza</th>
                                <th>Stato</th>
                                <th className="text-right">Lordo</th>
                                <th className="text-right">Provv.</th>
                                <th>Incassato il</th>
                                <th>Mezzo</th>
                                <th></th>
                            </tr>
                        </thead>
                        <tbody>
                            {list.map((t) => (
                                <tr key={t.id} data-testid={`titolo-row-${t.id}`}>
                                    <td><Link to={`/polizze/${t.polizza_id}`} className="text-sky-700 hover:underline">{t.numero_polizza || t.polizza_id.slice(0, 8)}</Link></td>
                                    <td>{t.tipo}</td>
                                    <td className="num">{fmtDate(t.effetto)}</td>
                                    <td className="num">{fmtDate(t.scadenza)}</td>
                                    <td><StatusBadge stato={t.stato} /></td>
                                    <td className="num text-right font-medium">{fmtEur(t.importo_lordo)}</td>
                                    <td className="num text-right text-slate-600">{fmtEur(t.provvigioni)}</td>
                                    <td className="num">{fmtDate(t.data_incasso)}</td>
                                    <td className="text-xs text-slate-600">{t.mezzo_pagamento || "-"}</td>
                                    <td>
                                        {t.stato === "da_incassare" && (
                                            <Button size="sm" variant="outline" onClick={() => incassa(t.id)} data-testid={`titolo-incassa-${t.id}`}>
                                                Incassa
                                            </Button>
                                        )}
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                )}
            </div>
        </div>
    );
}
