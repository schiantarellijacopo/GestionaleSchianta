import { useEffect, useState, useCallback } from "react";
import { toast } from "sonner";

// -----------------------------------------------------------------------------
// PIRAMIDE DELLA PROTEZIONE — replica fedele del modello stampato Schiantarelli.
// Triangolo unico con clip-path sul wrapper: tutte le scritte/pallini restano
// SEMPRE dentro i bordi. Geometria dinamica: aggiungendo voci custom la
// piramide cresce in altezza mantenendo la forma.
// -----------------------------------------------------------------------------

const PYR_W = 1040;          // larghezza base triangolo (px)
const CX = PYR_W / 2;        // apice orizzontale
const WEDGE_AREA = 250;      // colonna cunei zone a destra
const TOTAL_W = PYR_W + WEDGE_AREA;
const ROW_H = 24;            // altezza extra per ogni voce custom

const COLORS = {
    red: "#b93e3e",
    green: "#388a44",
    teal: "#217887",
    tealApex: "#1a5f6b",
};

const DOT_COLORS = {
    adeguato: "#22c55e",
    non_adeguato: "#eab308",
    assente: "#ef4444",
};
const DOT_LABEL = {
    adeguato: "ADEGUATO",
    non_adeguato: "NON ADEGUATO",
    assente: "ASSENTE",
};
const DOT_CYCLE = ["adeguato", "non_adeguato", "assente"];

// Livelli dal vertice alla base. baseH = altezza minima; cresce con le voci custom.
const LEVELS = [
    {
        id: "crescita", baseH: 160, color: COLORS.tealApex,
        strip: { top: 70, h: 44, maxW: 112, font: 8.5 },
        titolo: "CRESCITA DEL CAPITALE",
        inputVoce: "crescita_capitale",
        customW: null, // apice troppo stretto per voci custom
    },
    {
        id: "cassa_grandi", baseH: 80, color: COLORS.teal,
        strip: { top: 0, h: 30, maxW: 205, font: 9.5 },
        titolo: "CASSA PER LE GRANDI ESIGENZE",
        inputVoce: "cassa_grandi",
        customW: 240,
    },
    {
        id: "cassa_lievi", baseH: 80, color: COLORS.teal,
        strip: { top: 0, h: 30, maxW: 300, font: 10 },
        titolo: "CASSA PER LE LIEVI ESIGENZE",
        inputVoce: "cassa_lievi",
        customW: 310,
    },
    {
        id: "liquidita", baseH: 80, color: COLORS.teal,
        strip: { top: 0, h: 30, maxW: 400, font: 10 },
        titolo: "LIQUIDITÀ GIORNALIERA - CONTO CORRENTE -",
        inputVoce: "liquidita_giornaliera",
        customW: 370,
    },
    {
        id: "perdita", baseH: 96, color: COLORS.green,
        strip: { top: 0, h: 36, maxW: 480, font: 8.5 },
        titolo: "PERDITA DEI BENI DOVUTA DA INCENDI/ EVENTI ATMOSFERICI/ ALLUVIONI/TERREMOTI:",
        voci: [
            { id: "perdita_beni_immobili", label: "IMMOBILI, sei protetto fino a" },
            { id: "perdita_beni_aziende", label: "AZIENDE, sei protetto fino a" },
        ],
        customW: 430,
    },
    {
        id: "danni", baseH: 124, color: COLORS.red,
        strip: { top: 0, h: 28, maxW: 600, font: 10 },
        titolo: "IN CASO DI DANNI PROVOCATI AD ALTRI, DOVUTI A:",
        voci: [
            { id: "danni_veicoli", label: "VEICOLI, sei protetto fino a" },
            { id: "danni_immobili", label: "IMMOBILI, sei protetto fino a" },
            { id: "danni_professioni", label: "PROFESSIONI, sei protetto fino a" },
            { id: "danni_vita_privata", label: "VITA PRIVATA, sei protetto fino a" },
        ],
        customW: 430,
    },
    {
        id: "premorienza", baseH: 84, color: COLORS.red,
        strip: { top: 0, h: 28, maxW: 700, font: 10 },
        titolo: "IN CASO DI PREMORIENZA DOVUTA A:",
        voci: [
            { id: "premorienza_malattia", label: "MALATTIA, sei protetto fino a" },
            { id: "premorienza_infortunio", label: "INFORTUNIO, sei protetto fino a" },
        ],
        customW: 430,
    },
    {
        id: "invalidita", baseH: 102, color: COLORS.red,
        strip: { top: 0, h: 28, maxW: 820, font: 10 },
        titolo: "IN CASO DI INVALIDITÀ DOVUTA A:",
        voci: [
            { id: "invalidita_malattia", label: "MALATTIA, sei protetto fino a" },
            { id: "invalidita_infortunio", label: "INFORTUNIO, sei protetto fino a" },
            { id: "invalidita_non_autosufficienza", label: "NON AUTOSUFFICIENZA, sei protetto fino a" },
        ],
        customW: 430,
    },
];

