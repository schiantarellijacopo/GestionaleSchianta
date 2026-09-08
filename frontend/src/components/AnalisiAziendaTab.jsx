/**
 * AnalisiAziendaTab — scheda "Info Azienda" (persona giuridica).
 * Panoramica autocompilata + sotto-tab con grafici a torta:
 *  Soci/Azionisti · Governance · Forza lavoro · Commercio estero.
 * Dati da company.openapi.com (IT-full), salvati in openapi_data.company.
 * "Analisi Azienda" (approfondita) verrà sviluppata in seguito.
 */
import { useState } from "react";
import { api, fmtEur } from "@/lib/api";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Building2, Users, Briefcase, Globe2, RefreshCw, Loader2, Info } from "lucide-react";
import { PieChart, Pie, Cell, ResponsiveContainer, Tooltip, Legend } from "recharts";
import OpenApiActions from "@/components/OpenApiActions";
import { toast } from "sonner";

const COLORS = ["#6366f1", "#0ea5e9", "#f59e0b", "#10b981", "#ef4444", "#8b5cf6", "#14b8a6", "#eab308"];

const Field = ({ label, value }) => (
    <div className="py-1 border-b border-slate-100">
        <div className="text-[10px] uppercase tracking-wider text-slate-400">{label}</div>
        <div className="text-sm font-semibold text-slate-800">{value || "—"}</div>
    </div>
);

function TortaSemplice({ data }) {
    if (!data || data.length === 0) return <div className="text-sm text-slate-400 py-8 text-center">Nessun dato disponibile</div>;
    return (
        <ResponsiveContainer width="100%" height={260}>
            <PieChart>
                <Pie data={data} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={90} label={(e) => e.name}>
                    {data.map((_, i) => <Cell key={i} fill={COLORS[i % COLORS.length]} />)}
                </Pie>
                <Tooltip formatter={(v, n) => [`${v}${data[0]?.pct ? "%" : ""}`, n]} />
                <Legend />
            </PieChart>
        </ResponsiveContainer>
    );
}

