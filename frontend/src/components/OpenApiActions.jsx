/**
 * OpenApiActions — pulsanti per scaricare dati camerali/catastali/veicoli/visure
 * dall'integrazione OpenAPI.it (MOCK/live). Salva il risultato in
 * `Anagrafica.openapi_data` e lo mostra come pannello espandibile.
 */
import { useEffect, useState } from "react";
import { api, fmtEur } from "@/lib/api";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Building2, Home, Car, FileSearch, Loader2, ChevronDown, ChevronUp, Info } from "lucide-react";
import { toast } from "sonner";

export default function OpenApiActions({ ana, canEdit, onReload }) {
    const [mode, setMode] = useState(null); // "mock" | "live"
    const [credit, setCredit] = useState(null);
    const [loading, setLoading] = useState(null); // key attualmente in caricamento
    const [expanded, setExpanded] = useState(null);
    const openapi = ana.openapi_data || {};

    useEffect(() => {
        api.get("/openapi-it/status").then((r) => {
            setMode(r.data.mode);
            setCredit(r.data.credit_eur);
        }).catch(() => setMode(null));
    }, []);

    const call = async (endpoint, key, label) => {
        setLoading(key);
        try {
            const r = await api.post(`/openapi-it/${endpoint}/${ana.id}`);
            toast.success(`${label}: dati scaricati`);
            setExpanded(key);
            onReload?.();
            return r.data;
        } catch (e) {
            toast.error(e.response?.data?.detail || "Errore chiamata OpenAPI.it");
        } finally {
            setLoading(null);
        }
    };

    const hasPiva = !!ana.partita_iva;
    const hasCf = !!ana.codice_fiscale;

    return (
        <Card className="p-4 border-sky-200 bg-sky-50/40 mt-4" data-testid="openapi-actions">
            <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
                <div className="flex items-center gap-2">
                    <FileSearch size={16} className="text-sky-700" />
                    <h4 className="font-medium text-sm text-sky-900">Autocompilazione dati da OpenAPI.it</h4>
                </div>
                {mode && (
                    <div className="flex items-center gap-2">
                        <span className={`text-[10px] uppercase tracking-widest px-2 py-0.5 rounded-full ${mode === "mock" ? "bg-amber-100 text-amber-800" : "bg-emerald-100 text-emerald-800"}`} data-testid="openapi-mode-badge">
                            {mode === "mock" ? "⚠ MOCK" : "🟢 LIVE"}
                        </span>
                        {credit !== null && credit !== undefined && (
                            <span className={`text-[10px] px-2 py-0.5 rounded-full ${credit > 5 ? "bg-emerald-50 text-emerald-700 border border-emerald-200" : "bg-rose-50 text-rose-700 border border-rose-200"}`} data-testid="openapi-credit-badge">
                                Credito: €{credit.toFixed(2)}
                            </span>
                        )}
                    </div>
                )}
            </div>

            <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                <ActionBtn
                    icon={Building2} label="Camerale" testid="oapi-btn-company"
                    disabled={!canEdit || (!hasPiva && !hasCf) || loading === "company"}
                    loading={loading === "company"}
                    onClick={() => call("company", "company", "Camerale")}
                    hint={!hasPiva && !hasCf ? "P.IVA/CF mancante" : null}
                    hasData={!!openapi.company}
                />
                <ActionBtn
                    icon={Home} label="Catasto" testid="oapi-btn-cadastre"
                    disabled={!canEdit || (!hasPiva && !hasCf) || loading === "cadastre"}
                    loading={loading === "cadastre"}
                    onClick={() => call("cadastre", "cadastre", "Catasto")}
                    hint={!hasPiva && !hasCf ? "CF/P.IVA mancante" : null}
                    hasData={Array.isArray(openapi.cadastre) && openapi.cadastre.length > 0}
                />
                <ActionBtn
                    icon={Car} label="Veicoli" testid="oapi-btn-vehicles"
                    disabled={!canEdit || (!hasPiva && !hasCf) || loading === "vehicles"}
                    loading={loading === "vehicles"}
                    onClick={() => call("vehicles", "automotive", "Veicoli")}
                    hint={!hasPiva && !hasCf ? "CF/P.IVA mancante" : null}
                    hasData={Array.isArray(openapi.automotive) && openapi.automotive.length > 0}
                />
                <ActionBtn
                    icon={FileSearch} label="Visura" testid="oapi-btn-visura"
                    disabled={!canEdit || (!hasPiva && !hasCf) || loading === "visura"}
                    loading={loading === "visura"}
                    onClick={() => call("visura", "visura", "Visura")}
                    hint={!hasPiva && !hasCf ? "CF/P.IVA mancante" : null}
                    hasData={!!openapi.visura}
                />
            </div>

            {/* Pannelli dati */}
            {expanded === "company" && openapi.company && <CompanyPanel data={openapi.company} onClose={() => setExpanded(null)} />}
            {expanded === "cadastre" && openapi.cadastre && <CadastrePanel data={openapi.cadastre} onClose={() => setExpanded(null)} />}
            {expanded === "automotive" && openapi.automotive && <VehiclesPanel data={openapi.automotive} onClose={() => setExpanded(null)} />}
            {expanded === "visura" && openapi.visura && <VisuraPanel data={openapi.visura} onClose={() => setExpanded(null)} />}

            {/* Se ci sono dati salvati ma pannello chiuso, mostra chip per riaprire */}
            {expanded === null && (openapi.company || openapi.cadastre || openapi.automotive || openapi.visura) && (
                <div className="mt-3 pt-3 border-t border-sky-200 flex flex-wrap gap-1.5 text-[11px]">
                    <span className="text-slate-500">Dati precedenti:</span>
                    {openapi.company && <ChipView label="Camerale" onClick={() => setExpanded("company")} />}
                    {Array.isArray(openapi.cadastre) && openapi.cadastre.length > 0 && <ChipView label={`Catasto (${openapi.cadastre.length})`} onClick={() => setExpanded("cadastre")} />}
                    {Array.isArray(openapi.automotive) && openapi.automotive.length > 0 && <ChipView label={`Veicoli (${openapi.automotive.length})`} onClick={() => setExpanded("automotive")} />}
                    {openapi.visura && <ChipView label="Visura" onClick={() => setExpanded("visura")} />}
                    {openapi.last_sync && <span className="text-slate-400">· ultimo sync {openapi.last_sync.slice(0, 10)}</span>}
                </div>
            )}
        </Card>
    );
}