// Zone a destra: colori coerenti con i livelli che raggruppano
const WEDGE_DEFS = [
    { label: "INVESTIMENTO", from: "crescita", to: "crescita", color: COLORS.tealApex },
    { label: "RISPARMIO", from: "cassa_grandi", to: "liquidita", color: COLORS.teal },
    { label: "PROTEZIONE DEL PATRIMONIO", from: "perdita", to: "danni", color: COLORS.green },
    { label: "PROTEZIONE DEL REDDITO", from: "premorienza", to: "invalidita", color: COLORS.red },
];

export function fmtEur(v) {
    if (v == null || v === "" || Number.isNaN(Number(v))) return "";
    const n = Math.round(Number(v));
    if (n === 0) return "";
    return `${n.toLocaleString("it-IT")} €`;
}

function resolveLogo(logo) {
    if (!logo) return null;
    if (logo.startsWith("data:") || logo.startsWith("http")) return logo;
    return `${process.env.REACT_APP_BACKEND_URL}${logo}`;
}

function normEredi(list) {
    const b = (Array.isArray(list) ? list : []).map((e) => {
        if (typeof e === "string") return e;
        if (e && typeof e === "object") return String(e.nome || e.label || "");
        return e == null ? "" : String(e);
    });
    while (b.length < 4) b.push("");
    return b.slice(0, 4);
}

