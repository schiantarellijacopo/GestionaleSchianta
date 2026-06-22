import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { api, fmtDate, fmtEur } from "@/lib/api";
import { PageHeader, StatusBadge, Loading } from "@/components/Shared";
import { Card } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { ArrowLeft } from "lucide-react";
import { toast } from "sonner";

export default function PolizzaDetail() {
    const { id } = useParams();
    const [pol, setPol] = useState(null);

    const load = () => api.get(`/polizze/${id}`).then((r) => setPol(r.data));
    useEffect(() => { load(); /* eslint-disable-next-line */ }, [id]);

    if (!pol) return <Loading />;

    const incassa = async (tid) => {
        try {
            await api.post(`/titoli/${tid}/incassa`, { mezzo_pagamento: "bonifico" });
            toast.success("Titolo incassato");
            load();
        } catch (e) { toast.error("Errore: " + e.message); }
    };

    return (
        <div data-testid="polizza-detail-page">
            <Link to="/polizze" className="text-sm text-slate-500 hover:text-sky-700 inline-flex items-center gap-1 mb-3">
                <ArrowLeft size={14} /> Torna alle polizze
            </Link>
            <PageHeader
                title={`Polizza ${pol.numero_polizza}`}
                subtitle={`${pol.ramo} · ${pol.prodotto || "—"}`}
                actions={<StatusBadge stato={pol.stato} />}
            />

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 mb-6">
                <Card className="p-5 border-slate-200">
                    <div className="stat-label mb-1">Contraente</div>
                    <Link to={`/anagrafiche/${pol.contraente?.id}`} className="text-lg font-medium text-sky-700 hover:underline">
                        {pol.contraente?.ragione_sociale}
                    </Link>
                    <div className="text-xs text-slate-500 mt-1 num">{pol.contraente?.codice_fiscale || pol.contraente?.partita_iva || ""}</div>
                </Card>
                <Card className="p-5 border-slate-200">
                    <div className="stat-label mb-1">Compagnia</div>
                    <div className="text-lg font-medium text-slate-900">{pol.compagnia?.ragione_sociale}</div>
                    <div className="text-xs text-slate-500 mt-1">{pol.compagnia?.codice}</div>
                </Card>
                <Card className="p-5 border-slate-200">
                    <div className="grid grid-cols-2 gap-3">
                        <div>
                            <div className="stat-label">Effetto</div>
                            <div className="text-base num">{fmtDate(pol.effetto)}</div>
                        </div>
                        <div>
                            <div className="stat-label">Scadenza</div>
                            <div className="text-base num">{fmtDate(pol.scadenza)}</div>
                        </div>
                        <div>
                            <div className="stat-label">Premio lordo</div>
                            <div className="text-base num font-medium">{fmtEur(pol.premio_lordo)}</div>
                        </div>
                        <div>
                            <div className="stat-label">Provvigioni</div>
                            <div className="text-base num">{fmtEur(pol.provvigioni)}</div>
                        </div>
                    </div>
                </Card>
            </div>

            <Tabs defaultValue="titoli">
                <TabsList className="bg-slate-100">
                    <TabsTrigger value="titoli">Titoli ({pol.titoli?.length || 0})</TabsTrigger>
                    <TabsTrigger value="sinistri">Sinistri ({pol.sinistri?.length || 0})</TabsTrigger>
                </TabsList>

                <TabsContent value="titoli">
                    <Card className="border-slate-200 mt-4 overflow-hidden">
                        {pol.titoli?.length === 0 ? (
                            <div className="p-8 text-center text-slate-500 text-sm">Nessun titolo emesso.</div>
                        ) : (
                            <table className="tbl w-full">
                                <thead>
                                    <tr>
                                        <th>Tipo</th>
                                        <th>Effetto</th>
                                        <th>Scadenza</th>
                                        <th>Stato</th>
                                        <th className="text-right">Lordo</th>
                                        <th className="text-right">Netto</th>
                                        <th className="text-right">Imposte</th>
                                        <th>Pagato il</th>
                                        <th></th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {pol.titoli?.map((t) => (
                                        <tr key={t.id}>
                                            <td>{t.tipo}</td>
                                            <td className="num">{fmtDate(t.effetto)}</td>
                                            <td className="num">{fmtDate(t.scadenza)}</td>
                                            <td><StatusBadge stato={t.stato} /></td>
                                            <td className="num text-right">{fmtEur(t.importo_lordo)}</td>
                                            <td className="num text-right text-slate-600">{fmtEur(t.importo_netto)}</td>
                                            <td className="num text-right text-slate-600">{fmtEur(t.imposte)}</td>
                                            <td className="num">{fmtDate(t.data_incasso)}</td>
                                            <td>
                                                {t.stato === "da_incassare" && (
                                                    <Button size="sm" variant="outline" onClick={() => incassa(t.id)} data-testid={`incassa-${t.id}`}>
                                                        Incassa
                                                    </Button>
                                                )}
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        )}
                    </Card>
                </TabsContent>

                <TabsContent value="sinistri">
                    <Card className="border-slate-200 mt-4 overflow-hidden">
                        {pol.sinistri?.length === 0 ? (
                            <div className="p-8 text-center text-slate-500 text-sm">Nessun sinistro registrato.</div>
                        ) : (
                            <table className="tbl w-full">
                                <thead>
                                    <tr>
                                        <th>Numero</th>
                                        <th>Avvenimento</th>
                                        <th>Denuncia</th>
                                        <th>Luogo</th>
                                        <th>Stato</th>
                                        <th className="text-right">Riserva</th>
                                        <th className="text-right">Liquidazione</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {pol.sinistri?.map((s) => (
                                        <tr key={s.id}>
                                            <td className="num">{s.numero_sinistro}</td>
                                            <td className="num">{fmtDate(s.data_avvenimento)}</td>
                                            <td className="num">{fmtDate(s.data_denuncia)}</td>
                                            <td>{s.luogo}</td>
                                            <td><StatusBadge stato={s.stato} /></td>
                                            <td className="num text-right">{fmtEur(s.riserva)}</td>
                                            <td className="num text-right">{fmtEur(s.liquidazione)}</td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        )}
                    </Card>
                </TabsContent>
            </Tabs>
        </div>
    );
}