function ActionBtn({ icon: Icon, label, onClick, loading, disabled, hint, hasData, testid }) {
    return (
        <div>
            <Button
                type="button"
                variant="outline"
                onClick={onClick}
                disabled={disabled}
                className={`w-full ${hasData ? "border-emerald-400 bg-emerald-50 text-emerald-800 hover:bg-emerald-100" : ""}`}
                data-testid={testid}
            >
                {loading ? <Loader2 size={13} className="animate-spin mr-1" /> : <Icon size={13} className="mr-1" />}
                {label}
                {hasData && <span className="ml-1 text-[9px]">✓</span>}
            </Button>
            {hint && <div className="text-[10px] text-slate-500 mt-1 flex items-center gap-1"><Info size={9} /> {hint}</div>}
        </div>
    );
}

function ChipView({ label, onClick }) {
    return (
        <button type="button" onClick={onClick} className="bg-white border border-sky-300 text-sky-700 px-2 py-0.5 rounded-full hover:bg-sky-100">
            {label} <ChevronDown size={9} className="inline" />
        </button>
    );
}

function PanelWrap({ title, onClose, children }) {
    return (
        <div className="mt-3 pt-3 border-t border-sky-200 bg-white/70 rounded p-3">
            <div className="flex items-center justify-between mb-2">
                <div className="text-xs font-semibold text-sky-900 uppercase tracking-wider">{title}</div>
                <button onClick={onClose} className="text-[11px] text-slate-500 hover:text-slate-800 flex items-center gap-1">
                    <ChevronUp size={11} /> chiudi
                </button>
            </div>
            {children}
        </div>
    );
}

function CompanyPanel({ data, onClose }) {
    return (
        <PanelWrap title="Dati camerali" onClose={onClose}>
            <div className="grid grid-cols-2 md:grid-cols-3 gap-3 text-xs">
                <Kv k="Ragione sociale" v={data.ragione_sociale} />
                <Kv k="P.IVA" v={data.piva} />
                <Kv k="CF" v={data.cf} />
                <Kv k="Forma giuridica" v={data.forma_giuridica} />
                <Kv k="ATECO" v={`${data.ateco || ""} ${data.ateco_descrizione ? "· " + data.ateco_descrizione : ""}`} />
                <Kv k="Data costituzione" v={data.data_costituzione} />
                <Kv k="Capitale sociale" v={data.capitale_sociale_versato ? fmtEur(data.capitale_sociale_versato) : "—"} />
                <Kv k="Legale rappresentante" v={data.legale_rappresentante} />
                <Kv k="PEC" v={data.pec} />
                <Kv k="Sede" v={`${data.indirizzo || ""} ${data.cap || ""} ${data.comune || ""} (${data.provincia || "—"})`} />
                <Kv k="CCIAA / REA" v={`${data.cciaa || "—"} / ${data.rea || "—"}`} />
                <Kv k="Stato" v={data.attiva ? "Attiva" : "Cessata"} />
            </div>
        </PanelWrap>
    );
}

