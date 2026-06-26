import { useEffect, useState } from "react";
import { useParams, Link, useNavigate } from "react-router-dom";
import { api, fmtDate, fmtEur } from "@/lib/api";
import { PageHeader, StatusBadge, Loading } from "@/components/Shared";
import { Card } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import {
    Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from "@/components/ui/dialog";
import { ArrowLeft, Car, ShieldCheck, Banknote, FileText, Info, Pencil, Trash2, AlertTriangle, Zap } from "lucide-react";
import { toast } from "sonner";
import useMezziPagamento from "@/hooks/useMezziPagamento";
import { useAuth } from "@/contexts/AuthContext";
import DialogIncassoCopertura from "@/components/DialogIncassoCopertura";
import LibroMatricolaTab from "@/components/LibroMatricolaTab";
import TitoloDialog from "@/components/TitoloDialog";
import DocumentiPolizzaTab from "@/components/DocumentiPolizzaTab";
import AzioniPolizzaTab from "@/components/AzioniPolizzaTab";
import AllegatiCell from "@/components/AllegatiCell";

export default function PolizzaDetail() {
    const { id } = useParams();
    const navigate = useNavigate();
    const { user } = useAuth();
    const [pol, setPol] = useState(null);
    const [editOpen, setEditOpen] = useState(false);
    const [conti, setConti] = useState([]);
    const [paying, setPaying] = useState(null);
    const [titoloEditing, setTitoloEditing] = useState(null);
    const load = () => api.get(`/polizze/${id}`).then((r) => setPol(r.data));
    useEffect(() => { load(); /* eslint-disable-next-line */ }, [id]);
    useEffect(() => {
        api.get("/librerie/conti-cassa").then((r) => setConti(r.data || [])).catch(() => {});
    }, []);
    if (!pol) return <Loading />;

    const canEdit = ["admin", "collaboratore", "dipendente"].includes(user?.role);
    const canDelete = user?.role === "admin";

    const incassa = async (tid) => {
        try { await api.post(`/titoli/${tid}/incassa`, { mezzo_pagamento: "bonifico" }); toast.success("Incassato"); load(); }
        catch { toast.error("Errore"); }
    };

    const handleDelete = async () => {
        if (!window.confirm(`Eliminare definitivamente la polizza N. ${pol.numero_polizza}?\n\nVerranno eliminati anche tutti i titoli e sinistri collegati. Operazione non reversibile.`)) return;
        try {
            await api.delete(`/polizze/${id}`);
            toast.success("Polizza eliminata");
            navigate("/polizze");
        } catch (e) {
            toast.error(e.response?.data?.detail || "Errore");
        }
    };

    return (
        <div data-testid="polizza-detail-page">
            <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
                <Link to="/polizze" className="text-sm text-slate-500 hover:text-sky-700 inline-flex items-center gap-1">
                    <ArrowLeft size={14} /> Torna alle polizze
                </Link>
                <div className="flex gap-2">
                    {canEdit && (
                        <Button variant="outline" size="sm" onClick={() => setEditOpen(true)} data-testid="pol-edit-button">
                            <Pencil size={14} className="mr-1" /> Modifica polizza
                        </Button>
                    )}
                    {canDelete && (
                        <Button variant="outline" size="sm" onClick={handleDelete}
                                className="text-rose-700 hover:bg-rose-50 hover:text-rose-800" data-testid="pol-delete-button">
                            <Trash2 size={14} className="mr-1" /> Elimina
                        </Button>
                    )}
                </div>
            </div>

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
                        <Hd label="Collaboratore" value={pol.collaboratore_nome || (pol.collaboratore_id ? pol.collaboratore_id.slice(0, 6) : "—")} />
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
                    <F label="Premio netto" value={fmtEur(pol.premio_netto)} />
                    <F label="Tasse" value={fmtEur(pol.premio_tasse)} />
                    <F label="Imposte" value={fmtEur(pol.premio_imposte)} />
                    <F label="SSN" value={fmtEur(pol.premio_ssn)} />
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
                    <TabsTrigger value="documenti" data-testid="tab-documenti">
                        <FileText size={13} className="mr-1" />Documenti
                    </TabsTrigger>
                    <TabsTrigger value="sinistri" data-testid="tab-sinistri">
                        <AlertTriangle size={13} className="mr-1" />Sinistri ({pol.sinistri?.length || 0})
                    </TabsTrigger>
                    {pol.is_libro_matricola && (
                        <TabsTrigger value="libro-matricola" data-testid="tab-libro-matricola">
                            <Car size={13} className="mr-1" />Libro Matricola
                        </TabsTrigger>
                    )}
                    <TabsTrigger value="altri"><Info size={13} className="mr-1" />Altri dati</TabsTrigger>
                    <TabsTrigger value="azioni" data-testid="tab-azioni" className="text-rose-700 data-[state=active]:bg-rose-50">
                        <Zap size={13} className="mr-1" />Azioni
                    </TabsTrigger>
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
                            [
                                "Provv. totali",
                                <span key="provv-totali" className="font-semibold text-emerald-700 num" data-testid="provv-totali">
                                    {fmtEur(pol.provvigione_totale ?? pol.provvigioni ?? 0)}
                                </span>,
                            ],
                            [
                                "Provv. collaboratore",
                                <span key="provv-collab" className="num font-semibold text-sky-700" data-testid="provv-collab">
                                    {fmtEur(pol.provvigione_collaboratore || 0)}
                                    {pol.provvigione_pct_collab > 0 && (
                                        <span className="text-[10px] ml-2 text-slate-500 font-normal">
                                            ({pol.provvigione_pct_collab}% — {pol.provvigione_schema_nome || "schema"})
                                        </span>
                                    )}
                                </span>,
                            ],
                            [
                                "Provv. margine (agenzia)",
                                <span key="provv-margine" className="num font-semibold text-amber-700" data-testid="provv-margine">
                                    {fmtEur(pol.provvigione_margine || ((pol.provvigione_totale ?? pol.provvigioni ?? 0) - (pol.provvigione_collaboratore || 0)))}
                                </span>,
                            ],
                        ]} />
                        {pol.collaboratore_nome && (
                            <div className="mt-2 text-xs text-slate-600">
                                Collaboratore polizza: <strong>{pol.collaboratore_nome}</strong>
                            </div>
                        )}
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
                        <div className="p-3 border-b border-slate-200 flex justify-between items-center bg-slate-50">
                            <div className="text-xs text-slate-600">
                                {pol.titoli?.length || 0} titoli su questa polizza
                            </div>
                            <Button
                                size="sm"
                                className="bg-sky-700 hover:bg-sky-800"
                                onClick={() => setTitoloEditing({ _new: true, polizza_id: pol.id })}
                                data-testid="new-titolo-btn"
                            >+ Nuovo titolo</Button>
                        </div>
                        {pol.titoli?.length === 0 ? (
                            <div className="p-8 text-center text-slate-500 text-sm">Nessun titolo.</div>
                        ) : (
                            <table className="tbl w-full">
                                <thead><tr><th>Tipo</th><th>Effetto</th><th>Scadenza</th><th>Stato</th><th className="text-right">Lordo</th><th className="text-right">Provv. tot.</th><th className="text-right">Provv. collab.</th><th className="text-right">Margine</th><th>Coperto il</th><th>Pagato il</th><th className="text-center">Allegati</th><th className="text-center w-40">Azioni</th></tr></thead>
                                <tbody>
                                    {pol.titoli?.map((t) => (
                                        <tr key={t.id}
                                            className={`hover:bg-sky-50 cursor-pointer ${t.polizza_origine_id ? "bg-amber-50/40" : ""}`}
                                            onClick={(e) => {
                                                // ignora click sui pulsanti azione
                                                if (e.target.closest("button")) return;
                                                setTitoloEditing(t);
                                            }}
                                            data-testid={`titolo-row-${t.id}`}
                                        >
                                            <td>
                                                {t.tipo}
                                                {t.polizza_origine_numero && (
                                                    <div className="text-[9px] text-amber-700 italic" title="Titolo della polizza precedente (sostituita)">
                                                        polizza prec. {t.polizza_origine_numero}
                                                    </div>
                                                )}
                                            </td>
                                            <td className="num">{fmtDate(t.effetto)}</td>
                                            <td className="num">{fmtDate(t.scadenza)}</td>
                                            <td><StatusBadge stato={t.stato} titolo_coperto={t.titolo_coperto} data_copertura={t.data_copertura} /></td>
                                            <td className="num text-right font-medium">{fmtEur(t.importo_lordo)}</td>
                                            <td className="num text-right text-slate-600">{fmtEur(t.provvigione_totale ?? t.provvigioni ?? 0)}</td>
                                            <td className="num text-right text-sky-700 font-medium" data-testid={`titolo-provv-collab-${t.id}`}>{fmtEur(t.provvigione_collaboratore || 0)}</td>
                                            <td className="num text-right text-amber-700 font-medium" data-testid={`titolo-provv-margine-${t.id}`}>{fmtEur(t.provvigione_margine ?? ((t.provvigione_totale ?? t.provvigioni ?? 0) - (t.provvigione_collaboratore || 0)))}</td>
                                            <td className="num text-xs text-emerald-700" data-testid={`titolo-coperto-${t.id}`}>{t.data_copertura ? fmtDate(t.data_copertura) : (t.coperto_fino_a ? fmtDate(t.coperto_fino_a) : "—")}</td>
                                            <td className="num text-xs" data-testid={`titolo-pagato-${t.id}`}>{t.stato === "incassato" ? fmtDate(t.data_incasso) : "—"}</td>
                                            <td className="text-center" onClick={(e) => e.stopPropagation()}>
                                                <AllegatiCell
                                                    entita_tipo="titolo"
                                                    entita_id={t.id}
                                                    count={t.allegati_count}
                                                    hint={t.data_incasso ? "Allega ricevuta bonifico / assegno" : "Allega documento"}
                                                    onChange={load}
                                                />
                                            </td>
                                            <td className="text-center">
                                                <div className="flex gap-1 justify-center">
                                                    {t.stato !== "incassato" && t.stato !== "stornato" && (
                                                        <Button
                                                            size="sm"
                                                            className="h-7 px-2 text-xs bg-emerald-600 hover:bg-emerald-700"
                                                            onClick={() => setPaying({
                                                                ...t,
                                                                numero_polizza: pol.numero_polizza,
                                                                ramo: pol.ramo,
                                                                contraente_id: pol.contraente_id,
                                                                contraente_nome: pol.contraente?.ragione_sociale,
                                                                compagnia_nome: pol.compagnia?.ragione_sociale,
                                                            })}
                                                            data-testid={`pol-titolo-incassa-${t.id}`}
                                                            title="Incasso/Copertura"
                                                        >€</Button>
                                                    )}
                                                    <Button
                                                        size="sm" variant="outline"
                                                        className="h-7 px-2 text-xs"
                                                        onClick={() => setTitoloEditing(t)}
                                                        data-testid={`titolo-edit-${t.id}`}
                                                        title="Modifica"
                                                    >✎</Button>
                                                    <Button
                                                        size="sm" variant="outline"
                                                        className="h-7 px-2 text-xs text-rose-700 hover:bg-rose-50"
                                                        onClick={async () => {
                                                            if (!window.confirm(`Eliminare il titolo ${t.tipo} ${fmtDate(t.effetto)}?`)) return;
                                                            try {
                                                                await api.delete(`/titoli/${t.id}`);
                                                                toast.success("Titolo eliminato");
                                                                load();
                                                            } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
                                                        }}
                                                        data-testid={`titolo-delete-${t.id}`}
                                                        title="Elimina"
                                                    >🗑</Button>
                                                </div>
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        )}
                    </Card>
                </TabsContent>

                {pol.is_libro_matricola && (
                    <TabsContent value="libro-matricola">
                        <LibroMatricolaTab polizzaId={pol.id} />
                    </TabsContent>
                )}

                <TabsContent value="documenti">
                    <DocumentiPolizzaTab polizzaId={pol.id} canEdit={canEdit} onAfterOCR={load} />
                </TabsContent>

                <TabsContent value="sinistri">
                    <Card className="border-slate-200 mt-4 overflow-hidden" data-testid="sinistri-tab-card">
                        <div className="p-3 border-b border-slate-200 flex justify-between items-center bg-slate-50">
                            <div className="text-xs text-slate-600">
                                {pol.sinistri?.length || 0} sinistri su questa polizza
                            </div>
                            <Link
                                to={`/sinistri?polizza_id=${pol.id}`}
                                className="text-xs text-sky-700 hover:underline"
                                data-testid="sinistri-fulllist-link"
                            >
                                Apri elenco completo →
                            </Link>
                        </div>
                        {(!pol.sinistri || pol.sinistri.length === 0) ? (
                            <div className="p-8 text-center text-slate-500 text-sm">Nessun sinistro registrato su questa polizza.</div>
                        ) : (
                            <table className="tbl w-full">
                                <thead><tr>
                                    <th>N. sinistro</th>
                                    <th>Data avv.</th>
                                    <th>Data den.</th>
                                    <th>Stato</th>
                                    <th>Luogo</th>
                                    <th className="text-right">Riserva</th>
                                    <th className="text-right">Liquidato</th>
                                    <th className="text-center w-24">Azione</th>
                                </tr></thead>
                                <tbody>
                                    {pol.sinistri.map((s) => (
                                        <tr key={s.id} className="hover:bg-rose-50/40" data-testid={`sinistro-row-${s.id}`}>
                                            <td className="num font-medium text-rose-700">{s.numero_sinistro || "—"}</td>
                                            <td className="num">{fmtDate(s.data_avvenimento)}</td>
                                            <td className="num">{fmtDate(s.data_denuncia)}</td>
                                            <td><StatusBadge stato={s.stato} /></td>
                                            <td className="text-xs text-slate-600">{s.luogo || "—"}</td>
                                            <td className="num text-right">{fmtEur(s.riserva || 0)}</td>
                                            <td className="num text-right text-emerald-700 font-medium">{fmtEur(s.liquidazione || 0)}</td>
                                            <td className="text-center">
                                                <Link
                                                    to={`/sinistri?focus=${s.id}`}
                                                    className="text-xs text-sky-700 hover:underline"
                                                    data-testid={`sinistro-open-${s.id}`}
                                                >
                                                    Apri
                                                </Link>
                                            </td>
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

                <TabsContent value="azioni">
                    <AzioniPolizzaTab polizza={pol} onChanged={load} canEdit={canEdit} />
                </TabsContent>
            </Tabs>
            {editOpen && (
                <EditPolizzaDialog pol={pol} onClose={() => setEditOpen(false)} onSaved={() => { setEditOpen(false); load(); }} />
            )}
            {paying && (
                <DialogIncassoCopertura
                    titolo={paying}
                    conti={conti}
                    onClose={() => { setPaying(null); load(); }}
                />
            )}
            {titoloEditing && (
                <TitoloDialog
                    titolo={titoloEditing}
                    conti={conti}
                    onClose={() => { setTitoloEditing(null); load(); }}
                    onDelete={() => { setTitoloEditing(null); load(); }}
                />
            )}
        </div>
    );
}

function EditPolizzaDialog({ pol, onClose, onSaved }) {
    const { mezzi } = useMezziPagamento();
    const [collaboratori, setCollaboratori] = useState([]);
    const [rami, setRami] = useState([]);
    const [prodotti, setProdotti] = useState([]);
    useEffect(() => {
        api.get("/auth/users", { params: { role: "collaboratore" } })
            .then((r) => setCollaboratori(r.data || []))
            .catch(() => setCollaboratori([]));
        api.get("/librerie/rami").then((r) => setRami(r.data || []));
    }, []);
    const [f, setF] = useState({
        numero_polizza: pol.numero_polizza || "",
        stato: pol.stato || "attiva",
        ramo: pol.ramo || "",
        prodotto: pol.prodotto || "",
        collaboratore_id: pol.collaboratore_id || "",
        effetto: pol.effetto || "",
        scadenza: pol.scadenza || "",
        scadenza_copertura: pol.scadenza_copertura || "",
        prossima_quietanza: pol.prossima_quietanza || "",
        frazionamento: pol.frazionamento || "annuale",
        tacito_rinnovo: !!pol.tacito_rinnovo,
        termini_mora_giorni: pol.termini_mora_giorni ?? 15,
        termini_disdetta_giorni: pol.termini_disdetta_giorni ?? 0,
        mandato: pol.mandato || "",
        sostituisce_polizza: pol.sostituisce_polizza || "",
        iter_status: pol.iter_status || "",
        oggetto_assicurato: pol.oggetto_assicurato || "",
        premio_netto: pol.premio_netto || 0,
        premio_tasse: pol.premio_tasse || 0,
        premio_imposte: pol.premio_imposte || 0,
        premio_ssn: pol.premio_ssn || 0,
        premio_lordo: pol.premio_lordo || 0,
        provvigioni: pol.provvigioni || 0,
        targa: pol.targa || "",
        mezzo_pagamento_preferito: pol.mezzo_pagamento_preferito || "",
        veicolo_marca: pol.veicolo_marca || "",
        veicolo_modello: pol.veicolo_modello || "",
        veicolo_tipo: pol.veicolo_tipo || "",
        veicolo_alimentazione: pol.veicolo_alimentazione || "",
        veicolo_uso: pol.veicolo_uso || "",
        veicolo_data_immatricolazione: pol.veicolo_data_immatricolazione || "",
        veicolo_cv_fiscali: pol.veicolo_cv_fiscali || "",
        veicolo_kw: pol.veicolo_kw || "",
        veicolo_cilindrata: pol.veicolo_cilindrata || "",
        veicolo_posti: pol.veicolo_posti || "",
        veicolo_quintali: pol.veicolo_quintali ?? "",
        veicolo_gancio_traino: !!pol.veicolo_gancio_traino,
        veicolo_targa_rimorchio: pol.veicolo_targa_rimorchio || "",
        // Dati associazione contratto (RCA)
        tipo_tariffa: pol.tipo_tariffa || "",
        bm_provenienza: pol.bm_provenienza || "",
        bm_assegnata: pol.bm_assegnata || "",
        bm_assegnata_cu: pol.bm_assegnata_cu || "",
        pejus: pol.pejus ?? "",
        franchigia: pol.franchigia ?? 0,
        valore_veicolo: pol.valore_veicolo ?? 0,
        valore_residuo_veicolo: pol.valore_residuo_veicolo ?? 0,
        valore_accessori: pol.valore_accessori ?? 0,
        guida_esperta: !!pol.guida_esperta,
        guida_esclusiva: !!pol.guida_esclusiva,
        rinuncia_rivalsa: !!pol.rinuncia_rivalsa,
        intestatario: pol.intestatario || "",
        provincia_intestatario: pol.provincia_intestatario || "",
        massimali: pol.massimali || "",
        note: pol.note || "",
    });
    const set = (k, v) => setF((p) => ({ ...p, [k]: v }));

    const save = async () => {
        try {
            const payload = { ...f };
            ["premio_netto", "premio_tasse", "premio_imposte", "premio_ssn", "premio_lordo",
             "provvigioni", "termini_mora_giorni", "termini_disdetta_giorni",
             "pejus", "franchigia", "valore_veicolo", "valore_residuo_veicolo", "valore_accessori"].forEach((k) => {
                if (payload[k] !== "" && payload[k] !== null && payload[k] !== undefined) {
                    payload[k] = parseFloat(payload[k]) || 0;
                }
            });
            // Quintali numeric (nullable)
            if (payload.veicolo_quintali === "" || payload.veicolo_quintali === null) {
                payload.veicolo_quintali = null;
            } else if (payload.veicolo_quintali !== undefined) {
                payload.veicolo_quintali = parseFloat(payload.veicolo_quintali) || 0;
            }
            await api.put(`/polizze/${pol.id}`, payload);
            toast.success("Polizza aggiornata");
            onSaved();
        } catch (e) {
            toast.error(e.response?.data?.detail || "Errore");
        }
    };

    // Carica prodotti quando cambia il ramo
    useEffect(() => {
        if (!f.ramo) { setProdotti([]); return; }
        api.get("/librerie/prodotti", { params: { ramo: f.ramo, attivi: true } })
            .then((r) => setProdotti(r.data || []))
            .catch(() => setProdotti([]));
    }, [f.ramo]);

    const isRCA = (f.ramo || "").toUpperCase().includes("RCA");

    return (
        <Dialog open onOpenChange={(o) => !o && onClose()}>
            <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto">
                <DialogHeader><DialogTitle>Modifica polizza {pol.numero_polizza}</DialogTitle></DialogHeader>
                <Tabs defaultValue="anagrafica" className="py-2">
                    <TabsList className="bg-slate-100">
                        <TabsTrigger value="anagrafica">Anagrafica</TabsTrigger>
                        <TabsTrigger value="economici">Economici</TabsTrigger>
                        {isRCA && <TabsTrigger value="veicolo">Veicolo</TabsTrigger>}
                        <TabsTrigger value="altri">Altri</TabsTrigger>
                    </TabsList>

                    <TabsContent value="anagrafica">
                        <div className="grid grid-cols-2 gap-3 py-3">
                            <div><Label>N. polizza</Label><Input value={f.numero_polizza} onChange={(e) => set("numero_polizza", e.target.value)} data-testid="edit-pol-numero" /></div>
                            <div>
                                <Label>Stato</Label>
                                <Select value={f.stato} onValueChange={(v) => set("stato", v)}>
                                    <SelectTrigger><SelectValue /></SelectTrigger>
                                    <SelectContent>
                                        {["attiva", "sospesa", "in_emissione", "scaduta", "annullata"].map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}
                                    </SelectContent>
                                </Select>
                            </div>
                            <div>
                                <Label>Ramo</Label>
                                <Select value={f.ramo || ""} onValueChange={(v) => { set("ramo", v); set("prodotto", ""); }}>
                                    <SelectTrigger data-testid="edit-pol-ramo"><SelectValue placeholder="Seleziona ramo" /></SelectTrigger>
                                    <SelectContent>
                                        {rami.map((r) => (
                                            <SelectItem key={r.id || r.nome} value={r.nome}>{r.nome}</SelectItem>
                                        ))}
                                    </SelectContent>
                                </Select>
                            </div>
                            <div>
                                <Label>Prodotto</Label>
                                <Select
                                    value={f.prodotto || ""}
                                    onValueChange={(v) => set("prodotto", v)}
                                    disabled={!f.ramo}
                                >
                                    <SelectTrigger data-testid="edit-pol-prodotto">
                                        <SelectValue placeholder={f.ramo ? (prodotti.length ? "Seleziona prodotto" : "Nessun prodotto per questo ramo") : "Scegli prima un ramo"} />
                                    </SelectTrigger>
                                    <SelectContent>
                                        {prodotti.map((p) => (
                                            <SelectItem key={p.id || p.nome} value={p.nome}>{p.nome}</SelectItem>
                                        ))}
                                    </SelectContent>
                                </Select>
                            </div>
                            <div>
                                <Label>Collaboratore (Operatore)</Label>
                                <Select
                                    value={f.collaboratore_id || "__none__"}
                                    onValueChange={(v) => set("collaboratore_id", v === "__none__" ? "" : v)}
                                >
                                    <SelectTrigger data-testid="edit-pol-collab"><SelectValue /></SelectTrigger>
                                    <SelectContent>
                                        <SelectItem value="__none__">— nessuno —</SelectItem>
                                        {collaboratori.map((c) => (
                                            <SelectItem key={c.id} value={c.id}>{c.name || c.email}</SelectItem>
                                        ))}
                                    </SelectContent>
                                </Select>
                            </div>
                            <div><Label>Effetto</Label><Input type="date" value={f.effetto} onChange={(e) => set("effetto", e.target.value)} /></div>
                            <div><Label>Scadenza</Label><Input type="date" value={f.scadenza} onChange={(e) => set("scadenza", e.target.value)} /></div>
                            <div><Label>Scad. copertura</Label><Input type="date" value={f.scadenza_copertura} onChange={(e) => set("scadenza_copertura", e.target.value)} /></div>
                            <div><Label>Prossima quietanza</Label><Input type="date" value={f.prossima_quietanza} onChange={(e) => set("prossima_quietanza", e.target.value)} /></div>
                            <div>
                                <Label>Frazionamento</Label>
                                <Select value={f.frazionamento} onValueChange={(v) => set("frazionamento", v)}>
                                    <SelectTrigger><SelectValue /></SelectTrigger>
                                    <SelectContent>
                                        {["annuale", "semestrale", "quadrimestrale", "trimestrale", "mensile", "unica"].map((s) => <SelectItem key={s} value={s}>{s}</SelectItem>)}
                                    </SelectContent>
                                </Select>
                            </div>
                            <div className="flex items-center gap-2 mt-6">
                                <input type="checkbox" id="tacito" checked={f.tacito_rinnovo} onChange={(e) => set("tacito_rinnovo", e.target.checked)} />
                                <Label htmlFor="tacito" className="cursor-pointer">Tacito rinnovo</Label>
                            </div>
                            <div><Label>Mandato</Label><Input value={f.mandato} onChange={(e) => set("mandato", e.target.value)} /></div>
                            <div><Label>Sostituisce polizza</Label><Input value={f.sostituisce_polizza} onChange={(e) => set("sostituisce_polizza", e.target.value)} /></div>
                            <div><Label>Stato iter</Label><Input value={f.iter_status} onChange={(e) => set("iter_status", e.target.value)} /></div>
                            <div><Label>Oggetto assicurato</Label><Input value={f.oggetto_assicurato} onChange={(e) => set("oggetto_assicurato", e.target.value)} /></div>
                            <div><Label>Termini mora (gg)</Label><Input type="number" value={f.termini_mora_giorni} onChange={(e) => set("termini_mora_giorni", e.target.value)} /></div>
                            <div><Label>Termini disdetta (gg)</Label><Input type="number" value={f.termini_disdetta_giorni} onChange={(e) => set("termini_disdetta_giorni", e.target.value)} /></div>
                            <div>
                                <Label>Mezzo pagamento preferito (questa polizza)</Label>
                                <Select
                                    value={f.mezzo_pagamento_preferito || "__auto__"}
                                    onValueChange={(v) => set("mezzo_pagamento_preferito", v === "__auto__" ? "" : v)}
                                >
                                    <SelectTrigger data-testid="polizza-mezzo-preferito"><SelectValue /></SelectTrigger>
                                    <SelectContent>
                                        <SelectItem value="__auto__">Auto (segue ultimo incasso)</SelectItem>
                                        {mezzi.map((m) => (
                                            <SelectItem key={m.codice} value={m.codice}>{m.label}</SelectItem>
                                        ))}
                                    </SelectContent>
                                </Select>
                                {pol.ultimo_mezzo_pagamento && (
                                    <div className="text-[10px] text-slate-500 mt-1">
                                        Ultimo incasso: <strong>{pol.ultimo_mezzo_pagamento}</strong>
                                        {pol.ultimo_mezzo_pagamento_data && ` (${pol.ultimo_mezzo_pagamento_data})`}
                                    </div>
                                )}
                            </div>
                        </div>
                    </TabsContent>

                    <TabsContent value="economici">
                        <div className="grid grid-cols-2 gap-3 py-3">
                            <div><Label>Premio netto €</Label><Input type="number" step="0.01" value={f.premio_netto} onChange={(e) => set("premio_netto", e.target.value)} data-testid="edit-pol-premio-netto" /></div>
                            <div><Label>Tasse €</Label><Input type="number" step="0.01" value={f.premio_tasse} onChange={(e) => set("premio_tasse", e.target.value)} data-testid="edit-pol-tasse" /></div>
                            <div><Label>Imposte €</Label><Input type="number" step="0.01" value={f.premio_imposte} onChange={(e) => set("premio_imposte", e.target.value)} data-testid="edit-pol-imposte" /></div>
                            <div><Label>SSN €</Label><Input type="number" step="0.01" value={f.premio_ssn} onChange={(e) => set("premio_ssn", e.target.value)} data-testid="edit-pol-ssn" /></div>
                            <div><Label>Premio lordo €</Label><Input type="number" step="0.01" value={f.premio_lordo} onChange={(e) => set("premio_lordo", e.target.value)} data-testid="edit-pol-premio-lordo" /></div>
                            <div>
                                <Label>Provvigioni €</Label>
                                <div className="flex gap-2">
                                    <Input type="number" step="0.01" value={f.provvigioni}
                                        onChange={(e) => set("provvigioni", e.target.value)}
                                        data-testid="edit-pol-provv" />
                                    <Button
                                        variant="outline" size="sm"
                                        onClick={async () => {
                                            try {
                                                const r = await api.get("/provvigioni/calcola", {
                                                    params: {
                                                        premio_lordo: f.premio_lordo || 0,
                                                        collaboratore_id: f.collaboratore_id || undefined,
                                                        compagnia_id: pol.compagnia_id,
                                                        ramo: f.ramo,
                                                    },
                                                });
                                                if (r.data.provvigione_totale > 0) {
                                                    set("provvigioni", r.data.provvigione_totale);
                                                    toast.success(`Provvigione: ${r.data.provvigione_totale}€ (schema: ${r.data.schema_nome})`);
                                                } else {
                                                    toast.warning("Nessuno schema provvigionale applicabile");
                                                }
                                            } catch { toast.error("Errore calcolo"); }
                                        }}
                                        data-testid="recalc-provv-btn"
                                    >
                                        Auto
                                    </Button>
                                </div>
                                <div className="text-[10px] text-slate-500 mt-1">
                                    Click <em>Auto</em> per ricalcolare dal premio lordo + collaboratore (via schema provvigionale)
                                </div>
                            </div>
                        </div>
                    </TabsContent>

                    {isRCA && (
                        <TabsContent value="veicolo">
                            <div className="text-[11px] uppercase tracking-wide text-sky-700 font-semibold pt-3 pb-1">Dati veicolo</div>
                            <div className="grid grid-cols-2 gap-3 pb-3">
                                <div><Label>Targa</Label><Input value={f.targa} onChange={(e) => set("targa", e.target.value.toUpperCase())} data-testid="edit-pol-targa" /></div>
                                <div><Label>Marca</Label><Input value={f.veicolo_marca} onChange={(e) => set("veicolo_marca", e.target.value)} data-testid="edit-pol-marca" /></div>
                                <div><Label>Modello</Label><Input value={f.veicolo_modello} onChange={(e) => set("veicolo_modello", e.target.value)} data-testid="edit-pol-modello" /></div>
                                <div><Label>Tipo veicolo</Label><Input value={f.veicolo_tipo} onChange={(e) => set("veicolo_tipo", e.target.value)} /></div>
                                <div><Label>Alimentazione</Label><Input value={f.veicolo_alimentazione} onChange={(e) => set("veicolo_alimentazione", e.target.value)} /></div>
                                <div><Label>Tipo uso</Label><Input value={f.veicolo_uso} onChange={(e) => set("veicolo_uso", e.target.value)} /></div>
                                <div><Label>Immatricolazione</Label><Input type="date" value={f.veicolo_data_immatricolazione} onChange={(e) => set("veicolo_data_immatricolazione", e.target.value)} /></div>
                                <div><Label>CV fiscali</Label><Input value={f.veicolo_cv_fiscali} onChange={(e) => set("veicolo_cv_fiscali", e.target.value)} /></div>
                                <div><Label>KW</Label><Input value={f.veicolo_kw} onChange={(e) => set("veicolo_kw", e.target.value)} /></div>
                                <div><Label>Quintali P.C.</Label><Input type="number" step="0.01" value={f.veicolo_quintali} onChange={(e) => set("veicolo_quintali", e.target.value)} data-testid="edit-pol-quintali" /></div>
                                <div><Label>Cilindrata</Label><Input value={f.veicolo_cilindrata} onChange={(e) => set("veicolo_cilindrata", e.target.value)} /></div>
                                <div><Label>Numero posti</Label><Input value={f.veicolo_posti} onChange={(e) => set("veicolo_posti", e.target.value)} /></div>
                                <div className="flex items-center gap-2 mt-6">
                                    <input type="checkbox" id="gancio-traino" checked={f.veicolo_gancio_traino} onChange={(e) => set("veicolo_gancio_traino", e.target.checked)} data-testid="edit-pol-gancio" />
                                    <Label htmlFor="gancio-traino" className="cursor-pointer">Gancio traino</Label>
                                </div>
                                <div><Label>Targa rimorchio</Label><Input value={f.veicolo_targa_rimorchio} onChange={(e) => set("veicolo_targa_rimorchio", e.target.value.toUpperCase())} data-testid="edit-pol-targa-rim" /></div>
                            </div>

                            <div className="text-[11px] uppercase tracking-wide text-sky-700 font-semibold pt-2 pb-1 border-t border-slate-200">Dati associazione contratto</div>
                            <div className="grid grid-cols-2 gap-3 pb-3 pt-2">
                                <div><Label>Tipo tariffa</Label><Input value={f.tipo_tariffa} onChange={(e) => set("tipo_tariffa", e.target.value)} data-testid="edit-pol-tipo-tariffa" /></div>
                                <div><Label>B-M provenienza</Label><Input value={f.bm_provenienza} onChange={(e) => set("bm_provenienza", e.target.value)} data-testid="edit-pol-bm-prov" /></div>
                                <div><Label>B-M assegnata</Label><Input value={f.bm_assegnata} onChange={(e) => set("bm_assegnata", e.target.value)} data-testid="edit-pol-bm-ass" /></div>
                                <div><Label>B-M ass. CU</Label><Input value={f.bm_assegnata_cu} onChange={(e) => set("bm_assegnata_cu", e.target.value)} data-testid="edit-pol-bm-cu" /></div>
                                <div><Label>Pejus</Label><Input type="number" step="0.01" value={f.pejus} onChange={(e) => set("pejus", e.target.value)} data-testid="edit-pol-pejus" /></div>
                                <div><Label>Franchigia €</Label><Input type="number" step="0.01" value={f.franchigia} onChange={(e) => set("franchigia", e.target.value)} data-testid="edit-pol-franchigia" /></div>
                                <div><Label>Valore veicolo €</Label><Input type="number" step="0.01" value={f.valore_veicolo} onChange={(e) => set("valore_veicolo", e.target.value)} data-testid="edit-pol-valore-veicolo" /></div>
                                <div><Label>Valore residuo €</Label><Input type="number" step="0.01" value={f.valore_residuo_veicolo} onChange={(e) => set("valore_residuo_veicolo", e.target.value)} data-testid="edit-pol-valore-residuo" /></div>
                                <div><Label>Valore accessori €</Label><Input type="number" step="0.01" value={f.valore_accessori} onChange={(e) => set("valore_accessori", e.target.value)} data-testid="edit-pol-valore-accessori" /></div>
                                <div className="flex items-center gap-2 mt-6">
                                    <input type="checkbox" id="guida-esperta" checked={f.guida_esperta} onChange={(e) => set("guida_esperta", e.target.checked)} data-testid="edit-pol-guida-esperta" />
                                    <Label htmlFor="guida-esperta" className="cursor-pointer">Guida esperta</Label>
                                </div>
                                <div className="flex items-center gap-2 mt-6">
                                    <input type="checkbox" id="guida-esclusiva" checked={f.guida_esclusiva} onChange={(e) => set("guida_esclusiva", e.target.checked)} data-testid="edit-pol-guida-esclusiva" />
                                    <Label htmlFor="guida-esclusiva" className="cursor-pointer">Guida esclusiva</Label>
                                </div>
                                <div className="flex items-center gap-2 mt-6">
                                    <input type="checkbox" id="rinuncia-rivalsa" checked={f.rinuncia_rivalsa} onChange={(e) => set("rinuncia_rivalsa", e.target.checked)} data-testid="edit-pol-rinuncia-rivalsa" />
                                    <Label htmlFor="rinuncia-rivalsa" className="cursor-pointer">Rinuncia rivalsa</Label>
                                </div>
                                <div><Label>Intestatario</Label><Input value={f.intestatario} onChange={(e) => set("intestatario", e.target.value)} data-testid="edit-pol-intestatario" /></div>
                                <div><Label>Prov. intestatario</Label><Input maxLength={2} value={f.provincia_intestatario} onChange={(e) => set("provincia_intestatario", e.target.value.toUpperCase())} data-testid="edit-pol-prov-intest" /></div>
                                <div className="col-span-2"><Label>Massimali</Label><Input value={f.massimali} onChange={(e) => set("massimali", e.target.value)} data-testid="edit-pol-massimali" /></div>
                            </div>
                        </TabsContent>
                    )}

                    <TabsContent value="altri">
                        <div className="py-3">
                            <Label>Note</Label>
                            <textarea
                                rows={5}
                                className="w-full border border-slate-300 rounded-md px-3 py-2 text-sm"
                                value={f.note} onChange={(e) => set("note", e.target.value)}
                            />
                        </div>
                    </TabsContent>
                </Tabs>
                <DialogFooter>
                    <Button variant="outline" onClick={onClose}>Annulla</Button>
                    <Button onClick={save} className="bg-sky-700 hover:bg-sky-800" data-testid="edit-pol-save">Salva modifiche</Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
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
