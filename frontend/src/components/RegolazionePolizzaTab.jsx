import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, fmtEur, fmtDate } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Zap, Calculator, Mail, Receipt, Download, ExternalLink, CheckCircle2, MessageCircle, Trash2 } from "lucide-react";
import { toast } from "sonner";

const STATO_LABEL = {
    da_richiedere: "Da richiedere", lettera_inviata: "Lettera inviata",
    dati_ricevuti: "Dati ricevuti", calcolata: "Calcolata",
    titolo_generato: "Titolo generato", chiusa: "Chiusa",
};
const STATO_TONE = {
    da_richiedere: "bg-slate-100 text-slate-700", lettera_inviata: "bg-sky-100 text-sky-700",
    dati_ricevuti: "bg-amber-100 text-amber-700", calcolata: "bg-violet-100 text-violet-700",
    titolo_generato: "bg-emerald-100 text-emerald-700", chiusa: "bg-slate-200 text-slate-500",
};

export default function RegolazionePolizzaTab({ pol, onReload, onCalcola, onGeneraTitolo }) {
    const [eventi, setEventi] = useState([]);
    const [calcoli, setCalcoli] = useState([]);
    const [selCalcoli, setSelCalcoli] = useState(new Set());
    const [busy, setBusy] = useState(false);

    const loadEventi = () => api.get(`/regolazione-premio/${pol.id}/eventi`).then((r) => setEventi(r.data || [])).catch(() => {});
    const loadCalcoli = () => api.get(`/polizze/${pol.id}/regolazione-premio/storico`).then((r) => { setCalcoli(r.data || []); setSelCalcoli(new Set()); }).catch(() => {});
    useEffect(() => { loadEventi(); loadCalcoli(); /* eslint-disable-next-line */ }, [pol.id, pol.regolazione_stato, pol.regolazione_ultimo_calcolo]);

    const toggleCalcolo = (id) => setSelCalcoli((prev) => {
        const n = new Set(prev); n.has(id) ? n.delete(id) : n.add(id); return n;
    });
    const toggleAllCalcoli = () => setSelCalcoli((prev) => {
        const ids = calcoli.map((c) => c.id).filter(Boolean);
        return prev.size === ids.length ? new Set() : new Set(ids);
    });
    const eliminaCalcoliSelezionati = async () => {
        const ids = [...selCalcoli];
        if (ids.length === 0) return;
        if (!window.confirm(`Eliminare ${ids.length} regolazione/i selezionata/e?`)) return;
        setBusy(true);
        try {
            for (const id of ids) {
                await api.delete(`/polizze/${pol.id}/regolazione-premio/storico/${id}`);
            }
            toast.success(`${ids.length} regolazione/i eliminata/e`);
            loadCalcoli();
        } catch (e) { toast.error(e.response?.data?.detail || "Errore eliminazione"); }
        finally { setBusy(false); }
    };

    const stato = pol.regolazione_stato || "da_richiedere";

    const scaricaLettera = async () => {
        try {
            const r = await api.post(`/regolazione-premio/${pol.id}/lettera-pdf`, {}, { responseType: "blob" });
            window.open(URL.createObjectURL(new Blob([r.data], { type: "application/pdf" })), "_blank");
        } catch { toast.error("Errore generazione PDF"); }
    };
    const inviaLettera = async (email) => {
        setBusy(true);
        try {
            const r = await api.post(`/regolazione-premio/${pol.id}/invia-lettera`, { invia_email: email });
            toast.success(email ? `Email ${r.data.email}` : "Lettera segnata come inviata");
            onReload(); loadEventi();
        } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
        finally { setBusy(false); }
    };
    const generaTitolo = () => {
        if (!pol.regolazione_dovuto || pol.regolazione_dovuto <= 0) { toast.error("Calcola prima la regolazione"); return; }
        onGeneraTitolo();
    };

    const [linkUrl, setLinkUrl] = useState(pol.regolazione_public_token ? `${window.location.origin}/rp/${pol.regolazione_public_token}` : "");
    const generaLink = async () => {
        try {
            const r = await api.post(`/regolazione-premio/${pol.id}/genera-link`);
            const url = `${window.location.origin}${r.data.path}`;
            setLinkUrl(url);
            try { await navigator.clipboard.writeText(url); toast.success("Link generato e copiato negli appunti"); }
            catch { toast.success("Link generato"); }
            onReload();
        } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
    };
    const annulla = async () => {
        if (!window.confirm("Azzerare il calcolo della regolazione? La polizza resta soggetta a regolazione.")) return;
        try { await api.post(`/regolazione-premio/${pol.id}/annulla`); toast.success("Regolazione azzerata"); onReload(); loadEventi(); }
        catch { toast.error("Errore"); }
    };
    const elimina = async () => {
        const anche = window.confirm("Eliminare la regolazione da questa polizza?\n\nOK = elimina anche l'eventuale titolo generato\nAnnulla = mantieni il titolo");
        try {
            await api.delete(`/regolazione-premio/${pol.id}`, { params: { elimina_titolo: anche } });
            toast.success("Regolazione eliminata");
            onReload();
        } catch { toast.error("Errore"); }
    };
    const inviaLink = async (canale) => {
        try {
            const r = await api.post(`/regolazione-premio/${pol.id}/invia-link`, { canale });
            if (canale === "email") { toast.success(`Link inviato via email a ${r.data.email}`); }
            else if (r.data.whatsapp_url) { window.open(r.data.whatsapp_url, "_blank"); toast.success("WhatsApp aperto col messaggio precompilato"); }
            onReload();
        } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
    };

    const Info = ({ label, value }) => (
        <div><div className="text-[10px] uppercase tracking-wide text-slate-400">{label}</div><div className="text-sm text-slate-800 font-medium">{value ?? "—"}</div></div>
    );

    return (
        <div className="py-4 space-y-5" data-testid="regolazione-polizza-tab">
            <div className="flex items-center justify-between flex-wrap gap-2">
                <div className="flex items-center gap-2">
                    <Zap size={18} className="text-violet-600" />
                    <h3 className="text-lg font-medium text-slate-900">Regolazione premio</h3>
                    <span className={`px-2 py-0.5 rounded-full text-[11px] font-medium ${STATO_TONE[stato]}`}>{STATO_LABEL[stato]}</span>
                </div>
                <Link to="/regolazione-premio" className="text-xs text-violet-700 hover:underline flex items-center gap-1" data-testid="reg-goto-sezione">
                    Sezione Regolazione Premio <ExternalLink size={12} />
                </Link>
            </div>

            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 bg-violet-50/50 border border-violet-100 rounded-lg p-4">
                <Info label="Base di calcolo" value={pol.regolazione_base} />
                <Info label="Base preventivo" value={pol.regolazione_base_preventivo != null ? (pol.regolazione_base === "addetti" ? pol.regolazione_base_preventivo : fmtEur(pol.regolazione_base_preventivo)) : null} />
                <Info label="Dichiarato cliente" value={pol.regolazione_base_dichiarata_cliente != null ? <span className="text-emerald-700 font-bold">{pol.regolazione_base === "addetti" ? pol.regolazione_base_dichiarata_cliente : fmtEur(pol.regolazione_base_dichiarata_cliente)}</span> : null} />
                <Info label="Tasso" value={pol.regolazione_tasso != null ? `${pol.regolazione_tasso}%` : null} />
                <Info label="Premio minimo" value={pol.regolazione_minima != null ? fmtEur(pol.regolazione_minima) : null} />
                <Info label="Periodicità" value={pol.regolazione_periodicita} />
                <Info label="Invio lettera dopo" value={`${pol.regolazione_giorni_invio ?? 30} gg dalla scadenza`} />
                <Info label="Ultimo calcolo" value={fmtDate(pol.regolazione_ultimo_calcolo)} />
                <Info label="Dovuto" value={<span className="text-violet-700 font-bold">{fmtEur(pol.regolazione_dovuto || 0)}</span>} />
                <Info label="Lettera inviata" value={fmtDate(pol.regolazione_lettera_inviata_data)} />
            </div>

            {pol.regolazione_base_dichiarata_cliente != null && (
                <div className="flex flex-wrap items-center gap-3 bg-emerald-50 border border-emerald-200 rounded-lg p-3" data-testid="reg-dato-cliente-banner">
                    <CheckCircle2 size={18} className="text-emerald-600 shrink-0" />
                    <div className="flex-1 min-w-[200px]">
                        <div className="text-sm text-emerald-900">
                            Il cliente ha dichiarato: <span className="font-bold">{pol.regolazione_base === "addetti" ? pol.regolazione_base_dichiarata_cliente : fmtEur(pol.regolazione_base_dichiarata_cliente)}</span>
                            {pol.regolazione_dato_cliente_data && <span className="text-emerald-700 text-xs"> · il {fmtDate(pol.regolazione_dato_cliente_data)}</span>}
                        </div>
                        <div className="text-[11px] text-emerald-700">Vuoi importarlo come base dichiarata per il calcolo della regolazione?</div>
                    </div>
                    <Button size="sm" className="bg-emerald-700 hover:bg-emerald-800" onClick={onCalcola} data-testid="reg-importa-dato-cliente">
                        <Calculator size={14} className="mr-1" /> Importa e calcola
                    </Button>
                </div>
            )}

            <div className="flex flex-wrap items-center gap-2">
                <Button size="sm" className="bg-violet-700 hover:bg-violet-800" onClick={onCalcola} data-testid="reg-tab-calcola"><Calculator size={14} className="mr-1" /> Calcola regolazione</Button>
                <Button size="sm" variant="outline" onClick={scaricaLettera} data-testid="reg-tab-lettera-pdf"><Download size={14} className="mr-1" /> Anteprima lettera</Button>
                <Button size="sm" variant="outline" disabled={busy} onClick={() => inviaLettera(false)} data-testid="reg-tab-lettera-manuale"><CheckCircle2 size={14} className="mr-1" /> Segna lettera inviata</Button>
                <Button size="sm" variant="outline" disabled={busy} onClick={() => inviaLettera(true)} data-testid="reg-tab-lettera-email"><Mail size={14} className="mr-1" /> Invia email</Button>
                <div className="flex items-center gap-1 ml-auto">
                    <Button size="sm" className="bg-emerald-700 hover:bg-emerald-800" disabled={busy} onClick={generaTitolo} data-testid="reg-tab-genera-titolo"><Receipt size={14} className="mr-1" /> Genera titolo</Button>
                </div>
            </div>

            {/* Link pubblico cliente */}
            <div className="flex flex-wrap items-center gap-2 bg-sky-50 border border-sky-100 rounded-lg p-3">
                <Button size="sm" variant="outline" onClick={generaLink} data-testid="reg-tab-genera-link"><ExternalLink size={14} className="mr-1" /> {linkUrl ? "Rigenera link cliente" : "Genera link cliente"}</Button>
                {linkUrl && (
                    <input readOnly value={linkUrl} onClick={(e) => e.target.select()}
                        className="flex-1 min-w-[200px] text-xs bg-white border border-sky-200 rounded px-2 py-1.5 text-sky-800" data-testid="reg-tab-link-url" />
                )}
                <Button size="sm" variant="outline" className="text-sky-700" onClick={() => inviaLink("email")} data-testid="reg-tab-link-email"><Mail size={14} className="mr-1" /> Invia via email</Button>
                <Button size="sm" variant="outline" className="text-emerald-700" onClick={() => inviaLink("whatsapp")} data-testid="reg-tab-link-whatsapp"><MessageCircle size={14} className="mr-1" /> Invia via WhatsApp</Button>
                <span className="w-full text-[11px] text-sky-700">Il cliente apre il link, indica il dato aggiornato e si compila in automatico (riceverai una notifica).</span>
            </div>

            {/* Modifica / annulla / elimina */}
            <div className="flex flex-wrap items-center gap-2">
                <Button size="sm" variant="ghost" className="text-amber-700 hover:bg-amber-50" onClick={annulla} data-testid="reg-tab-annulla">Annulla calcolo</Button>
                <Button size="sm" variant="ghost" className="text-rose-600 hover:bg-rose-50" onClick={elimina} data-testid="reg-tab-elimina">Elimina regolazione</Button>
            </div>

            <div>
                <div className="flex items-center justify-between mb-2">
                    <div className="text-xs font-semibold text-slate-500 uppercase tracking-wide">Regolazioni calcolate</div>
                    {selCalcoli.size > 0 ? (
                        <Button size="sm" variant="ghost" className="h-7 text-rose-600 hover:bg-rose-50" onClick={eliminaCalcoliSelezionati} disabled={busy} data-testid="reg-elimina-selezionate">
                            <Trash2 size={14} className="mr-1" /> Elimina selezionate ({selCalcoli.size})
                        </Button>
                    ) : (
                        <span className="text-[11px] text-slate-400">Spunta le righe per eliminarle singolarmente</span>
                    )}
                </div>
                {calcoli.length === 0 ? (
                    <div className="text-sm text-slate-400 italic" data-testid="reg-calcoli-empty">Nessuna regolazione calcolata. Usa "Calcola regolazione" per crearne una.</div>
                ) : (
                    <div className="border border-slate-200 rounded-lg overflow-x-auto" data-testid="reg-calcoli-list">
                        <table className="w-full text-sm">
                            <thead className="bg-slate-50 text-[11px] uppercase tracking-wide text-slate-500">
                                <tr>
                                    <th className="text-center px-3 py-2 w-8">
                                        <input type="checkbox"
                                            checked={selCalcoli.size > 0 && selCalcoli.size === calcoli.filter((c) => c.id).length}
                                            onChange={toggleAllCalcoli} data-testid="reg-calcoli-check-all" />
                                    </th>
                                    <th className="text-left px-3 py-2">Periodo</th>
                                    <th className="text-left px-3 py-2">Base</th>
                                    <th className="text-right px-3 py-2">Dato polizza</th>
                                    <th className="text-right px-3 py-2">Dichiarato</th>
                                    <th className="text-right px-3 py-2">Differenza</th>
                                    <th className="text-right px-3 py-2">Tasso</th>
                                    <th className="text-right px-3 py-2">Dovuto</th>
                                    <th className="text-right px-3 py-2">Data</th>
                                </tr>
                            </thead>
                            <tbody className="divide-y divide-slate-100">
                                {calcoli.map((c, i) => {
                                    const addetti = c.base_tipo === "addetti";
                                    const money = (n) => n == null ? "—" : (addetti ? n : fmtEur(n));
                                    return (
                                        <tr key={c.id || i} data-testid={`reg-calcolo-row-${i}`} className={selCalcoli.has(c.id) ? "bg-rose-50/40" : ""}>
                                            <td className="px-3 py-2 text-center">
                                                <input type="checkbox" disabled={!c.id}
                                                    checked={selCalcoli.has(c.id)}
                                                    onChange={() => toggleCalcolo(c.id)}
                                                    data-testid={`reg-calcolo-check-${i}`} />
                                            </td>
                                            <td className="px-3 py-2 font-medium text-slate-800">{c.periodo || "—"}</td>
                                            <td className="px-3 py-2 text-slate-600 capitalize">{c.base_tipo || "—"}</td>
                                            <td className="px-3 py-2 text-right num">{money(c.base_preventivo)}</td>
                                            <td className="px-3 py-2 text-right num text-emerald-700">{money(c.base_effettiva)}</td>
                                            <td className="px-3 py-2 text-right num">{money(c.differenza)}</td>
                                            <td className="px-3 py-2 text-right num">{c.tasso_applicato_pct != null ? `${c.tasso_applicato_pct}%` : "—"}</td>
                                            <td className="px-3 py-2 text-right num font-semibold text-violet-700">{fmtEur(c.dovuto || 0)}</td>
                                            <td className="px-3 py-2 text-right text-xs text-slate-400">{fmtDate(c.data_calcolo)}</td>
                                        </tr>
                                    );
                                })}
                            </tbody>
                        </table>
                    </div>
                )}
            </div>

            <div>
                <div className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">Storico eventi</div>
                {eventi.length === 0 ? (
                    <div className="text-sm text-slate-400 italic">Nessun evento registrato.</div>
                ) : (
                    <div className="border border-slate-200 rounded-lg divide-y divide-slate-100">
                        {eventi.map((e, i) => (
                            <div key={e.id || i} className="px-3 py-2 flex items-center justify-between text-sm">
                                <span className="text-slate-700">{e.evento}{e.importo ? ` · ${fmtEur(e.importo)}` : ""}{e.email ? ` · ${e.email}` : ""}</span>
                                <span className="text-slate-400 text-xs">{fmtDate(e.data)}</span>
                            </div>
                        ))}
                    </div>
                )}
            </div>
        </div>
    );
}