function CadastrePanel({ data, onClose }) {
    return (
        <PanelWrap title={`Catasto (${data.length} immobili)`} onClose={onClose}>
            {data.length === 0 ? (
                <div className="text-xs text-slate-500 italic">Nessun immobile trovato al catasto.</div>
            ) : (
                <table className="w-full text-xs">
                    <thead className="text-[10px] uppercase text-slate-500 border-b border-slate-200">
                        <tr>
                            <th className="text-left py-1">Comune</th><th>F/P/S</th><th>Cat.</th><th>Sup. mq</th>
                            <th className="text-right">Rendita</th><th className="text-left">Titolo</th>
                        </tr>
                    </thead>
                    <tbody>
                        {data.map((im, i) => (
                            <tr key={i} className="border-b border-slate-100">
                                <td className="py-1">{im.comune}<div className="text-[10px] text-slate-500">{im.indirizzo}</div></td>
                                <td className="text-center num">{im.foglio}/{im.particella}/{im.subalterno}</td>
                                <td className="text-center">{im.categoria}</td>
                                <td className="text-center num">{im.superficie_catastale_mq}</td>
                                <td className="text-right num">{fmtEur(im.rendita_eur)}</td>
                                <td>{im.titolo}</td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            )}
        </PanelWrap>
    );
}

function VehiclesPanel({ data, onClose }) {
    return (
        <PanelWrap title={`Veicoli intestati (${data.length})`} onClose={onClose}>
            {data.length === 0 ? (
                <div className="text-xs text-slate-500 italic">Nessun veicolo intestato al PRA.</div>
            ) : (
                <table className="w-full text-xs">
                    <thead className="text-[10px] uppercase text-slate-500 border-b border-slate-200">
                        <tr>
                            <th className="text-left py-1">Targa</th><th>Marca/Modello</th><th>Alim.</th>
                            <th>KW</th><th>Immatr.</th><th>Rev.</th>
                        </tr>
                    </thead>
                    <tbody>
                        {data.map((v, i) => (
                            <tr key={i} className="border-b border-slate-100">
                                <td className="py-1 font-mono font-semibold">{v.targa}</td>
                                <td>{v.marca} {v.modello}</td>
                                <td className="text-center">{v.alimentazione}</td>
                                <td className="text-center num">{v.potenza_kw}</td>
                                <td className="text-center num">{v.data_immatricolazione}</td>
                                <td className="text-center num">{v.scadenza_revisione}</td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            )}
        </PanelWrap>
    );
}

function VisuraPanel({ data, onClose }) {
    return (
        <PanelWrap title="Visura camerale" onClose={onClose}>
            <div className="grid grid-cols-2 gap-3 text-xs">
                <Kv k="Ragione sociale" v={data.ragione_sociale} />
                <Kv k="P.IVA" v={data.piva} />
                <Kv k="Tipo visura" v={data.tipo_visura} />
                <Kv k="Data estrazione" v={data.data_estrazione} />
                <Kv k="Capitale sociale" v={data.capitale_sociale ? fmtEur(data.capitale_sociale) : "—"} />
                {Array.isArray(data.amministratori) && data.amministratori.length > 0 && (
                    <div className="col-span-2">
                        <div className="text-[10px] uppercase text-slate-500 mb-1">Amministratori</div>
                        <ul className="list-disc ml-4">
                            {data.amministratori.map((a, i) => (
                                <li key={i}>{a.nome_cognome} — <span className="text-slate-500">{a.carica}</span></li>
                            ))}
                        </ul>
                    </div>
                )}
            </div>
        </PanelWrap>
    );
}

function Kv({ k, v }) {
    return (
        <div>
            <div className="text-[10px] uppercase tracking-wider text-slate-500">{k}</div>
            <div className="text-slate-800">{v || "—"}</div>
        </div>
    );
}
