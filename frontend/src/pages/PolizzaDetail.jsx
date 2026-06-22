import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { api, fmtDate, fmtEur } from "@/lib/api";
import { PageHeader, StatusBadge, Loading } from "@/components/Shared";
import { Card } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ArrowLeft, Car, ShieldCheck, Banknote, FileText, Info } from "lucide-react";
import { toast } from "sonner";

export default function PolizzaDetail() {
    const { id } = useParams();
    const [pol, setPol] = useState(null);
    const load = () => api.get(`/polizze/${id}`).then((r) => setPol(r.data));
    useEffect(() => { load(); /* eslint-disable-next-line */ }, [id]);
    if (!pol) return <Loading />;

    const incassa = async (tid) => {
        try { await api.post(`/titoli/${tid}/incassa`, { mezzo_pagamento: "bonifico" }); toast.success("Incassato"); load(); }
        catch { toast.error("Errore"); }
    };

    return (
        <div data-testid="polizza-detail-page">
            <Link to="/polizze" className="text-sm text-slate-500 hover:text-sky-700 inline-flex items-center gap-1 mb-3">
                <ArrowLeft size={14} /> Torna alle polizze
            </Link>

            {/* Header tipo Cattolica */}
            <Card className="border-slate-200 mb-4 overflow-hidden">
                <div className="bg-gradient-to-r from-sky-900 to-slate-900 text-slate-100 px-6 py-5 flex items-center justify-between flex-wrap gap-4">
                    <div>
                        <div className="text-[10px] uppercase tracking-widest text-sky-300">{pol.compagnia?.ragione_sociale || "—"}</div>
                        <div className="text-xl font-semibold mt-0.5">{pol.prodotto || pol.ramo}</div>
                        <div className="text-xs text-slate-300 mt-1">N. {pol.numero_polizza} · Mandato {pol.mandato || "—"}</div>
                    </div>
                    <div className="flex gap-6 text-xs">
                        <Hd label="Ultimo titolo" value={fmtDate(pol.titoli?.[0]?.data_incasso || pol.effetto)} />
                        <Hd label="Stato" value={<StatusBadge stato={pol.stato} />} />
                        <Hd label="Copertura" value={pol.scadenza_copertura || pol.scadenza} />
                        <Hd label="Operatore" value={pol.collaboratore_id ? pol.collaboratore_id.slice(0, 6) : "—"} />
                    </div>
                </div>
                <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-x-6 gap-y-3 px-6 py-4 text-sm">
                    <F label="N° contratto" value={pol.numero_polizza} mono />
                    <F label="Sostituisce" value={pol.sostituisce_polizza} />
                    <F label="Compagnia" value={pol.compagnia?.ragione_sociale} />
                    <F label="Contraente" value={<Link to={`/anagrafiche/${pol.contraente?.id}`} className="text-sky-700 hover:underline">{pol.contraente?.ragione_sociale}</Link>} />
                    <F label="Iter" value={pol.iter_status} />
                    <F label="Frazionamento" value={`${pol.frazionamento}${pol.tacito_rinnovo ? " · tacito rinnovo" : ""}`} />
                    <F label="Effetto" value={fmtDate(pol.effetto)} />
                    <F label="Presa in carico" value={fmtDate(pol.presa_in_carico)} />
                    <F label="Prossima quietanza" value={fmtDate(pol.prossima_quietanza)} />
                    <F label="Scad. copertura" value={fmtDate(pol.scadenza_copertura || pol.scadenza)} />
                    <F label="Scad. contratto" value={fmtDate(pol.scadenza)} />
                    <F label="Termini mora" value={pol.termini_mora_giorni ? `${pol.termini_mora_giorni} gg` : "—"} />
                    <F label="Termini disdetta" value={pol.termini_disdetta_giorni ? `${pol.termini_disdetta_giorni} gg` : "—"} />
                    <F label="Oggetto assicurato" value={pol.oggetto_assicurato || pol.targa} />
                    <F label="Premio lordo" value={<span className="font-semibold text-slate-900 num">{fmtEur(pol.premio_lordo)}</span>} />
                    <F label="Provvigioni" value={fmtEur(pol.provvigioni)} />
                </div>
            </Card>

            <Tabs defaultValue="veicolo">
                <TabsList className="bg-slate-100 flex-wrap h-auto">
                    {pol.ramo === "RCA" && <TabsTrigger value="veicolo"><Car size={13} className="mr-1" />Veicolo</TabsTrigger>}
                    <TabsTrigger value="garanzie"><ShieldCheck size={13} className="mr-1" />Garanzie</TabsTrigger>
                    <TabsTrigger value="provvigioni"><Banknote size={13} className="mr-1" />Provvigioni</TabsTrigger>
                    <TabsTrigger value="titoli"><FileText size={13} className="mr-1" />Titoli ({pol.titoli?.length || 0})</TabsTrigger>
                    <TabsTrigger value="altri"><Info size={13} className="mr-1" />Altri dati</TabsTrigger>
                </TabsList>

                {pol.ramo === "RCA" && (
                    <TabsContent value="veicolo">
                        <Card className="p-6 border-slate-200 mt-4">
                            <SezioneTitolo titolo="Dati veicolo" />
                            <Grid items={[
                                ["Targa", pol.targa],
                                ["Marca", pol.veicolo_marca],
                                ["Modello", pol.veicolo_modello],
                                ["Tipo veicolo", pol.veicolo_tipo],
                                ["Alimentazione", pol.veicolo_alimentazione],
                                ["Tipo uso", pol.veicolo_uso],
                                ["Immatricolazione", fmtDate(pol.veicolo_data_immatricolazione)],
                                ["CV fiscali", pol.veicolo_cv_fiscali],
                                ["KW", pol.veicolo_kw],
                                ["Quintali P.C.", pol.veicolo_quintali],
                                ["Cilindrata", pol.veicolo_cilindrata],
                                ["Numero posti", pol.veicolo_posti],
                                ["Gancio traino", pol.veicolo_gancio_traino ? "SÌ" : "NO"],
                                ["Targa rimorchio", pol.veicolo_targa_rimorchio],
                            ]} />
                            <SezioneTitolo titolo="Dati associazione contratto" extra />
                            <Grid items={[
                                ["Tipo tariffa", pol.tipo_tariffa],
                                ["B-M provenienza", pol.bm_provenienza],
                                ["B-M assegnata", pol.bm_assegnata],
                                ["B-M ass. CU", pol.bm_assegnata_cu],
                                ["Pejus", pol.pejus],
                                ["Franchigia", fmtEur(pol.franchigia)],
                                ["Valore veicolo", fmtEur(pol.valore_veicolo)],
                                ["Valore residuo", fmtEur(pol.valore_residuo_veicolo)],
                                ["Valore accessori", fmtEur(pol.valore_accessori)],
                                ["Guida esperta", pol.guida_esperta ? "SÌ" : "NO"],
                                ["Guida esclusiva", pol.guida_esclusiva ? "SÌ" : "NO"],
                                ["Rinuncia rivalsa", pol.rinuncia_rivalsa ? "SÌ" : "NO"],
                                ["Intestatario", pol.intestatario],
                                ["Prov. intestatario", pol.provincia_intestatario],
                                ["Massimali", pol.massimali],
                            ]} />
                        </Card>
                    </TabsContent>
                )}

                <TabsContent value="garanzie">
                    <Card className="border-slate-200 mt-4 overflow-hidden">
                        {(!pol.garanzie || pol.garanzie.length === 0) ? (
                            <div className="p-8 text-center text-slate-500 text-sm">Nessuna garanzia di dettaglio importata.</div>
                        ) : (
                            <table className="tbl w-full">
                                <thead>
                                    <tr>
                                        <th>Garanzia</th>
                                        <th className="text-right">Netto</th>
                                        <th className="text-right">Accessori</th>
                                        <th className="text-right">Imposte</th>
                                        <th className="text-right">SSN</th>
                                        <th className="text-right">Lordo</th>
                                        <th className="text-right">Diritti</th>
                                        <th className="text-right">Provvigione</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {pol.garanzie.map((g, i) => (
                                        <tr key={i}>
                                            <td className="font-medium">{g.garanzia || "—"}</td>
                                            <td className="num text-right">{fmtEur(g.netto)}</td>
                                            <td className="num text-right text-slate-600">{fmtEur(g.accessori)}</td>
                                            <td className="num text-right text-slate-600">{fmtEur(g.imposte)}</td>
                                            <td className="num text-right text-slate-600">{fmtEur(g.ssn)}</td>
                                            <td className="num text-right font-semibold">{fmtEur(g.lordo)}</td>
                                            <td className="num text-right text-slate-600">{fmtEur(g.diritti)}</td>
                                            <td className="num text-right text-emerald-700">{fmtEur(g.provvigione)}</td>
                                        </tr>
                                    ))}
                                </tbody>
                                <tfoot>
                                    <tr className="bg-slate-50 font-semibold">
                                        <td>TOTALE</td>
                                        <td className="num text-right">{fmtEur(pol.garanzie.reduce((s, g) => s + (g.netto || 0), 0))}</td>
                                        <td className="num text-right">{fmtEur(pol.garanzie.reduce((s, g) => s + (g.accessori || 0), 0))}</td>
                                        <td className="num text-right">{fmtEur(pol.garanzie.reduce((s, g) => s + (g.imposte || 0), 0))}</td>
                                        <td className="num text-right">{fmtEur(pol.garanzie.reduce((s, g) => s + (g.ssn || 0), 0))}</td>
                                        <td className="num text-right">{fmtEur(pol.premio_lordo)}</td>
                                        <td className="num text-right">{fmtEur(pol.diritti || 0)}</td>
                                        <td className="num text-right">{fmtEur(pol.provvigioni)}</td>
                                    </tr>
                                </tfoot>
                            </table>
                        )}
                    </Card>

                    {pol.addizionali && pol.addizionali.length > 0 && (
                        <Card className="border-slate-200 mt-4 p-6">
                            <SezioneTitolo titolo="Addizionali" />
                            <Grid items={pol.addizionali.map((a) => [a.descrizione, fmtEur(a.importo)])} />
                        </Card>
                    )}
                </TabsContent>

                <TabsContent value="provvigioni">
                    <Card className="p-6 border-slate-200 mt-4">
                        <Grid items={[
                            ["Provv. struttura rata", fmtEur(pol.provv_struttura)],
                            ["Provvigioni totali", <span className="font-semibold text-emerald-700 num">{fmtEur(pol.provvigioni)}</span>],
                        ]} />
                        {pol.provvigioni_operatori?.length > 0 && (
                            <>
                                <SezioneTitolo titolo="Provvigioni operatori" extra />
                                <table className="tbl w-full">
                                    <thead><tr><th>Operatore</th><th className="text-right">Provvigione</th><th className="text-right">Su addizionali</th></tr></thead>
                                    <tbody>
                                        {pol.provvigioni_operatori.map((o, i) => (
                                            <tr key={i}>
                                                <td>{o.operatore_nome}</td>
                                                <td className="num text-right">{fmtEur(o.provvigione)}</td>
                                                <td className="num text-right">{fmtEur(o.provvigione_addizionali)}</td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            </>
                        )}
                    </Card>
                </TabsContent>

                <TabsContent value="titoli">
                    <Card className="border-slate-200 mt-4 overflow-hidden">
                        {pol.titoli?.length === 0 ? (
                            <div className="p-8 text-center text-slate-500 text-sm">Nessun titolo.</div>
                        ) : (
                            <table className="tbl w-full">
                                <thead><tr><th>Tipo</th><th>Effetto</th><th>Scadenza</th><th>Stato</th><th className="text-right">Lordo</th><th className="text-right">Provv.</th><th>Pagato il</th><th></th></tr></thead>
                                <tbody>
                                    {pol.titoli?.map((t) => (
                                        <tr key={t.id}>
                                            <td>{t.tipo}</td>
                                            <td className="num">{fmtDate(t.effetto)}</td>
                                            <td className="num">{fmtDate(t.scadenza)}</td>
                                            <td><StatusBadge stato={t.stato} /></td>
                                            <td className="num text-right font-medium">{fmtEur(t.importo_lordo)}</td>
                                            <td className="num text-right text-slate-600">{fmtEur(t.provvigioni)}</td>
                                            <td className="num">{fmtDate(t.data_incasso)}</td>
                                            <td>{t.stato === "da_incassare" && (
                                                <button onClick={() => incassa(t.id)} className="text-xs text-emerald-700 hover:underline">Incassa</button>
                                            )}</td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        )}
                    </Card>
                </TabsContent>

                <TabsContent value="altri">
                    <Card className="p-6 border-slate-200 mt-4 space-y-5">
                        <div>
                            <SezioneTitolo titolo="Caratteristiche" />
                            <div className="text-sm whitespace-pre-line">{pol.caratteristiche || "—"}</div>
                        </div>
                        <div>
                            <SezioneTitolo titolo="Da restituire" extra />
                            <div className="text-sm whitespace-pre-line">{pol.da_restituire || "—"}</div>
                        </div>
                        <div>
                            <SezioneTitolo titolo="Note interne" extra />
                            <div className="text-sm whitespace-pre-line">{pol.note_interne || pol.note || "—"}</div>
                        </div>
                    </Card>
                </TabsContent>
            </Tabs>
        </div>
    );
}

function Hd({ label, value }) {
    return (
        <div>
            <div className="text-[10px] uppercase tracking-widest text-sky-300/80">{label}</div>
            <div className="text-sm mt-0.5">{value || "—"}</div>
        </div>
    );
}

function F({ label, value, mono }) {
    return (
        <div>
            <div className="text-[10px] uppercase tracking-widest text-slate-500">{label}</div>
            <div className={`text-sm mt-0.5 text-slate-900 ${mono ? "num font-medium" : ""}`}>{value || "—"}</div>
        </div>
    );
}

function SezioneTitolo({ titolo, extra }) {
    return (
        <div className={`text-xs uppercase tracking-widest font-semibold text-slate-500 ${extra ? "mt-6" : ""} mb-3 pb-1 border-b border-slate-100`}>
            {titolo}
        </div>
    );
}

function Grid({ items }) {
    return (
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-x-6 gap-y-3">
            {items.map(([k, v], i) => (
                <div key={i}>
                    <div className="text-[10px] uppercase tracking-widest text-slate-500">{k}</div>
                    <div className="text-sm text-slate-900 mt-0.5">{v || "—"}</div>
                </div>
            ))}
        </div>
    );
}
