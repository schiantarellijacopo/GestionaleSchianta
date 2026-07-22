/**
 * AnalisiAziendaTab — Tab dedicato a persona giuridica, con 4 sotto-tab:
 *   • Soci/Azionisti
 *   • Governance (amministratori + rappresentante legale)
 *   • Forza lavoro (dipendenti, contratti, full/part time)
 *   • Commercio estero (% export Italia/UE/altri paesi)
 *
 * I dati sono estratti da OpenAPI.it (imprese.openapi.it/advance) e salvati in
 * `Anagrafica.openapi_data.company.raw`. Bottone "🔄 Aggiorna" chiama
 * POST /api/openapi-it/company/{aid} per refresh dati.
 */
import { useState } from "react";
import { api } from "@/lib/api";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Building2, Users, Briefcase, Globe2, RefreshCw, Info } from "lucide-react";
import { toast } from "sonner";

export default function AnalisiAziendaTab({ ana, onReload }) {
    const [refreshing, setRefreshing] = useState(false);
    const company = ana.openapi_data?.company || {};
    const raw = company.raw || {};
    const dett = raw.dettaglio || {};

    const doRefresh = async () => {
        setRefreshing(true);
        try {
            await api.post(`/openapi-it/company/${ana.id}`);
            toast.success("Dati azienda aggiornati da OpenAPI.it");
            onReload?.();
        } catch (e) {
            toast.error("Errore refresh: " + (e.response?.data?.detail || e.message));
        } finally {
            setRefreshing(false);
        }
    };

    const isMock = (company.provider || "").includes("MOCK");
    const noData = !company.provider;

    // Sezioni dati (fallback su null se mancante — in sandbox alcuni campi non esistono)
    const soci = dett.soci || raw.soci || [];
    const cariche = dett.cariche || dett.amministratori || raw.amministratori || raw.cariche || [];
    const forza = dett.forza_lavoro || raw.forza_lavoro || {
        fascia: dett.fascia_dipendenti,
        dipendenti: dett.numero_dipendenti,
    };
    const commercio = dett.commercio_estero || raw.commercio_estero || {};

    return (
        <div className="space-y-4 mt-4" data-testid="analisi-azienda-tab">
            <Card className="p-4 border-sky-200 bg-sky-50/40">
                <div className="flex items-center justify-between flex-wrap gap-2">
                    <div className="flex items-center gap-2">
                        <Building2 size={18} className="text-sky-700" />
                        <h3 className="font-medium text-sky-900">Analisi azienda — dati OpenAPI.it Camerale</h3>
                        {isMock && <span className="text-[10px] uppercase bg-amber-100 text-amber-800 border border-amber-300 px-2 py-0.5 rounded-full">MOCK</span>}
                        {!isMock && !noData && <span className="text-[10px] uppercase bg-emerald-100 text-emerald-800 border border-emerald-300 px-2 py-0.5 rounded-full">LIVE</span>}
                    </div>
                    <Button size="sm" variant="outline" onClick={doRefresh} disabled={refreshing} data-testid="azienda-refresh-btn">
                        <RefreshCw size={13} className={`mr-1 ${refreshing ? "animate-spin" : ""}`} />
                        {refreshing ? "Aggiornamento…" : (noData ? "Scarica dati" : "Aggiorna")}
                    </Button>
                </div>
                {noData && (
                    <div className="text-xs text-slate-600 mt-3 bg-white rounded p-3 border border-slate-200 flex items-start gap-2">
                        <Info size={13} className="text-sky-600 mt-0.5 shrink-0" />
                        <span>Nessun dato camerale scaricato. Premi &quot;Scarica dati&quot; per interrogare OpenAPI.it. Se in sandbox, il sistema ritornerà dati fittizi di OPENAPI S.P.A.</span>
                    </div>
                )}
            </Card>

            {!noData && (
                <Tabs defaultValue="soci" className="w-full">
                    <TabsList className="bg-slate-100">
                        <TabsTrigger value="soci" data-testid="az-tab-soci"><Users size={13} className="mr-1" /> Soci/Azionisti</TabsTrigger>
                        <TabsTrigger value="governance" data-testid="az-tab-governance"><Briefcase size={13} className="mr-1" /> Governance</TabsTrigger>
                        <TabsTrigger value="forza-lavoro" data-testid="az-tab-forza"><Users size={13} className="mr-1" /> Forza lavoro</TabsTrigger>
                        <TabsTrigger value="commercio" data-testid="az-tab-commercio"><Globe2 size={13} className="mr-1" /> Commercio estero</TabsTrigger>
                    </TabsList>

                    <TabsContent value="soci">
                        <SociSection soci={soci} />
                    </TabsContent>
                    <TabsContent value="governance">
                        <GovernanceSection cariche={cariche} />
                    </TabsContent>
                    <TabsContent value="forza-lavoro">
                        <ForzaLavoroSection forza={forza} />
                    </TabsContent>
                    <TabsContent value="commercio">
                        <CommercioEsteroSection commercio={commercio} />
                    </TabsContent>
                </Tabs>
            )}
        </div>
    );
}