// ─────────────────────────────────────────────────────────────
export default function PiramidePrivati({
    voci_calcolate = {},
    dati_reddito = {},
    testamento = false,
    eredi_legittimi = [],
    override_voci = {},
    stato_voci = {},
    voci_custom = {},
    onSave,                 // (payload) => Promise | null → read-only
    onRichiediPreventivo,   // (voce_id, label) => void (portale)
    agenziaLogo,
    agenziaName = "Assicurazioni",
    clienteNome = "",
}) {
    const editable = typeof onSave === "function";
    const [reddito, setReddito] = useState(dati_reddito || {});
    const [test, setTest] = useState(!!testamento);
    const [eredi, setEredi] = useState(() => normEredi(eredi_legittimi));
    const [overrides, setOverrides] = useState(override_voci || {});
    const [stati, setStati] = useState(stato_voci || {});
    const [custom, setCustom] = useState(voci_custom || {});
    const [saving, setSaving] = useState(false);

    useEffect(() => { setReddito(dati_reddito || {}); }, [dati_reddito]);
    useEffect(() => { setTest(!!testamento); }, [testamento]);
    useEffect(() => {
        const b = Array.isArray(eredi_legittimi) ? [...eredi_legittimi] : [];
        while (b.length < 4) b.push("");
        setEredi(b.slice(0, 4));
    }, [eredi_legittimi]);
    useEffect(() => { setOverrides(override_voci || {}); }, [override_voci]);
    useEffect(() => { setStati(stato_voci || {}); }, [stato_voci]);
    useEffect(() => { setCustom(voci_custom || {}); }, [voci_custom]);

    // ── geometria dinamica: la piramide cresce con le voci custom ──
    const layout = (() => {
        let y = 0;
        const map = {};
        for (const lvl of LEVELS) {
            const nCustom = (custom[lvl.id] || []).length;
            const h = lvl.baseH + nCustom * ROW_H;
            map[lvl.id] = { yTop: y, h };
            y += h;
        }
        return { map, H: y };
    })();
    const H = layout.H;
    const xRight = (y) => CX + (y / H) * CX;

    const salva = useCallback(async () => {
        if (!editable) return;
        setSaving(true);
        try {
            await onSave({
                dati_reddito: reddito,
                testamento: test,
                eredi_legittimi: eredi.filter((e) => typeof e === "string" && e.trim()),
                override_voci: overrides,
                stato_voci: stati,
                voci_custom: custom,
            });
            toast.success("Piramide salvata");
        } catch (e) { toast.error("Errore salvataggio: " + (e.response?.data?.detail || e.message)); }
        finally { setSaving(false); }
    }, [editable, onSave, reddito, test, eredi, overrides, stati, custom]);

    const capitaleVoce = (vid) => {
        const ov = overrides[vid];
        if (ov != null && ov !== "") return Number(ov) || 0;
        return voci_calcolate[vid]?.capitale || 0;
    };
    const statoVoce = (vid) => {
        if (stati[vid]) return stati[vid];
        const ov = overrides[vid];
        if (ov != null && ov !== "") return Number(ov) > 0 ? "adeguato" : "assente";
        return voci_calcolate[vid]?.stato || "assente";
    };
    const cycleStato = (vid) => {
        setStati((s) => {
            const cur = s[vid];
            if (!cur) return { ...s, [vid]: DOT_CYCLE[0] };
            const idx = DOT_CYCLE.indexOf(cur);
            if (idx === DOT_CYCLE.length - 1) {
                const nx = { ...s };
                delete nx[vid];   // torna ad automatico
                return nx;
            }
            return { ...s, [vid]: DOT_CYCLE[idx + 1] };
        });
    };
    const onDotClick = (voce) => {
        if (editable) { cycleStato(voce.id); return; }
        const st = statoVoce(voce.id);
        if (onRichiediPreventivo && st !== "adeguato") onRichiediPreventivo(voce.id, voce.label);
    };

    // ── voci custom ──
    const addCustom = (levelId) => {
        setCustom((c) => ({
            ...c,
            [levelId]: [...(c[levelId] || []), {
                id: `custom_${Date.now()}`, label: "", capitale: "", stato: "assente",
            }],
        }));
    };
    const updateCustom = (levelId, idx, patch) => {
        setCustom((c) => ({
            ...c,
            [levelId]: (c[levelId] || []).map((v, i) => i === idx ? { ...v, ...patch } : v),
        }));
    };
    const removeCustom = (levelId, idx) => {
        setCustom((c) => ({
            ...c,
            [levelId]: (c[levelId] || []).filter((_, i) => i !== idx),
        }));
    };
    const cycleCustomStato = (levelId, idx) => {
        setCustom((c) => {
            const list = c[levelId] || [];
            const cur = list[idx]?.stato || "assente";
            const nx = DOT_CYCLE[(DOT_CYCLE.indexOf(cur) + 1) % DOT_CYCLE.length];
            return { ...c, [levelId]: list.map((v, i) => i === idx ? { ...v, stato: nx } : v) };
        });
    };
    const onCustomDotClick = (levelId, idx, voce) => {
        if (editable) { cycleCustomStato(levelId, idx); return; }
        if (onRichiediPreventivo && (voce.stato || "assente") !== "adeguato") {
            onRichiediPreventivo(voce.id, voce.label || "Copertura personalizzata");
        }
    };

    const logoSrc = resolveLogo(agenziaLogo);

    return (
        <div className="bg-white rounded-lg border-2 border-slate-800 p-4 md:p-6" data-testid="piramide-privati">
            {/* HEADER: logo in alto a SINISTRA + titolo a destra */}
            <div className="flex items-start justify-between gap-4 mb-2 pb-3 border-b border-slate-300 flex-wrap">
                <div className="flex items-center gap-3">
                    {logoSrc ? (
                        <img src={logoSrc} alt={agenziaName} className="h-14 md:h-16 w-auto object-contain"
                             data-testid="piramide-logo" />
                    ) : (
                        <div className="text-xl font-bold text-sky-900">{agenziaName}</div>
                    )}
                </div>
                <div className="text-right">
                    <div className="text-[11px] uppercase tracking-widest text-slate-500 font-semibold">
                        Piramide della protezione di:
                    </div>
                    <div className="border border-slate-400 rounded px-4 py-1 mt-1 min-w-[220px] text-sm font-bold text-slate-800 text-center"
                         data-testid="piramide-cliente-nome">
                        {clienteNome || "\u00A0"}
                    </div>
                </div>
            </div>

            {/* LEGENDA */}
            <div className="flex items-center gap-4 mb-2 text-[11px] font-semibold text-slate-700 flex-wrap">
                <span>LEGENDA:</span>
                {DOT_CYCLE.map((s) => (
                    <span key={s} className="flex items-center gap-1.5">
                        <span className="w-4 h-4 rounded-full border border-slate-400"
                              style={{ background: DOT_COLORS[s] }} /> {DOT_LABEL[s]}
                    </span>
                ))}
                {editable && (
                    <span className="text-[10px] text-slate-400 font-normal italic">
                        · clicca un pallino per cambiare colore · «+» sulla banda per aggiungere una voce
                    </span>
                )}
            </div>

            {/* AREA PIRAMIDE — scroll orizzontale su schermi stretti */}
            <div className="overflow-x-auto pb-2">
                <div className="relative" style={{ width: TOTAL_W, height: H, minWidth: TOTAL_W }}>

                    {/* Sidebar dati reddito: in alto a sinistra, fuori dal triangolo */}
                    <div className="absolute left-0 top-1 w-[295px] space-y-1 text-[11px] z-20"
                         data-testid="piramide-sidebar">
                        <SidebarField label="IL TUO REDDITO ATTUALE" value={reddito.reddito_attuale}
                                      editable={editable}
                                      onChange={(v) => setReddito((s) => ({ ...s, reddito_attuale: v }))} />
                        <div className="flex items-center gap-1">
                            <span className="font-semibold text-slate-700 text-[10px] uppercase">Estratto conto contributivo:</span>
                            <label className="ml-1 mr-1 text-[10px]">
                                <input type="checkbox" disabled={!editable}
                                       checked={reddito.estratto_conto === true}
                                       onChange={() => editable && setReddito((s) => ({ ...s, estratto_conto: true }))} /> Sì
                            </label>
                            <label className="text-[10px]">
                                <input type="checkbox" disabled={!editable}
                                       checked={reddito.estratto_conto === false}
                                       onChange={() => editable && setReddito((s) => ({ ...s, estratto_conto: false }))} /> No
                            </label>
                        </div>
                        <div className="text-[9px] text-slate-600 font-semibold uppercase pt-0.5">
                            Il tuo reddito lordo annuale in caso di:
                        </div>
                        <SidebarField label="INVALIDITÀ: 66%-99%" value={reddito.reddito_invalidita_66_99}
                                      editable={editable}
                                      onChange={(v) => setReddito((s) => ({ ...s, reddito_invalidita_66_99: v }))} />
                        <SidebarField label="INABILITÀ: 100%" value={reddito.reddito_inabilita_100}
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

                    {/* TRIANGOLO CLIPPATO: tutto il contenuto resta dentro i bordi */}
                    <div className="absolute top-0 left-0 bg-white"
                         style={{
                             width: PYR_W, height: H,
                             clipPath: "polygon(50% 0%, 100% 100%, 0% 100%)",
                         }}>
                        {LEVELS.map((lvl) => (
                            <Level key={lvl.id} lvl={lvl}
                                   yTop={layout.map[lvl.id].yTop}
                                   h={layout.map[lvl.id].h}
                                   editable={editable}
                                   capitaleVoce={capitaleVoce}
                                   statoVoce={statoVoce}
                                   onDotClick={onDotClick}
                                   onChangeOverride={(vid, v) => setOverrides((s) => ({ ...s, [vid]: v }))}
                                   canRequestQuote={!editable && !!onRichiediPreventivo}
                                   customVoci={custom[lvl.id] || []}
                                   onAddCustom={() => addCustom(lvl.id)}
                                   onUpdateCustom={(idx, patch) => updateCustom(lvl.id, idx, patch)}
                                   onRemoveCustom={(idx) => removeCustom(lvl.id, idx)}
                                   onCustomDotClick={(idx, voce) => onCustomDotClick(lvl.id, idx, voce)}
                            />
                        ))}
                    </div>

                    {/* Contorno triangolo (sopra il clip, non intercetta i click) */}
                    <svg width={PYR_W} height={H} className="absolute top-0 left-0 pointer-events-none z-10"
                         style={{ overflow: "visible" }}>
                        <polygon points={`${CX},0 ${PYR_W},${H} 0,${H}`}
                                 fill="none" stroke="#1e293b" strokeWidth="2" strokeLinejoin="round" />
                    </svg>

                    {/* Cunei colorati zone a destra */}
                    {WEDGE_DEFS.map((w) => {
                        const y1 = layout.map[w.from].yTop + (w.from === "crescita" ? 0 : 4);
                        const y2 = layout.map[w.to].yTop + layout.map[w.to].h - 4;
                        const left = xRight(y1) + 6;
                        const dx = xRight(y2) - xRight(y1);
                        return (
                            <div key={w.label}
                                 className="absolute flex items-center justify-center text-center"
                                 style={{
                                     top: y1, height: y2 - y1,
                                     left, width: TOTAL_W - left,
                                     background: w.color,
                                     clipPath: `polygon(0 0, 100% 0, 100% 100%, ${dx}px 100%)`,
                                     paddingLeft: dx,
                                 }}
                                 data-testid={`piramide-zona-${w.label.toLowerCase().replace(/ /g, "-")}`}>
                                <span className="text-white font-bold uppercase tracking-wider text-[11px] leading-tight px-2 text-center"
                                      style={{ maxWidth: TOTAL_W - left - dx - 8, textShadow: "0 1px 2px rgba(0,0,0,.25)" }}>
                                    {w.label}
                                </span>
                            </div>
                        );
                    })}
                </div>
            </div>

            {/* FOOTER: testamento + eredi */}
            <div className="mt-4 pt-4 border-t border-slate-300 text-[11px]">
                <div className="text-center mb-3 font-semibold">
                    TESTAMENTO:{" "}
                    <label className="ml-2 mr-2">
                        <input type="checkbox" disabled={!editable} checked={test === true}
                               onChange={() => editable && setTest(true)} data-testid="piramide-testamento-si" /> Sì
                    </label>
                    <label>
                        <input type="checkbox" disabled={!editable} checked={test === false}
                               onChange={() => editable && setTest(false)} data-testid="piramide-testamento-no" /> No
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
                               className="border border-slate-400 rounded px-2 py-2 text-[11px] text-center" />
                    ))}
                </div>
            </div>

            {editable && (
                <div className="mt-4 flex justify-end">
                    <button onClick={salva} disabled={saving}
                            className="bg-sky-700 hover:bg-sky-800 text-white text-sm px-5 py-2 rounded font-medium disabled:opacity-60 transition-colors"
                            data-testid="piramide-salva">
                        {saving ? "Salvataggio..." : "Salva Piramide"}
                    </button>
                </div>
            )}
        </div>
    );
}

