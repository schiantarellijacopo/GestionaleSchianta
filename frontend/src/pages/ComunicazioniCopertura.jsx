import { useState, useCallback } from "react";
import { api, fmtEur, fmtDate, formatError, API_BASE } from "@/lib/api";
import { PageHeader, Empty, Loading } from "@/components/Shared";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Checkbox } from "@/components/ui/checkbox";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from "@/components/ui/select";
import DateInputIt from "@/components/DateInputIt";
import { ShieldCheck, Send, Save, FileText, Eye, Trash2, RefreshCw, Mail, MailX } from "lucide-react";
import { toast } from "sonner";
import { useAuth } from "@/contexts/AuthContext";

const todayIso = () => new Date().toISOString().slice(0, 10);

const StatoBadge = ({ stato }) => {
    const map = {
        bozza: { cls: "bg-slate-100 text-slate-700", label: "Bozza" },
        inviata: { cls: "bg-emerald-100 text-emerald-700", label: "Inviata" },
        errore: { cls: "bg-red-100 text-red-700", label: "Errore" },
    };
    const m = map[stato] || map.bozza;
    return <Badge className={`${m.cls} border-0`} data-testid={`stato-badge-${stato}`}>{m.label}</Badge>;
};

export default function ComunicazioniCopertura() {
    const { user } = useAuth();
    const isAdmin = user?.role === "admin";
    const [tab, setTab] = useState("genera");

    // --- Genera ---
    const [giorno, setGiorno] = useState(todayIso());
    const [gruppi, setGruppi] = useState(null); // null = non caricato
    const [loadingGen, setLoadingGen] = useState(false);
    const [sel, setSel] = useState({}); // { compagnia_id: Set(titolo_id) }
    const [working, setWorking] = useState(false);

    // --- Storico ---
    const [stDal, setStDal] = useState("");
    const [stAl, setStAl] = useState("");
    const [stStato, setStStato] = useState("all");
    const [storico, setStorico] = useState(null);
    const [loadingSt, setLoadingSt] = useState(false);

    const carica = useCallback(async () => {
        if (!giorno) { toast.error("Seleziona una data"); return; }
        setLoadingGen(true); setGruppi(null);
        try {
            const r = await api.get("/comunicazioni-copertura/genera", { params: { giorno } });
            const gs = r.data.gruppi || [];
            setGruppi(gs);
            // preseleziona tutti i titoli
            const s = {};
            gs.forEach((g) => { s[g.compagnia_id] = new Set(g.titoli.map((t) => t.titolo_id)); });
            setSel(s);
        } catch (e) {
            toast.error(formatError(e));
            setGruppi([]);
        } finally {
            setLoadingGen(false);
        }
    }, [giorno]);

    const toggleTitolo = (cid, tid) => {
        setSel((prev) => {
            const next = { ...prev };
            const set = new Set(next[cid] || []);
            if (set.has(tid)) set.delete(tid); else set.add(tid);
            next[cid] = set;
            return next;
        });
    };
    const toggleGruppo = (cid, titoli) => {
        setSel((prev) => {
            const next = { ...prev };
            const cur = next[cid] || new Set();
            if (cur.size === titoli.length) next[cid] = new Set();
            else next[cid] = new Set(titoli.map((t) => t.titolo_id));
            return next;
        });
    };

    const buildPayload = () => {
        const out = [];
        (gruppi || []).forEach((g) => {
            const set = sel[g.compagnia_id] || new Set();
            const titoli = g.titoli.filter((t) => set.has(t.titolo_id));
            if (titoli.length) out.push({ ...g, titoli, totale: titoli.reduce((s, t) => s + (t.importo || 0), 0) });
        });
        return out;
    };

    const salva = async (invia) => {
        const payloadGruppi = buildPayload();
        if (!payloadGruppi.length) { toast.error("Nessun titolo selezionato"); return; }
        if (invia) {
            const senzaEmail = payloadGruppi.filter((g) => !g.destinatario_email);
            if (senzaEmail.length) {
                const ok = window.confirm(
                    `${senzaEmail.length} comunicazione/i non ha email dell'agenzia partner e resterà in errore. Procedere comunque?`
                );
                if (!ok) return;
            }
        }
        setWorking(true);
        try {
            const r = await api.post("/comunicazioni-copertura/salva", { giorno, gruppi: payloadGruppi, invia });
            const coms = r.data.comunicazioni || [];
            const inviate = coms.filter((c) => c.stato === "inviata").length;
            const errori = coms.filter((c) => c.stato === "errore").length;
            if (invia) {
                toast.success(`${inviate} inviate${errori ? `, ${errori} in errore` : ""}`);
            } else {
                toast.success(`${coms.length} comunicazioni salvate in bozza`);
            }
            setGruppi(null); setSel({});
        } catch (e) {
            toast.error(formatError(e));
        } finally {
            setWorking(false);
        }
    };

    const caricaStorico = useCallback(async () => {
        setLoadingSt(true);
        try {
            const params = {};
            if (stDal) params.dal = stDal;
            if (stAl) params.al = stAl;
            if (stStato !== "all") params.stato = stStato;
            const r = await api.get("/comunicazioni-copertura", { params });
            setStorico(r.data || []);
        } catch (e) {
            toast.error(formatError(e));
            setStorico([]);
        } finally {
            setLoadingSt(false);
        }
    }, [stDal, stAl, stStato]);

    const inviaBozza = async (c) => {
        try {
            await api.post(`/comunicazioni-copertura/${c.id}/invia`);
            toast.success(`Comunicazione N.${c.numero} inviata`);
            caricaStorico();
        } catch (e) { toast.error(formatError(e)); caricaStorico(); }
    };
    const eliminaBozza = async (c) => {
        if (!window.confirm(`Eliminare la comunicazione N.${c.numero}?`)) return;
        try {
            await api.delete(`/comunicazioni-copertura/${c.id}`);
            toast.success("Comunicazione eliminata");
            caricaStorico();
        } catch (e) { toast.error(formatError(e)); }
    };

    const totaleSelezionato = buildPayload().reduce((s, g) => s + g.totale, 0);
    const nSelezionati = buildPayload().reduce((s, g) => s + g.titoli.length, 0);

    return (
        <div data-testid="comunicazioni-copertura-page">
            <PageHeader
                title="Comunicazioni di Copertura"
                subtitle="Invio giornaliero alle agenzie partner dei titoli incassati registrati in Prima Nota"
            />

            <Tabs value={tab} onValueChange={setTab}>
                <TabsList className="mb-4" data-testid="cc-tabs">
                    <TabsTrigger value="genera" data-testid="tab-genera">Genera e invia</TabsTrigger>
                    <TabsTrigger value="storico" data-testid="tab-storico" onClick={() => !storico && caricaStorico()}>Storico</TabsTrigger>
                </TabsList>

                {/* ====================== GENERA ====================== */}
                <TabsContent value="genera">
                    <Card className="p-4 mb-4">
                        <div className="flex flex-wrap items-end gap-3">
                            <div>
                                <label className="text-xs font-medium text-slate-500 block mb-1">Giorno di Prima Nota</label>
                                <DateInputIt value={giorno} onChange={setGiorno} className="w-40" data-testid="input-giorno" />
                            </div>
                            <Button onClick={carica} disabled={loadingGen} data-testid="btn-carica-titoli">
                                <RefreshCw className="w-4 h-4 mr-2" />{loadingGen ? "Carico…" : "Carica titoli del giorno"}
                            </Button>
                        </div>
                    </Card>

                    {loadingGen && <Loading />}

                    {gruppi && gruppi.length === 0 && !loadingGen && (
                        <Empty title="Nessun titolo da comunicare" subtitle="Non ci sono titoli incassati o coperti (non ancora comunicati) per il giorno selezionato." />
                    )}

                    {gruppi && gruppi.length > 0 && (
                        <>
                            <div className="sticky top-0 z-10 bg-white/90 backdrop-blur border border-slate-200 rounded-lg p-3 mb-4 flex flex-wrap items-center justify-between gap-3" data-testid="cc-toolbar">
                                <div className="text-sm text-slate-600">
                                    <b data-testid="cc-n-selezionati">{nSelezionati}</b> titoli selezionati · Totale <b data-testid="cc-totale-selezionato">{fmtEur(totaleSelezionato)}</b>
                                </div>
                                <div className="flex gap-2">
                                    <Button variant="outline" onClick={() => salva(false)} disabled={working} data-testid="btn-salva-bozze">
                                        <Save className="w-4 h-4 mr-2" />Salva bozze
                                    </Button>
                                    <Button onClick={() => salva(true)} disabled={working} data-testid="btn-salva-invia">
                                        <Send className="w-4 h-4 mr-2" />{working ? "Invio…" : "Salva e Invia"}
                                    </Button>
                                </div>
                            </div>

                            <div className="space-y-4">
                                {gruppi.map((g) => {
                                    const set = sel[g.compagnia_id] || new Set();
                                    const allSel = set.size === g.titoli.length;
                                    return (
                                        <Card key={g.compagnia_id} className="overflow-hidden" data-testid={`gruppo-${g.compagnia_id}`}>
                                            <div className="flex flex-wrap items-center justify-between gap-2 px-4 py-3 bg-slate-50 border-b">
                                                <div className="flex items-center gap-3">
                                                    <Checkbox checked={allSel} onCheckedChange={() => toggleGruppo(g.compagnia_id, g.titoli)} data-testid={`chk-gruppo-${g.compagnia_id}`} />
                                                    <div>
                                                        <div className="font-semibold text-slate-800">{g.mandato_label}</div>
                                                        <div className="text-xs text-slate-500">
                                                            Destinatario: {g.agenzia_partner_nome || "— nessuna agenzia partner —"}
                                                        </div>
                                                    </div>
                                                </div>
                                                <div className="flex items-center gap-3">
                                                    {g.destinatario_email ? (
                                                        <span className="inline-flex items-center gap-1 text-xs text-emerald-700" data-testid={`mezzo-${g.compagnia_id}`}>
                                                            <Mail className="w-3.5 h-3.5" />{g.destinatario_email}
                                                        </span>
                                                    ) : (
                                                        <span className="inline-flex items-center gap-1 text-xs text-amber-600" data-testid={`mezzo-${g.compagnia_id}`}>
                                                            <MailX className="w-3.5 h-3.5" />Nessuna email
                                                        </span>
                                                    )}
                                                    <span className="text-sm font-semibold text-slate-800">{fmtEur(g.totale)}</span>
                                                </div>
                                            </div>
                                            <div className="overflow-x-auto">
                                                <table className="w-full text-sm">
                                                    <thead>
                                                        <tr className="text-left text-xs text-slate-500 border-b">
                                                            <th className="px-3 py-2 w-8"></th>
                                                            <th className="px-3 py-2">N. Contratto</th>
                                                            <th className="px-3 py-2">Rischio</th>
                                                            <th className="px-3 py-2">Operatore</th>
                                                            <th className="px-3 py-2">Contraente</th>
                                                            <th className="px-3 py-2">Rata del</th>
                                                            <th className="px-3 py-2 text-right">Rata</th>
                                                        </tr>
                                                    </thead>
                                                    <tbody>
                                                        {g.titoli.map((t) => (
                                                            <tr key={t.titolo_id} className="border-b last:border-0 hover:bg-slate-50" data-testid={`riga-${t.titolo_id}`}>
                                                                <td className="px-3 py-2">
                                                                    <Checkbox checked={set.has(t.titolo_id)} onCheckedChange={() => toggleTitolo(g.compagnia_id, t.titolo_id)} data-testid={`chk-titolo-${t.titolo_id}`} />
                                                                </td>
                                                                <td className="px-3 py-2 font-medium">{t.numero_polizza || "—"}</td>
                                                                <td className="px-3 py-2">{t.rischio}</td>
                                                                <td className="px-3 py-2">{t.operatore}</td>
                                                                <td className="px-3 py-2">{t.contraente}</td>
                                                                <td className="px-3 py-2">{fmtDate(t.rata_del)}</td>
                                                                <td className="px-3 py-2 text-right">{fmtEur(t.importo)}</td>
                                                            </tr>
                                                        ))}
                                                    </tbody>
                                                </table>
                                            </div>
                                        </Card>
                                    );
                                })}
                            </div>
                        </>
                    )}
                </TabsContent>

                {/* ====================== STORICO ====================== */}
                <TabsContent value="storico">
                    <Card className="p-4 mb-4">
                        <div className="flex flex-wrap items-end gap-3">
                            <div>
                                <label className="text-xs font-medium text-slate-500 block mb-1">Dal</label>
                                <DateInputIt value={stDal} onChange={setStDal} className="w-36" data-testid="st-dal" />
                            </div>
                            <div>
                                <label className="text-xs font-medium text-slate-500 block mb-1">Al</label>
                                <DateInputIt value={stAl} onChange={setStAl} className="w-36" data-testid="st-al" />
                            </div>
                            <div>
                                <label className="text-xs font-medium text-slate-500 block mb-1">Stato</label>
                                <Select value={stStato} onValueChange={setStStato}>
                                    <SelectTrigger className="w-36" data-testid="st-stato"><SelectValue /></SelectTrigger>
                                    <SelectContent>
                                        <SelectItem value="all">Tutti</SelectItem>
                                        <SelectItem value="bozza">Bozza</SelectItem>
                                        <SelectItem value="inviata">Inviata</SelectItem>
                                        <SelectItem value="errore">Errore</SelectItem>
                                    </SelectContent>
                                </Select>
                            </div>
                            <Button onClick={caricaStorico} disabled={loadingSt} data-testid="btn-carica-storico">
                                <RefreshCw className="w-4 h-4 mr-2" />Aggiorna
                            </Button>
                        </div>
                    </Card>

                    {loadingSt && <Loading />}
                    {storico && storico.length === 0 && !loadingSt && (
                        <Empty title="Nessuna comunicazione" subtitle="Non sono presenti comunicazioni per i filtri selezionati." />
                    )}

                    {storico && storico.length > 0 && (
                        <Card className="overflow-x-auto" data-testid="storico-table">
                            <table className="w-full text-sm">
                                <thead>
                                    <tr className="text-left text-xs text-slate-500 border-b bg-slate-50">
                                        <th className="px-3 py-2">N.</th>
                                        <th className="px-3 py-2">Giorno</th>
                                        <th className="px-3 py-2">Mandato</th>
                                        <th className="px-3 py-2">Destinatario</th>
                                        <th className="px-3 py-2 text-center">Titoli</th>
                                        <th className="px-3 py-2 text-right">Totale</th>
                                        <th className="px-3 py-2">Stato</th>
                                        <th className="px-3 py-2">Inviata il</th>
                                        <th className="px-3 py-2 text-right">Azioni</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {storico.map((c) => (
                                        <tr key={c.id} className="border-b last:border-0 hover:bg-slate-50" data-testid={`storico-row-${c.id}`}>
                                            <td className="px-3 py-2 font-semibold">{c.numero}</td>
                                            <td className="px-3 py-2">{fmtDate(c.giorno)}</td>
                                            <td className="px-3 py-2">{c.mandato_label}</td>
                                            <td className="px-3 py-2">
                                                <div>{c.agenzia_partner_nome || "—"}</div>
                                                <div className="text-xs text-slate-400">{c.destinatario_email || "no email"}</div>
                                                {c.stato === "errore" && c.email_errore && (
                                                    <div className="text-xs text-red-500" data-testid={`err-${c.id}`}>{c.email_errore}</div>
                                                )}
                                            </td>
                                            <td className="px-3 py-2 text-center">{(c.titoli || []).length}</td>
                                            <td className="px-3 py-2 text-right">{fmtEur(c.totale)}</td>
                                            <td className="px-3 py-2"><StatoBadge stato={c.stato} /></td>
                                            <td className="px-3 py-2 text-xs">{c.inviata_at ? fmtDate(c.inviata_at.slice(0, 10)) : "—"}</td>
                                            <td className="px-3 py-2">
                                                <div className="flex items-center justify-end gap-1">
                                                    <Button size="sm" variant="ghost" title="Anteprima" onClick={() => window.open(`${API_BASE}/comunicazioni-copertura/${c.id}/anteprima`, "_blank")} data-testid={`btn-anteprima-${c.id}`}>
                                                        <Eye className="w-4 h-4" />
                                                    </Button>
                                                    <Button size="sm" variant="ghost" title="PDF" onClick={() => window.open(`${API_BASE}/comunicazioni-copertura/${c.id}/pdf`, "_blank")} data-testid={`btn-pdf-${c.id}`}>
                                                        <FileText className="w-4 h-4" />
                                                    </Button>
                                                    {c.stato !== "inviata" && (
                                                        <Button size="sm" variant="ghost" title="Invia" onClick={() => inviaBozza(c)} data-testid={`btn-invia-${c.id}`}>
                                                            <Send className="w-4 h-4" />
                                                        </Button>
                                                    )}
                                                    {c.stato !== "inviata" && isAdmin && (
                                                        <Button size="sm" variant="ghost" title="Elimina" onClick={() => eliminaBozza(c)} data-testid={`btn-elimina-${c.id}`}>
                                                            <Trash2 className="w-4 h-4 text-red-500" />
                                                        </Button>
                                                    )}
                                                </div>
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </Card>
                    )}
                </TabsContent>
            </Tabs>
        </div>
    );
}
