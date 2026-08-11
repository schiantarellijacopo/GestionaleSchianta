import { useEffect, useState, useCallback } from "react";
import { toast } from "sonner";

// -----------------------------------------------------------------------------
// PIRAMIDE COPERTURE — Modello Schiantarelli
// Componente riusabile: modalità editabile (agenzia) o read-only (portale).
// -----------------------------------------------------------------------------
// Le 8 bande della piramide dal basso (larga) all'apice (stretta).
// Ogni banda ha una zona/categoria (colore) e una lista di voci con capitale
// popolato automaticamente dalle polizze o inserito manualmente.
// -----------------------------------------------------------------------------

const LIVELLI = [
    // livello 1 (base) — INVALIDITÀ
    {
        idx: 0, zona: "reddito", colore_banda: "bg-red-500", colore_zona: "reddito",
        titolo: "IN CASO DI INVALIDITÀ DOVUTA A:",
        voci: [
            { id: "invalidita_malattia", label: "MALATTIA, sei protetto fino a" },
            { id: "invalidita_infortunio", label: "INFORTUNIO, sei protetto fino a" },
            { id: "invalidita_non_autosufficienza", label: "NON AUTOSUFFICIENZA, sei protetto fino a" },
        ],
    },
    // livello 2 — PREMORIENZA
    {
        idx: 1, zona: "reddito", colore_banda: "bg-red-500", colore_zona: "reddito",
        titolo: "IN CASO DI PREMORIENZA DOVUTA A:",
        voci: [
            { id: "premorienza_malattia", label: "MALATTIA, sei protetto fino a" },
            { id: "premorienza_infortunio", label: "INFORTUNIO, sei protetto fino a" },
        ],
    },
    // livello 3 — DANNI AD ALTRI
    {
        idx: 2, zona: "patrimonio", colore_banda: "bg-red-500", colore_zona: "patrimonio",
        titolo: "IN CASO DI DANNI PROVOCATI AD ALTRI, DOVUTI A:",
        voci: [
            { id: "danni_veicoli", label: "VEICOLI, sei protetto fino a" },
            { id: "danni_immobili", label: "IMMOBILI, sei protetto fino a" },
            { id: "danni_professioni", label: "PROFESSIONI, sei protetto fino a" },
            { id: "danni_vita_privata", label: "VITA PRIVATA, sei protetto fino a" },
        ],
    },
    // livello 4 — PERDITA BENI
    {
        idx: 3, zona: "patrimonio", colore_banda: "bg-emerald-600", colore_zona: "patrimonio",
        titolo: "PERDITA DEI BENI DOVUTA DA INCENDI/EVENTI ATMOSFERICI/ALLUVIONI/TERREMOTI",
        voci: [
            { id: "perdita_beni_immobili", label: "IMMOBILI, sei protetto fino a" },
            { id: "perdita_beni_aziende", label: "AZIENDE, sei protetto fino a" },
        ],
    },
    // livello 5 — LIQUIDITÀ
    {
        idx: 4, zona: "risparmio", colore_banda: "bg-teal-500", colore_zona: "risparmio",
        titolo: "LIQUIDITÀ GIORNALIERA - CONTO CORRENTE",
        voci: [], // solo banda, valore aggregato
    },
    // livello 6 — CASSA LIEVI
    {
        idx: 5, zona: "risparmio", colore_banda: "bg-teal-500", colore_zona: "risparmio",
        titolo: "CASSA PER LE LIEVI ESIGENZE",
        voci: [],
    },
    // livello 7 — CASSA GRANDI
    {
        idx: 6, zona: "risparmio", colore_banda: "bg-teal-500", colore_zona: "risparmio",
        titolo: "CASSA PER LE GRANDI ESIGENZE",
        voci: [],
    },
    // livello 8 (apice) — CRESCITA CAPITALE
    {
        idx: 7, zona: "investimento", colore_banda: "bg-teal-600", colore_zona: "investimento",
        titolo: "CRESCITA DEL CAPITALE",
        voci: [],
    },
];

// Larghezza di ogni banda in % (dal basso al vertice). Base = 100%, apice ≈ 20%.
const WIDTHS = [100, 90, 78, 66, 56, 46, 34, 22];

const STATO_COLORE = {
    adeguato: "bg-emerald-500 border-emerald-700",
    non_adeguato: "bg-yellow-400 border-yellow-600",
    assente: "bg-red-500 border-red-700",
};
const STATO_LABEL = {
    adeguato: "ADEGUATO",
    non_adeguato: "NON ADEGUATO",
    assente: "ASSENTE",
};
const ZONA_LABEL = {
    reddito: "PROTEZIONE DEL REDDITO",
    patrimonio: "PROTEZIONE DEL PATRIMONIO",
    risparmio: "RISPARMIO",
    investimento: "INVESTIMENTO",
};
const ZONA_COLORS = {
    reddito: "bg-slate-100 text-slate-800 border-slate-300",
    patrimonio: "bg-slate-100 text-slate-800 border-slate-300",
    risparmio: "bg-slate-100 text-slate-800 border-slate-300",
    investimento: "bg-slate-100 text-slate-800 border-slate-300",
};

