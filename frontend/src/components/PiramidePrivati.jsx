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

// Larghezza di ogni banda in % (dal basso al vertice). Base = 100%, apice ≈ 18%.
// Progressione dramática per dare visivamente forma di piramide reale.
const WIDTHS = [100, 92, 82, 72, 62, 52, 40, 22];
// Altezza minima in pixel per ogni banda anche se vuota (livelli senza voci)
const MIN_HEIGHTS = [null, null, null, null, 55, 55, 55, 65];

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

// Formatter € completo con separatore migliaia (es. 1.500.000 €)
function fmtEur(v) {
    if (v == null || v === "" || Number.isNaN(Number(v))) return "";
    const n = Math.round(Number(v));
    if (n === 0) return "";
    // Formato italiano: 1.234.567 €
    return `${n.toLocaleString("it-IT")} €`;
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
            {/* HEADER: solo logo agenzia (grande, centrato/destra) */}
            <div className="flex justify-end items-center mb-3 pb-3 border-b border-slate-300">
                {agenziaLogo ? (
                    <img src={agenziaLogo} alt={agenziaName} className="h-16 md:h-20 w-auto object-contain" />
                ) : (
                    <div className="text-right">
                        <div className="text-2xl md:text-3xl font-bold text-sky-900 tracking-tight">{agenziaName}</div>
                        <div className="text-[11px] text-slate-500 uppercase tracking-wider mt-0.5">Piramide delle Coperture</div>
                    </div>
                )}
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

            {/* CORPO: sidebar dati + piramide + zone labels come step-pyramid */}
            <div className="grid grid-cols-12 gap-3">
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
                <div className="col-span-12 md:col-span-7">
                    <div className="relative">
                        {/* Outline outer piramide (SVG) — dà l'aspetto di una vera piramide */}
                        <svg
                            viewBox="0 0 100 100"
                            preserveAspectRatio="none"
                            className="absolute inset-0 w-full h-full pointer-events-none z-10"
                        >
                            <polygon
                                points="50,0 100,100 0,100"
                                fill="none"
                                stroke="#1e293b"
                                strokeWidth="0.4"
                                vectorEffect="non-scaling-stroke"
                            />
                        </svg>
                        <div className="flex flex-col-reverse items-center gap-0">
                            {LIVELLI.map((lvl, i) => (
                                <PiramideLivello
                                    key={lvl.idx}
                                    lvl={lvl}
                                    width={WIDTHS[lvl.idx]}
                                    widthAbove={WIDTHS[lvl.idx + 1] ?? 0}
                                    minHeight={MIN_HEIGHTS[lvl.idx]}
                                    capitaleVoce={capitaleVoce}
                                    statoVoce={statoVoce}
                                    editable={editable}
                                    onChangeOverride={(vid, v) => setOverrides((s) => ({ ...s, [vid]: v }))}
                                    onRichiediPreventivo={onRichiediPreventivo}
                                />
                            ))}
                        </div>
                    </div>
                </div>

                {/* ZONE LABELS DX — piramide di gradini che seguono le zone */}
                <div className="col-span-12 md:col-span-2 flex flex-col-reverse gap-0.5 text-[10px] font-bold uppercase tracking-wider">
                    {/* Base larga → apice stretto, ogni zona in gradiente rettangolo di altezza proporzionale */}
                    <ZoneStep
                        text="Protezione del Reddito"
                        gradient="from-red-400 to-red-300"
                        heightVh={20}
                        widthPct={100}
                    />
                    <ZoneStep
                        text="Protezione del Patrimonio"
                        gradient="from-red-300 via-emerald-200 to-emerald-300"
                        heightVh={18}
                        widthPct={82}
                    />
                    <ZoneStep
                        text="Risparmio"
                        gradient="from-teal-300 to-teal-200"
                        heightVh={22}
                        widthPct={64}
                    />
                    <ZoneStep
                        text="Investimento"
                        gradient="from-teal-500 to-teal-400"
                        heightVh={10}
                        widthPct={46}
                        textColor="text-white"
                    />
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

function ZoneStep({ text, gradient, heightVh, widthPct, textColor = "text-slate-800" }) {
    // Larghezza in % del container: base larga (100%), apice stretto (46%)
    return (
        <div className="w-full flex justify-start">
            <div
                className={`bg-gradient-to-r ${gradient} border border-white/60 shadow-sm rounded-r-md flex items-center justify-center text-center px-2 py-1 ${textColor}`}
                style={{
                    width: `${widthPct}%`,
                    minHeight: `${heightVh * 4}px`,  // scala da vh a px approssimato
                }}
            >
                <span className="leading-tight text-[9px] md:text-[10px] break-words">
                    {text}
                </span>
            </div>
        </div>
    );
}

function PiramideLivello({ lvl, width, widthAbove, minHeight, capitaleVoce, statoVoce, editable, onChangeOverride, onRichiediPreventivo }) {
    const isEmptyLevel = lvl.voci.length === 0;
    // Bande occupano il `width`% del container padre (centrate). Il contorno SVG esterno
    // dà l'aspetto piramidale complessivo. Per evitare tagli di testo, NON usiamo
    // clip-path sui singoli livelli — solo max-width con centraggio.
    return (
        <div
            className="relative"
            style={{
                width: `${width}%`,
                minHeight: minHeight ? `${minHeight}px` : undefined,
            }}
            data-testid={`piramide-livello-${lvl.idx}`}
        >
            {/* Titolo banda (sempre visibile, sfumatura verso i bordi) */}
            <div className={`${lvl.colore_banda} text-white text-[10px] md:text-[11px] font-bold uppercase text-center px-2 py-1 tracking-tight`}>
                {lvl.titolo}
            </div>
            {/* Voci con input + pallino (fondo bianco) */}
            {!isEmptyLevel && (
                <div className="border-x border-b border-slate-300 bg-white">
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
                                    className="border border-slate-300 rounded px-1.5 py-0.5 text-[10px] w-24 md:w-28 text-right font-mono"
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
    );
}

// Espone anche i costanti per uso esterno
export { LIVELLI, STATO_COLORE, STATO_LABEL, ZONA_LABEL, fmtEur };