export default function AnalisiAziendaTab({ ana, canEdit, onReload }) {
    const [loading, setLoading] = useState(false);
    const c = ana.openapi_data?.company || {};
    const hasData = !!c.ragione_sociale;
    const ultimoBilancio = (c.bilanci || [])[0] || {};

    const caricaDati = async () => {
        if (hasData && !window.confirm("Aggiornare i dati azienda? (chiamata a pagamento company.openapi.com)")) return;
        setLoading(true);
        try {
            await api.post(`/openapi-it/company/${ana.id}`);
            toast.success("Dati azienda aggiornati");
            onReload?.();
        } catch (e) {
            toast.error(e.response?.data?.detail || "Errore caricamento dati");
        } finally { setLoading(false); }
    };

    const soci = (c.soci || []).map((s) => ({ name: s.nome || "—", value: s.quota != null ? s.quota : 1, pct: s.quota != null }));
    const gov = (c.amministratori || []).map((m) => ({ name: m.nome || "—", value: 1 }));

    return (
        <div className="space-y-4" data-testid="info-azienda-tab">
            <OpenApiActions ana={ana} canEdit={canEdit} onReload={onReload} />
            <div className="flex items-center justify-between">
                <h3 className="text-lg font-semibold flex items-center gap-2"><Building2 size={18} className="text-sky-700" /> Info Azienda</h3>
                <Button size="sm" onClick={caricaDati} disabled={loading} className="bg-sky-700 hover:bg-sky-800" data-testid="info-azienda-load">
                    {loading ? <Loader2 size={14} className="animate-spin mr-1" /> : <RefreshCw size={14} className="mr-1" />}
                    {hasData ? "Aggiorna dati" : "Carica dati azienda"}
                </Button>
            </div>

            {!hasData ? (
                <Card className="p-8 text-center text-slate-500">
                    <Info size={28} className="mx-auto mb-2 text-slate-300" />
                    Clicca <b>"Carica dati azienda"</b> per importare i dati camerali e di bilancio da OpenAPI.it.
                </Card>
            ) : (
                <>
                    {/* Panoramica */}
                    <Card className="p-4">
                        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-x-6">
                            <Field label="Ragione sociale" value={c.ragione_sociale} />
                            <Field label="Forma giuridica" value={c.forma_giuridica} />
                            <Field label="Stato" value={c.stato_attivita} />
                            <Field label="Cod. ATECO" value={c.ateco ? `${c.ateco} — ${c.ateco_descrizione || ""}` : null} />
                            <Field label="Indirizzo" value={c.indirizzo} />
                            <Field label="N° dipendenti" value={ultimoBilancio.dipendenti ?? "—"} />
                            <Field label="REA / CCIAA" value={[c.rea, c.cciaa].filter(Boolean).join(" / ")} />
                            <Field label="PEC" value={c.pec} />
                            <Field label="Fatturato ultimo bilancio" value={ultimoBilancio.fatturato != null ? fmtEur(ultimoBilancio.fatturato) : "—"} />
                        </div>
                    </Card>

                    {/* Sotto-tab */}
                    <Card className="p-4">
                        <Tabs defaultValue="soci">
                            <TabsList className="bg-slate-100">
                                <TabsTrigger value="soci" data-testid="ia-tab-soci"><Users size={13} className="mr-1" />Soci/Azionisti</TabsTrigger>
                                <TabsTrigger value="governance" data-testid="ia-tab-governance"><Building2 size={13} className="mr-1" />Governance</TabsTrigger>
                                <TabsTrigger value="forza" data-testid="ia-tab-forza"><Briefcase size={13} className="mr-1" />Forza lavoro</TabsTrigger>
                                <TabsTrigger value="estero" data-testid="ia-tab-estero"><Globe2 size={13} className="mr-1" />Commercio estero</TabsTrigger>
                            </TabsList>

                            <TabsContent value="soci">
                                <TortaSemplice data={soci} />
                                {soci.length > 0 && (
                                    <table className="w-full text-xs mt-2">
                                        <tbody>
                                            {(c.soci || []).map((s, i) => (
                                                <tr key={i} className="border-b border-slate-100">
                                                    <td className="py-1">{s.nome}</td>
                                                    <td className="text-right text-slate-600">{s.quota != null ? `${s.quota}%` : ""} {s.tipo || ""}</td>
                                                </tr>
                                            ))}
                                        </tbody>
                                    </table>
                                )}
                            </TabsContent>

                            <TabsContent value="governance">
                                <TortaSemplice data={gov} />
                                {(c.amministratori || []).length > 0 && (
                                    <table className="w-full text-xs mt-2">
                                        <thead className="text-[10px] uppercase text-slate-500 border-b">
                                            <tr><th className="text-left py-1">Nome</th><th className="text-left">Ruolo</th><th className="text-center">Rappr. legale</th></tr>
                                        </thead>
                                        <tbody>
                                            {(c.amministratori || []).map((m, i) => (
                                                <tr key={i} className="border-b border-slate-100">
                                                    <td className="py-1">{m.nome}</td>
                                                    <td className="text-slate-600">{m.ruoli}</td>
                                                    <td className="text-center">{m.legale_rappresentante ? "✓" : ""}</td>
                                                </tr>
                                            ))}
                                        </tbody>
                                    </table>
                                )}
                            </TabsContent>

                            <TabsContent value="forza">
                                <table className="w-full text-sm">
                                    <tbody>
                                        <tr className="border-b border-slate-100"><td className="py-1.5 text-slate-500">Dipendenti (ultimo bilancio)</td><td className="text-right font-medium">{ultimoBilancio.dipendenti ?? "—"}</td></tr>
                                        <tr className="border-b border-slate-100"><td className="py-1.5 text-slate-500">Costo del personale</td><td className="text-right font-medium">{ultimoBilancio.costo_personale != null ? fmtEur(ultimoBilancio.costo_personale) : "—"}</td></tr>
                                        <tr className="border-b border-slate-100"><td className="py-1.5 text-slate-500">Stipendio medio</td><td className="text-right font-medium">{ultimoBilancio.stipendio_medio != null ? fmtEur(ultimoBilancio.stipendio_medio) : "—"}</td></tr>
                                    </tbody>
                                </table>
                                {(c.bilanci || []).length > 1 && (
                                    <div className="mt-3">
                                        <div className="text-[10px] uppercase tracking-wider text-slate-400 mb-1">Trend dipendenti</div>
                                        <table className="w-full text-xs">
                                            <tbody>
                                                {(c.bilanci || []).slice(0, 6).map((b) => (
                                                    <tr key={b.anno} className="border-b border-slate-100"><td className="py-1">{b.anno}</td><td className="text-right">{b.dipendenti ?? "—"}</td></tr>
                                                ))}
                                            </tbody>
                                        </table>
                                    </div>
                                )}
                            </TabsContent>

                            <TabsContent value="estero">
                                <div className="text-sm text-slate-500 bg-slate-50 border border-dashed rounded p-6 text-center">
                                    <Globe2 size={24} className="mx-auto mb-2 text-slate-300" />
                                    Dati import/export non disponibili con questa fonte.<br />
                                    Saranno disponibili con l'attivazione del prodotto <b>Report Aziende</b>.
                                </div>
                            </TabsContent>
                        </Tabs>
                    </Card>

                    <div className="text-[11px] text-slate-400 text-right">Fonte: {c.provider}</div>
                </>
            )}
        </div>
    );
}