// Formatter € breve (1.5M €, 250K €, …)
function fmtEur(v) {
    if (v == null || v === "" || Number.isNaN(Number(v))) return "";
    const n = Number(v);
    if (n === 0) return "";
    if (n >= 1000000) return `${(n / 1000000).toFixed(1).replace(/\.0$/, "")}M €`;
    if (n >= 1000) return `${Math.round(n / 1000)}K €`;
    return `${Math.round(n)} €`;
}

// ─────────────────────────────────────────────────────────────
// Componente principale
// ─────────────────────────────────────────────────────────────
export default function PiramidePrivati({
    voci_calcolate = {},
    dati_reddito = {},
    testamento = false,
    eredi_legittimi = [],
    override_voci = {},
    onSave, // (payload) => Promise. Se null → read-only
    onRichiediPreventivo, // (voce_id, voce_label) => void
    agenziaLogo,
    agenziaName = "Assicurazioni",
}) {
    const editable = typeof onSave === "function";
    const [reddito, setReddito] = useState(dati_reddito || {});
    const [test, setTest] = useState(!!testamento);
    const [eredi, setEredi] = useState(() => {
        const base = Array.isArray(eredi_legittimi) ? [...eredi_legittimi] : [];
        while (base.length < 4) base.push("");
        return base.slice(0, 4);
    });
    const [overrides, setOverrides] = useState(override_voci || {});
    const [saving, setSaving] = useState(false);

    useEffect(() => { setReddito(dati_reddito || {}); }, [dati_reddito]);
    useEffect(() => { setTest(!!testamento); }, [testamento]);
    useEffect(() => {
        const b = Array.isArray(eredi_legittimi) ? [...eredi_legittimi] : [];
        while (b.length < 4) b.push("");
        setEredi(b.slice(0, 4));
    }, [eredi_legittimi]);
    useEffect(() => { setOverrides(override_voci || {}); }, [override_voci]);

    const salva = useCallback(async () => {
        if (!editable) return;
        setSaving(true);
        try {
            await onSave({
                dati_reddito: reddito,
                testamento: test,
                eredi_legittimi: eredi.filter((e) => (e || "").trim()),
                override_voci: overrides,
            });
            toast.success("Piramide salvata");
        } catch (e) { toast.error("Errore salvataggio: " + (e.response?.data?.detail || e.message)); }
        finally { setSaving(false); }
    }, [editable, onSave, reddito, test, eredi, overrides]);

    // Combina valore calcolato + override manuale
    const capitaleVoce = (vid) => {
        const ov = overrides[vid];
        if (ov != null && ov !== "") return Number(ov) || 0;
        return voci_calcolate[vid]?.capitale || 0;
    };
    const statoVoce = (vid) => {
        const ov = overrides[vid];
        if (ov != null && ov !== "") {
            // Se override → usa lo stato dal capitale numerico (semplicistico)
            return Number(ov) > 0 ? "adeguato" : "assente";
        }
        return voci_calcolate[vid]?.stato || "assente";
    };

    return (
        <div className="bg-white rounded-lg border-2 border-slate-800 p-4 md:p-6 font-sans" data-testid="piramide-privati">
            {/* HEADER: logo agenzia + titolo brand */}
            <div className="flex justify-between items-start mb-3 pb-3 border-b border-slate-300">
                <div className="flex items-center gap-3">
                    <div className="w-14 h-14 rounded-full bg-emerald-100 border-2 border-emerald-700 flex items-center justify-center text-[9px] font-bold text-emerald-900 text-center leading-tight">
                        FUTURO<br />SENZA<br />SORPRESE
                    </div>
                </div>
                <div className="flex items-center gap-2">
                    {agenziaLogo ? (
                        <img src={agenziaLogo} alt="logo" className="h-12 w-auto object-contain" />
                    ) : (
                        <div className="text-right">
                            <div className="text-2xl font-bold text-slate-800">{agenziaName}</div>
                            <div className="text-[10px] text-slate-500 uppercase tracking-wider">Piramide delle Coperture</div>
                        </div>
                    )}
                </div>
            </div>

            {/* LEGENDA */}
            <div className="flex items-center gap-4 mb-4 text-[11px] font-semibold text-slate-700">
                <span>LEGENDA:</span>
                <span className="flex items-center gap-1.5">
                    <span className="w-4 h-4 rounded-full bg-emerald-500 border-2 border-emerald-700" /> ADEGUATO
                </span>
                <span className="flex items-center gap-1.5">
                    <span className="w-4 h-4 rounded-full bg-yellow-400 border-2 border-yellow-600" /> NON ADEGUATO
                </span>
                <span className="flex items-center gap-1.5">
                    <span className="w-4 h-4 rounded-full bg-red-500 border-2 border-red-700" /> ASSENTE
                </span>
            </div>

            {/* CORPO: sidebar dati + piramide */}
            <div className="grid grid-cols-12 gap-4">
                {/* SIDEBAR SX — dati reddito */}
                <div className="col-span-12 md:col-span-3 space-y-2 text-[11px]">
                    <SidebarField label="IL TUO REDDITO ATTUALE" value={reddito.reddito_attuale}
                                  editable={editable}
                                  onChange={(v) => setReddito((s) => ({ ...s, reddito_attuale: v }))} />
                    <div className="pb-1 border-b border-slate-200">
                        <span className="font-semibold text-slate-700">ESTRATTO CONTO CONTRIBUTIVO:</span>
                        <label className="ml-2 mr-2">
                            <input type="checkbox" disabled={!editable}
                                   checked={reddito.estratto_conto === true}
                                   onChange={() => editable && setReddito((s) => ({ ...s, estratto_conto: true }))} /> Sì
                        </label>
                        <label>
                            <input type="checkbox" disabled={!editable}
                                   checked={reddito.estratto_conto === false}
                                   onChange={() => editable && setReddito((s) => ({ ...s, estratto_conto: false }))} /> No
                        </label>
                    </div>
                    <div className="text-[10px] text-slate-600 font-semibold uppercase pt-1">
                        Il tuo reddito lordo annuale in caso di:
                    </div>
                    <SidebarField label="INVALIDITÀ 66%-99%" value={reddito.reddito_invalidita_66_99}
                                  editable={editable}
                                  onChange={(v) => setReddito((s) => ({ ...s, reddito_invalidita_66_99: v }))} />
                    <SidebarField label="INABILITÀ 100%" value={reddito.reddito_inabilita_100}
                                  editable={editable}
                                  onChange={(v) => setReddito((s) => ({ ...s, reddito_inabilita_100: v }))} />
                    <SidebarField label="SUPERSTITI" value={reddito.reddito_superstiti}
                                  editable={editable}
                                  onChange={(v) => setReddito((s) => ({ ...s, reddito_superstiti: v }))} />
                    <SidebarField label="RESPONSABILITÀ" value={reddito.reddito_responsabilita}
                                  editable={editable}
                                  onChange={(v) => setReddito((s) => ({ ...s, reddito_responsabilita: v }))} />
                    <SidebarField label="PERDITA BENI" value={reddito.reddito_perdita_beni}
                                  editable={editable}
                                  onChange={(v) => setReddito((s) => ({ ...s, reddito_perdita_beni: v }))} />
                </div>

                {/* PIRAMIDE — colonna centrale grande */}
                <div className="col-span-12 md:col-span-9 relative">
                    <div className="flex flex-col-reverse items-center gap-0.5 px-2">
                        {LIVELLI.map((lvl) => (
                            <PiramideLivello
                                key={lvl.idx}
                                lvl={lvl}
                                width={WIDTHS[lvl.idx]}
                                capitaleVoce={capitaleVoce}
                                statoVoce={statoVoce}
                                editable={editable}
                                onChangeOverride={(vid, v) => setOverrides((s) => ({ ...s, [vid]: v }))}
                                onRichiediPreventivo={onRichiediPreventivo}
                            />
                        ))}
                    </div>
                    {/* ZONE LABELS a destra (posizionamento assoluto opzionale, qui semplificato) */}
                    <div className="hidden lg:flex flex-col-reverse absolute right-[-140px] top-0 h-full py-2 gap-1 w-32 text-[10px] font-bold uppercase tracking-wider">
                        <ZoneLabel color="from-red-100 to-red-50 border-red-200" text="Protezione del Reddito" flex={2} />
                        <ZoneLabel color="from-emerald-100 to-red-100 border-slate-200" text="Protezione del Patrimonio" flex={2} />
                        <ZoneLabel color="from-teal-100 to-emerald-100 border-teal-200" text="Risparmio" flex={3} />
                        <ZoneLabel color="from-teal-200 to-teal-100 border-teal-300" text="Investimento" flex={1} />
                    </div>
                </div>
            </div>

            {/* FOOTER: testamento + eredi */}
            <div className="mt-6 pt-4 border-t border-slate-300 text-[11px]">
                <div className="text-center mb-3 font-semibold">
                    TESTAMENTO:{" "}
                    <label className="ml-2 mr-2">
                        <input type="checkbox" disabled={!editable} checked={test === true}
                               onChange={() => editable && setTest(true)} /> Sì
                    </label>
                    <label>
                        <input type="checkbox" disabled={!editable} checked={test === false}
                               onChange={() => editable && setTest(false)} /> No
                    </label>
                </div>
                <div className="text-center font-semibold mb-2">EREDI LEGITTIMI:</div>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                    {[0, 1, 2, 3].map((i) => (
                        <input key={i} type="text"
                               value={eredi[i] || ""}
                               disabled={!editable}
                               onChange={(e) => {
                                   const nx = [...eredi]; nx[i] = e.target.value; setEredi(nx);
                               }}
                               placeholder={`Erede ${i + 1}`}
                               data-testid={`eredi-${i}`}
                               className="border border-slate-300 rounded px-2 py-1 text-[11px]" />
                    ))}
                </div>
            </div>

            {editable && (
                <div className="mt-4 flex justify-end">
                    <button
                        onClick={salva}
                        disabled={saving}
                        className="bg-sky-700 hover:bg-sky-800 text-white text-sm px-4 py-2 rounded font-medium disabled:opacity-60"
                        data-testid="piramide-salva"
                    >
                        {saving ? "Salvataggio..." : "Salva Piramide"}
                    </button>
                </div>
            )}
        </div>
    );
}