function SociSection({ soci }) {
    const list = Array.isArray(soci) ? soci : [];
    if (list.length === 0) {
        return <EmptyPanel label="Nessun socio disponibile in OpenAPI.it per questa azienda" />;
    }
    return (
        <Card className="p-4 mt-2" data-testid="az-soci-section">
            <table className="w-full text-sm">
                <thead className="text-[10px] uppercase tracking-wider text-slate-500 border-b">
                    <tr>
                        <th className="text-left py-2">Nome/Ragione</th>
                        <th className="text-left py-2">CF/P.IVA</th>
                        <th className="text-right py-2">Quote/azioni</th>
                        <th className="text-left py-2">Data inizio</th>
                    </tr>
                </thead>
                <tbody>
                    {list.map((s, i) => (
                        <tr key={i} className="border-b border-slate-100" data-testid={`az-socio-${i}`}>
                            <td className="py-2 font-medium">{s.denominazione || s.nome_cognome || s.nome || "—"}</td>
                            <td className="py-2 font-mono text-xs">{s.codice_fiscale || s.cf || s.piva || "—"}</td>
                            <td className="py-2 text-right num">{s.quota_percentuale ? `${s.quota_percentuale}%` : (s.quota || "—")}</td>
                            <td className="py-2 num">{s.data_inizio || "—"}</td>
                        </tr>
                    ))}
                </tbody>
            </table>
        </Card>
    );
}

function GovernanceSection({ cariche }) {
    const list = Array.isArray(cariche) ? cariche : [];
    if (list.length === 0) {
        return <EmptyPanel label="Nessuna informazione governance disponibile per questa azienda" />;
    }
    return (
        <Card className="p-4 mt-2" data-testid="az-governance-section">
            <table className="w-full text-sm">
                <thead className="text-[10px] uppercase tracking-wider text-slate-500 border-b">
                    <tr>
                        <th className="text-left py-2">Nome/Cognome</th>
                        <th className="text-left py-2">Ruolo</th>
                        <th className="text-left py-2">Data nascita</th>
                        <th className="text-left py-2">Data inizio</th>
                        <th className="text-center py-2">Rappresentante</th>
                    </tr>
                </thead>
                <tbody>
                    {list.map((c, i) => (
                        <tr key={i} className="border-b border-slate-100" data-testid={`az-carica-${i}`}>
                            <td className="py-2 font-medium">{c.nome_cognome || `${c.cognome || ""} ${c.nome || ""}`.trim() || "—"}</td>
                            <td className="py-2 text-xs">{c.ruolo || c.carica || "—"}</td>
                            <td className="py-2 num text-xs">{c.data_nascita || "—"}</td>
                            <td className="py-2 num text-xs">{c.data_inizio || c.data_nomina || "—"}</td>
                            <td className="py-2 text-center text-xs">
                                {(c.rappresentante_legale === true || c.rappresentante === true || (c.ruolo || "").toLowerCase().includes("legale"))
                                    ? <span className="bg-emerald-100 text-emerald-800 px-2 py-0.5 rounded-full text-[10px]">Sì</span>
                                    : <span className="text-slate-400">No</span>}
                            </td>
                        </tr>
                    ))}
                </tbody>
            </table>
        </Card>
    );
}