// ─────────────────────────────────────────────────────────────
function Level({
    lvl, yTop, h, editable, capitaleVoce, statoVoce, onDotClick, onChangeOverride, canRequestQuote,
    customVoci, onAddCustom, onUpdateCustom, onRemoveCustom, onCustomDotClick,
}) {
    const hasRows = Array.isArray(lvl.voci) && lvl.voci.length > 0;
    const canAdd = editable && lvl.customW;
    return (
        <div className="absolute left-0 w-full" style={{ top: yTop, height: h }}
             data-testid={`piramide-livello-${lvl.id}`}>
            {/* strip colorata: piena larghezza, il clip del wrapper la taglia a trapezio */}
            <div className="absolute left-0 w-full flex items-center justify-center gap-1.5"
                 style={{ top: lvl.strip.top, height: lvl.strip.h, background: lvl.color }}>
                <span className="text-white font-bold uppercase text-center leading-tight tracking-tight"
                      style={{ maxWidth: lvl.strip.maxW, fontSize: lvl.strip.font }}>
                    {lvl.titolo}
                </span>
                {canAdd && (
                    <button type="button" onClick={onAddCustom}
                            title="Aggiungi una voce a questa sezione"
                            className="w-[15px] h-[15px] rounded-full bg-white/30 hover:bg-white/60 text-white leading-none flex items-center justify-center transition-colors flex-shrink-0"
                            style={{ fontSize: 11 }}
                            data-testid={`piramide-add-voce-${lvl.id}`}>
                        +
                    </button>
                )}
            </div>
            {/* contenuto sotto la strip */}
            <div className="absolute left-0 w-full flex flex-col items-center justify-center"
                 style={{ top: lvl.strip.top + lvl.strip.h, height: h - lvl.strip.top - lvl.strip.h }}>
                {hasRows && lvl.voci.map((voce) => {
                    const cap = capitaleVoce(voce.id);
                    const st = statoVoce(voce.id);
                    const clickable = editable || (canRequestQuote && st !== "adeguato");
                    return (
                        <div key={voce.id} className="flex items-center justify-center gap-2"
                             style={{ width: 430, padding: "1px 0" }}>
                            <span className="flex-1 text-right uppercase font-medium text-slate-800"
                                  style={{ fontSize: 10.5 }}>
                                {voce.label}
                            </span>
                            <input type="text"
                                   value={cap ? fmtEur(cap) : ""}
                                   disabled={!editable}
                                   onChange={(e) => {
                                       const raw = e.target.value.replace(/[^\d]/g, "");
                                       onChangeOverride(voce.id, raw);
                                   }}
                                   className="bg-white border border-slate-500 rounded-sm px-1.5 py-0.5 text-right font-mono w-28 focus:outline-none focus:ring-2 focus:ring-sky-500"
                                   style={{ fontSize: 10.5, height: 20 }}
                                   data-testid={`piramide-input-${voce.id}`} />
                            <button type="button"
                                    onClick={() => onDotClick(voce)}
                                    title={DOT_LABEL[st] + (editable ? " — clicca per cambiare" : (st !== "adeguato" ? " — clicca per richiedere un preventivo" : ""))}
                                    className={`w-[18px] h-[18px] rounded-full border-2 border-white shadow-sm flex-shrink-0 transition-transform ${clickable ? "cursor-pointer hover:scale-125" : "cursor-default"}`}
                                    style={{ background: DOT_COLORS[st], outline: "1px solid #64748b" }}
                                    data-testid={`piramide-pallino-${voce.id}`} />
                        </div>
                    );
                })}
                {!hasRows && (
                    // spazio bianco editabile (livelli risparmio/investimento)
                    <input type="text"
                           value={capitaleVoce(lvl.inputVoce) ? fmtEur(capitaleVoce(lvl.inputVoce)) : ""}
                           disabled={!editable}
                           onChange={(e) => {
                               const raw = e.target.value.replace(/[^\d]/g, "");
                               onChangeOverride(lvl.inputVoce, raw);
                           }}
                           placeholder="€"
                           className="bg-white border border-slate-500 rounded-sm px-1.5 py-0.5 text-center font-mono focus:outline-none focus:ring-2 focus:ring-sky-500"
                           style={{ fontSize: 10.5, height: 22, width: lvl.id === "crescita" ? 78 : 110 }}
                           data-testid={`piramide-input-${lvl.inputVoce}`} />
                )}
                {/* voci custom aggiunte dall'agenzia */}
                {customVoci.map((voce, idx) => {
                    const st = voce.stato || "assente";
                    const clickable = editable || (canRequestQuote && st !== "adeguato");
                    return (
                        <div key={voce.id || idx} className="flex items-center justify-center gap-2"
                             style={{ width: lvl.customW || 430, padding: "1px 0" }}
                             data-testid={`piramide-custom-${lvl.id}-${idx}`}>
                            {editable ? (
                                <input type="text"
                                       value={voce.label || ""}
                                       onChange={(e) => onUpdateCustom(idx, { label: e.target.value })}
                                       placeholder="VOCE PERSONALIZZATA, protetto fino a"
                                       className="flex-1 text-right uppercase font-medium text-slate-800 bg-transparent border-0 border-b border-dashed border-slate-400 focus:outline-none focus:border-sky-500"
                                       style={{ fontSize: 10 }}
                                       data-testid={`piramide-custom-label-${lvl.id}-${idx}`} />
                            ) : (
                                <span className="flex-1 text-right uppercase font-medium text-slate-800"
                                      style={{ fontSize: 10.5 }}>
                                    {voce.label || "—"}
                                </span>
                            )}
                            <input type="text"
                                   value={voce.capitale ? fmtEur(voce.capitale) : ""}
                                   disabled={!editable}
                                   onChange={(e) => {
                                       const raw = e.target.value.replace(/[^\d]/g, "");
                                       onUpdateCustom(idx, { capitale: raw });
                                   }}
                                   className="bg-white border border-slate-500 rounded-sm px-1.5 py-0.5 text-right font-mono w-24 focus:outline-none focus:ring-2 focus:ring-sky-500"
                                   style={{ fontSize: 10.5, height: 20 }}
                                   data-testid={`piramide-custom-capitale-${lvl.id}-${idx}`} />
                            <button type="button"
                                    onClick={() => onCustomDotClick(idx, voce)}
                                    title={DOT_LABEL[st] + (editable ? " — clicca per cambiare" : "")}
                                    className={`w-[18px] h-[18px] rounded-full border-2 border-white shadow-sm flex-shrink-0 transition-transform ${clickable ? "cursor-pointer hover:scale-125" : "cursor-default"}`}
                                    style={{ background: DOT_COLORS[st], outline: "1px solid #64748b" }}
                                    data-testid={`piramide-custom-pallino-${lvl.id}-${idx}`} />
                            {editable && (
                                <button type="button" onClick={() => onRemoveCustom(idx)}
                                        title="Rimuovi voce"
                                        className="text-slate-400 hover:text-rose-600 font-bold leading-none flex-shrink-0"
                                        style={{ fontSize: 12 }}
                                        data-testid={`piramide-custom-remove-${lvl.id}-${idx}`}>
                                    ×
                                </button>
                            )}
                        </div>
                    );
                })}
            </div>
        </div>
    );
}

function SidebarField({ label, value, editable, onChange }) {
    return (
        <div className="flex items-center gap-1.5">
            <span className="font-semibold text-slate-700 text-[10px] uppercase whitespace-nowrap">{label}:</span>
            <input type="text"
                   value={value ?? ""}
                   disabled={!editable}
                   onChange={(e) => onChange(e.target.value)}
                   className="border border-slate-400 rounded-sm px-1.5 py-0.5 text-[10px] w-[90px] font-mono text-right" />
        </div>
    );
}