// -----------------------------------------------------------------------------
// Sub-components
// -----------------------------------------------------------------------------

function SidebarField({ label, value, editable, onChange }) {
    return (
        <div className="flex items-center gap-2">
            <span className="font-semibold text-slate-700 text-[10px] uppercase min-w-[70%]">{label}:</span>
            <input
                type="text"
                value={value ?? ""}
                disabled={!editable}
                onChange={(e) => onChange(e.target.value)}
                className="border border-slate-300 rounded px-1.5 py-0.5 text-[10px] w-full max-w-[80px] font-mono"
            />
        </div>
    );
}

function ZoneLabel({ color, text, flex }) {
    return (
        <div className={`bg-gradient-to-r ${color} border rounded flex items-center justify-center text-center px-2 py-1`}
             style={{ flex }}>
            {text}
        </div>
    );
}

function PiramideLivello({ lvl, width, capitaleVoce, statoVoce, editable, onChangeOverride, onRichiediPreventivo }) {
    // La forma della banda usa un trapezoide via clip-path
    const marginX = (100 - width) / 2;
    return (
        <div className="w-full flex justify-center" style={{ paddingLeft: `${marginX}%`, paddingRight: `${marginX}%` }}>
            <div className="w-full">
                {/* Banda del livello con titolo */}
                <div className={`${lvl.colore_banda} text-white text-[10px] md:text-[11px] font-bold uppercase text-center px-2 py-1 tracking-tight`}
                     data-testid={`piramide-livello-${lvl.idx}`}>
                    {lvl.titolo}
                </div>
                {/* Voci: se il livello ne ha, mostra input; altrimenti banda vuota */}
                {lvl.voci.length > 0 && (
                    <div className="border border-slate-300 bg-white">
                        {lvl.voci.map((voce) => {
                            const cap = capitaleVoce(voce.id);
                            const st = statoVoce(voce.id);
                            return (
                                <div key={voce.id} className="flex items-center gap-2 border-b last:border-b-0 border-slate-200 px-2 py-1 text-[10px]">
                                    <span className="flex-1 uppercase font-medium text-slate-700 text-[9px] md:text-[10px]" title={voce.label}>
                                        {voce.label}
                                    </span>
                                    <input
                                        type="text"
                                        value={cap ? fmtEur(cap) : ""}
                                        disabled={!editable}
                                        onChange={(e) => {
                                            const raw = e.target.value.replace(/[^\d]/g, "");
                                            onChangeOverride(voce.id, raw);
                                        }}
                                        placeholder="—"
                                        className="border border-slate-300 rounded px-1.5 py-0.5 text-[10px] w-20 md:w-24 text-right font-mono"
                                        data-testid={`piramide-input-${voce.id}`}
                                    />
                                    <button
                                        type="button"
                                        onClick={() => onRichiediPreventivo && st !== "adeguato"
                                            ? onRichiediPreventivo(voce.id, voce.label)
                                            : null}
                                        title={STATO_LABEL[st] + (st !== "adeguato" ? " — click per richiedere preventivo" : "")}
                                        className={`w-4 h-4 rounded-full border-2 ${STATO_COLORE[st]} flex-shrink-0 ${
                                            onRichiediPreventivo && st !== "adeguato" ? "cursor-pointer hover:scale-125 transition-transform" : "cursor-default"
                                        }`}
                                        data-testid={`piramide-pallino-${voce.id}`}
                                    />
                                </div>
                            );
                        })}
                    </div>
                )}
            </div>
        </div>
    );
}

// Espone anche i costanti per uso esterno
export { LIVELLI, STATO_COLORE, STATO_LABEL, ZONA_LABEL, fmtEur };