function ForzaLavoroSection({ forza }) {
    const f = forza || {};
    const hasData = f.dipendenti || f.fascia || f.contratti_indeterminato_pct;
    if (!hasData) {
        return <EmptyPanel label="Nessun dato sulla forza lavoro disponibile per questa azienda" />;
    }
    return (
        <Card className="p-4 mt-2" data-testid="az-forza-section">
            <table className="w-full text-sm">
                <tbody>
                    <Row label="Fascia" value={f.fascia || "—"} />
                    <Row label="Dipendenti" value={f.dipendenti != null ? f.dipendenti : "—"} mono />
                    <Row label="Trend" value={f.trend_pct != null ? `${f.trend_pct}%` : "—"} mono
                         color={f.trend_pct < 0 ? "text-rose-700" : (f.trend_pct > 0 ? "text-emerald-700" : "")} />
                    <Row label="Contratti a tempo indeterminato" value={f.contratti_indeterminato_pct != null ? `${f.contratti_indeterminato_pct}%` : "—"} mono />
                    <Row label="Full time" value={f.full_time_pct != null ? `${f.full_time_pct}%` : "—"} mono />
                    <Row label="Part time" value={f.part_time_pct != null ? `${f.part_time_pct}%` : "—"} mono />
                </tbody>
            </table>
            {f.part_time_pct != null && f.full_time_pct != null && (
                <div className="mt-4">
                    <div className="text-[10px] uppercase text-slate-500 mb-1">Ripartizione full/part-time</div>
                    <div className="flex h-6 rounded overflow-hidden border border-slate-200">
                        <div className="bg-sky-500" style={{ width: `${f.full_time_pct}%` }} title={`Full time ${f.full_time_pct}%`} />
                        <div className="bg-sky-200" style={{ width: `${f.part_time_pct}%` }} title={`Part time ${f.part_time_pct}%`} />
                    </div>
                </div>
            )}
        </Card>
    );
}

function CommercioEsteroSection({ commercio }) {
    const c = commercio || {};
    const italia = c.italia_pct ?? 100;
    const ue = c.ue_pct ?? 0;
    const extra_ue = c.extra_ue_pct ?? 0;
    if (!c.italia_pct && !c.ue_pct && !c.extra_ue_pct && !c.esporta) {
        return <EmptyPanel label="Nessun dato di commercio estero disponibile per questa azienda" />;
    }
    return (
        <Card className="p-4 mt-2" data-testid="az-commercio-section">
            <div className="text-[10px] uppercase text-slate-500 mb-2">Ripartizione fatturato per area geografica</div>
            <div className="flex h-8 rounded overflow-hidden border border-slate-200">
                <div className="bg-rose-500 flex items-center justify-center text-white text-[11px] font-semibold" style={{ width: `${italia}%` }} title={`Italia ${italia}%`}>
                    {italia > 8 && `IT ${italia}%`}
                </div>
                <div className="bg-blue-500 flex items-center justify-center text-white text-[11px] font-semibold" style={{ width: `${ue}%` }} title={`UE ${ue}%`}>
                    {ue > 8 && `UE ${ue}%`}
                </div>
                <div className="bg-amber-500 flex items-center justify-center text-white text-[11px] font-semibold" style={{ width: `${extra_ue}%` }} title={`Extra-UE ${extra_ue}%`}>
                    {extra_ue > 8 && `Extra-UE ${extra_ue}%`}
                </div>
            </div>
            <table className="w-full text-sm mt-4">
                <tbody>
                    <Row label="% Italia" value={`${italia}%`} mono />
                    <Row label="% Unione Europea" value={`${ue}%`} mono />
                    <Row label="% Altri paesi (Extra-UE)" value={`${extra_ue}%`} mono />
                    {c.paesi_top && c.paesi_top.length > 0 && (
                        <Row label="Top paesi export" value={c.paesi_top.join(", ")} />
                    )}
                </tbody>
            </table>
        </Card>
    );
}

function Row({ label, value, mono, color }) {
    return (
        <tr className="border-b border-slate-100">
            <td className="py-2 text-slate-600">{label}</td>
            <td className={`py-2 text-right ${mono ? "num" : ""} ${color || ""}`}>{value}</td>
        </tr>
    );
}

function EmptyPanel({ label }) {
    return (
        <div className="text-center py-8 text-sm text-slate-400 border border-dashed border-slate-200 rounded mt-2 bg-slate-50" data-testid="az-empty-panel">
            {label}
            <div className="text-[11px] text-slate-400 mt-1">
                (In sandbox alcuni campi sono nulli — in prod saranno popolati per le aziende attive)
            </div>
        </div>
    );
}
