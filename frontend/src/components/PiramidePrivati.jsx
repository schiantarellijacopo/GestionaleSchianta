import { useEffect, useState, useCallback } from "react";
import { toast } from "sonner";

// -----------------------------------------------------------------------------
// PIRAMIDE DELLA PROTEZIONE — replica fedele del modello stampato Schiantarelli.
// Triangolo unico con clip-path sul wrapper: tutte le scritte/pallini restano
// SEMPRE dentro i bordi. Geometria dinamica: aggiungendo voci custom la
// piramide cresce in altezza mantenendo la forma.
// -----------------------------------------------------------------------------

// Layout compatto per stampa A4 (max ~830px totali).
const PYR_W = 720;           // larghezza base triangolo (px)
const CX = PYR_W / 2;        // apice orizzontale
const WEDGE_AREA = 105;      // colonna cunei zone a destra (compatta)
const TOTAL_W = PYR_W + WEDGE_AREA;   // 825 px
const ROW_H = 22;            // altezza extra per ogni voce custom

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

// Geometria fissa per livello (id → colore, strip, larghezza voci custom).
const GEOM = {
    crescita: { baseH: 130, color: COLORS.tealApex, strip: { top: 56, h: 38, maxW: 88, font: 8 }, customW: null },
    cassa_grandi: { baseH: 66, color: COLORS.teal, strip: { top: 0, h: 26, maxW: 150, font: 8.5 }, customW: 180 },
    cassa_lievi: { baseH: 66, color: COLORS.teal, strip: { top: 0, h: 26, maxW: 220, font: 9 }, customW: 240 },
    liquidita: { baseH: 66, color: COLORS.teal, strip: { top: 0, h: 26, maxW: 300, font: 9 }, customW: 290 },
    perdita: { color: COLORS.green, strip: { top: 0, h: 32, maxW: 350, font: 7.5 }, customW: 340 },
    danni: { color: COLORS.green, strip: { top: 0, h: 24, maxW: 430, font: 9 }, customW: 340 },
    premorienza: { color: COLORS.red, strip: { top: 0, h: 24, maxW: 500, font: 9 }, customW: 340 },
    invalidita: { color: COLORS.red, strip: { top: 0, h: 24, maxW: 580, font: 9 }, customW: 340 },
};

// Template di default (modello PRIVATI) usato se il backend non ne fornisce uno.
const DEFAULT_TEMPLATE = {
    mostra_testamento: true,
    levels: [
        { id: "crescita", modo: "input", input_voce: "crescita_capitale", titolo: "CRESCITA DEL CAPITALE" },
        { id: "cassa_grandi", modo: "input", input_voce: "cassa_grandi", titolo: "CASSA PER LE GRANDI ESIGENZE" },
        { id: "cassa_lievi", modo: "input", input_voce: "cassa_lievi", titolo: "CASSA PER LE LIEVI ESIGENZE" },
        { id: "liquidita", modo: "input", input_voce: "liquidita_giornaliera", titolo: "LIQUIDITÀ GIORNALIERA - CONTO CORRENTE -" },
        {
            id: "perdita", modo: "voci",
            titolo: "PERDITA DEI BENI DOVUTA DA INCENDI/ EVENTI ATMOSFERICI/ ALLUVIONI/TERREMOTI:",
            voci: [
                { id: "perdita_beni_immobili", label: "IMMOBILI, sei protetto fino a" },
                { id: "perdita_beni_aziende", label: "AZIENDE, sei protetto fino a" },
            ],
        },
        {
            id: "danni", modo: "voci",
            titolo: "IN CASO DI DANNI PROVOCATI AD ALTRI, DOVUTI A:",
            voci: [
                { id: "danni_veicoli", label: "VEICOLI, sei protetto fino a" },
                { id: "danni_immobili", label: "IMMOBILI, sei protetto fino a" },
                { id: "danni_professioni", label: "PROFESSIONI, sei protetto fino a" },
                { id: "danni_vita_privata", label: "VITA PRIVATA, sei protetto fino a" },
            ],
        },
        {
            id: "premorienza", modo: "voci",
            titolo: "IN CASO DI PREMORIENZA DOVUTA A:",
            voci: [
                { id: "premorienza_malattia", label: "MALATTIA, sei protetto fino a" },
                { id: "premorienza_infortunio", label: "INFORTUNIO, sei protetto fino a" },
            ],
        },
        {
            id: "invalidita", modo: "voci",
            titolo: "IN CASO DI INVALIDITÀ DOVUTA A:",
            voci: [
                { id: "invalidita_malattia", label: "MALATTIA, sei protetto fino a" },
                { id: "invalidita_infortunio", label: "INFORTUNIO, sei protetto fino a" },
                { id: "invalidita_non_autosufficienza", label: "NON AUTOSUFFICIENZA, sei protetto fino a" },
            ],
        },
    ],
    wedges: [
        { label: "INVESTIMENTO", from: "crescita", to: "crescita" },
        { label: "RISPARMIO", from: "cassa_grandi", to: "liquidita" },
        { label: "PROTEZIONE DEL PATRIMONIO", from: "perdita", to: "danni" },
        { label: "PROTEZIONE DEL REDDITO", from: "premorienza", to: "invalidita" },
    ],
};

const WEDGE_COLORS = [COLORS.tealApex, COLORS.teal, COLORS.green, COLORS.red];

// Costruisce i livelli renderizzabili dal template (altezza in base al n° di voci).
function buildLevels(template) {
    const src = template?.levels?.length ? template.levels : DEFAULT_TEMPLATE.levels;
    return src.map((l) => {
        const g = GEOM[l.id] || GEOM.danni;
        const voci = l.modo === "voci" ? (l.voci || []) : null;
        const baseH = voci
            ? g.strip.top + g.strip.h + Math.max(1, voci.length) * 22 + 6
            : g.baseH;
        return {
            id: l.id, baseH, color: g.color, strip: g.strip, titolo: l.titolo,
            voci: voci || undefined,
            inputVoce: l.modo === "input" ? l.input_voce : undefined,
            customW: g.customW,
        };
    });
}

function buildWedges(template) {
    const src = (template?.wedges?.length === 4 ? template.wedges : DEFAULT_TEMPLATE.wedges);
    return src.map((w, i) => ({
        label: w.label,
        from: DEFAULT_TEMPLATE.wedges[i].from,
        to: DEFAULT_TEMPLATE.wedges[i].to,
        color: WEDGE_COLORS[i],
    }));
}

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
    onPrepopolate,          // () => Promise<datiRedditoSuggeriti> — bottone "Prepopola"
    onRichiediPreventivo,   // (voce_id, label) => void (portale)
    template = null,        // modello globale (privati/aziende) dal backend
    tipoPiramide = "privati",
    agenziaLogo,
    agenziaName = "Assicurazioni",
    clienteNome = "",
}) {
    const editable = typeof onSave === "function";
    const isAziende = tipoPiramide === "aziende";
    const [reddito, setReddito] = useState(dati_reddito || {});
    const [test, setTest] = useState(!!testamento);
    const [eredi, setEredi] = useState(() => normEredi(eredi_legittimi));
    const [overrides, setOverrides] = useState(override_voci || {});
    const [stati, setStati] = useState(stato_voci || {});
    const [custom, setCustom] = useState(voci_custom || {});
    const [saving, setSaving] = useState(false);
    const [prepopolando, setPrepopolando] = useState(false);

    // Sync dalle prop SOLO quando il contenuto cambia davvero (firma JSON).
    // Con dipendenza sull'oggetto, i default "= {}" creavano una nuova referenza
    // ad ogni render e resettavano lo stato locale (input/pallini/+ non funzionanti).
    const sigReddito = JSON.stringify(dati_reddito || {});
    const sigEredi = JSON.stringify(eredi_legittimi || []);
    const sigOverrides = JSON.stringify(override_voci || {});
    const sigStati = JSON.stringify(stato_voci || {});
    const sigCustom = JSON.stringify(voci_custom || {});
    /* eslint-disable react-hooks/exhaustive-deps */
    useEffect(() => { setReddito(dati_reddito || {}); }, [sigReddito]);
    useEffect(() => { setTest(!!testamento); }, [testamento]);
    useEffect(() => { setEredi(normEredi(eredi_legittimi)); }, [sigEredi]);
    useEffect(() => { setOverrides(override_voci || {}); }, [sigOverrides]);
    useEffect(() => { setStati(stato_voci || {}); }, [sigStati]);
    useEffect(() => { setCustom(voci_custom || {}); }, [sigCustom]);
    /* eslint-enable react-hooks/exhaustive-deps */

    // ── template → livelli e cunei renderizzabili ──
    const LEVELS = buildLevels(template);
    const WEDGE_DEFS = buildWedges(template);
    const mostraTestamento = !template || template.mostra_testamento !== false;

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

    const prepopola = useCallback(async () => {
        if (!editable || !onPrepopolate) return;
        setPrepopolando(true);
        try {
            const suggeriti = await onPrepopolate();
            setReddito((s) => ({ ...s, ...suggeriti }));
            toast.success("Dati reddito pre-popolati dall'estratto INPS. Verifica e salva.");
        } catch (e) {
            toast.error(e.response?.data?.detail || e.message || "Errore prepopolamento");
        } finally { setPrepopolando(false); }
    }, [editable, onPrepopolate]);

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
        const cur = statoVoce(vid); // parte dallo stato attualmente mostrato
        const nx = DOT_CYCLE[(DOT_CYCLE.indexOf(cur) + 1) % DOT_CYCLE.length];
        setStati((s) => ({ ...s, [vid]: nx }));
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

            {/* SIDEBAR DATI REDDITO — sopra la piramide, layout orizzontale compatto */}
            <div className="border border-slate-300 rounded p-2 mb-2 bg-slate-50" data-testid="piramide-sidebar">
                {editable && onPrepopolate && (
                    <div className="flex items-center justify-between mb-2 pb-1 border-b border-slate-200">
                        <span className="text-[10px] font-semibold text-slate-600 uppercase">Dati reddito cliente</span>
                        <button type="button" onClick={prepopola} disabled={prepopolando}
                                className="bg-emerald-600 hover:bg-emerald-700 text-white text-[10px] font-semibold px-2.5 py-1 rounded disabled:opacity-60 transition-colors flex items-center gap-1"
                                title="Riempi automaticamente dai dati anagrafica / estratto INPS caricato"
                                data-testid="piramide-btn-prepopola">
                            {prepopolando ? "…" : "⚡ Prepopola dati"}
                        </button>
                    </div>
                )}
                <div className="grid grid-cols-2 md:grid-cols-4 gap-x-3 gap-y-1 text-[10px]">
                    {isAziende ? (
                        <>
                            <SidebarField label="Fatturato" value={reddito.reddito_attuale}
                                          editable={editable}
                                          onChange={(v) => setReddito((s) => ({ ...s, reddito_attuale: v }))} />
                            <SidebarField label="Utile" value={reddito.reddito_invalidita_66_99}
                                          editable={editable}
                                          onChange={(v) => setReddito((s) => ({ ...s, reddito_invalidita_66_99: v }))} />
                            <SidebarField label="EBITDA" value={reddito.reddito_inabilita_100}
                                          editable={editable}
                                          onChange={(v) => setReddito((s) => ({ ...s, reddito_inabilita_100: v }))} />
                            <SidebarField label="N. dipendenti" value={reddito.reddito_superstiti}
                                          editable={editable}
                                          onChange={(v) => setReddito((s) => ({ ...s, reddito_superstiti: v }))} />
                            <SidebarField label="N. soci" value={reddito.reddito_responsabilita}
                                          editable={editable}
                                          onChange={(v) => setReddito((s) => ({ ...s, reddito_responsabilita: v }))} />
                            <SidebarField label="Perdita beni" value={reddito.reddito_perdita_beni}
                                          editable={editable}
                                          onChange={(v) => setReddito((s) => ({ ...s, reddito_perdita_beni: v }))} />
                        </>
                    ) : (
                    <>
                    <SidebarField label="Reddito attuale" value={reddito.reddito_attuale}
                                  editable={editable}
                                  onChange={(v) => setReddito((s) => ({ ...s, reddito_attuale: v }))} />
                    <div className="flex items-center gap-1 text-[9px]">
                        <span className="font-semibold text-slate-700 uppercase whitespace-nowrap">Est. conto:</span>
                        <label className="ml-1 mr-1">
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
                    <SidebarField label="Reddito lordo invalidità 66-99%" value={reddito.reddito_invalidita_66_99}
                                  editable={editable}
                                  onChange={(v) => setReddito((s) => ({ ...s, reddito_invalidita_66_99: v }))} />
                    <SidebarField label="Inabilità 100%" value={reddito.reddito_inabilita_100}
                                  editable={editable}
                                  onChange={(v) => setReddito((s) => ({ ...s, reddito_inabilita_100: v }))} />
                    <SidebarField label="Superstiti" value={reddito.reddito_superstiti}
                                  editable={editable}
                                  onChange={(v) => setReddito((s) => ({ ...s, reddito_superstiti: v }))} />
                    <SidebarField label="Responsabilità" value={reddito.reddito_responsabilita}
                                  editable={editable}
                                  onChange={(v) => setReddito((s) => ({ ...s, reddito_responsabilita: v }))} />
                    <SidebarField label="Perdita beni" value={reddito.reddito_perdita_beni}
                                  editable={editable}
                                  onChange={(v) => setReddito((s) => ({ ...s, reddito_perdita_beni: v }))} />
                    </>
                    )}
                </div>
            </div>

            {/* AREA PIRAMIDE — scroll orizzontale su schermi stretti */}
            <div className="overflow-x-auto pb-2">
                <div className="relative mx-auto" style={{ width: TOTAL_W, height: H, minWidth: TOTAL_W }}>

                    {/* LAYER 1 — TRIANGOLO CLIPPATO: solo bg + strip colorate (decorativo, non intercetta click) */}
                    <div className="absolute top-0 left-0 bg-white pointer-events-none"
                         style={{
                             width: PYR_W, height: H,
                             clipPath: "polygon(50% 0%, 100% 100%, 0% 100%)",
                         }}>
                        {LEVELS.map((lvl) => (
                            <LevelBackground key={"bg-" + lvl.id} lvl={lvl}
                                             yTop={layout.map[lvl.id].yTop}
                                             h={layout.map[lvl.id].h} />
                        ))}
                    </div>

                    {/* LAYER 2 — Contorno triangolo (sopra il clip, non intercetta i click) */}
                    <svg width={PYR_W} height={H} className="absolute top-0 left-0 pointer-events-none z-10"
                         style={{ overflow: "visible" }}>
                        <polygon points={`${CX},0 ${PYR_W},${H} 0,${H}`}
                                 fill="none" stroke="#1e293b" strokeWidth="2" strokeLinejoin="round" />
                    </svg>

                    {/* LAYER 3 — Cunei colorati zone a destra (decorativi, non intercettano i click) */}
                    {WEDGE_DEFS.map((w) => {
                        const y1 = layout.map[w.from].yTop + (w.from === "crescita" ? 0 : 4);
                        const y2 = layout.map[w.to].yTop + layout.map[w.to].h - 4;
                        const left = xRight(y1) + 4;
                        const dx = xRight(y2) - xRight(y1);
                        return (
                            <div key={w.label}
                                 className="absolute flex items-center justify-center text-center pointer-events-none z-10"
                                 style={{
                                     top: y1, height: y2 - y1,
                                     left, width: TOTAL_W - left,
                                     background: w.color,
                                     clipPath: `polygon(0 0, 100% 0, 100% 100%, ${dx}px 100%)`,
                                     paddingLeft: dx,
                                 }}
                                 data-testid={`piramide-zona-${w.label.toLowerCase().replace(/ /g, "-")}`}>
                                <span className="text-white font-bold uppercase tracking-wider leading-tight px-1 text-center"
                                      style={{ fontSize: 9, maxWidth: TOTAL_W - left - dx - 4, textShadow: "0 1px 2px rgba(0,0,0,.25)" }}>
                                    {w.label}
                                </span>
                            </div>
                        );
                    })}

                    {/* LAYER 4 (TOP) — CONTENUTO INTERATTIVO: input, pallini, tasto "+", labels.
                        Senza clip-path e con z-20 → click SEMPRE garantiti su qualsiasi browser. */}
                    <div className="absolute top-0 left-0 z-20" style={{ width: PYR_W, height: H }}>
                        {LEVELS.map((lvl) => (
                            <LevelForeground key={"fg-" + lvl.id} lvl={lvl}
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
                                             onCustomDotClick={(idx, voce) => onCustomDotClick(lvl.id, idx, voce)} />
                        ))}
                    </div>
                </div>
            </div>

            {/* FOOTER: testamento + eredi (solo modello privati) */}
            {mostraTestamento && (
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
            )}

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
// LayerBackground: SOLO la strip colorata di fondo, DENTRO il triangolo clippato.
// Nessun click interattivo qui — è puramente decorativo (pointer-events: none).
// ─────────────────────────────────────────────────────────────
function LevelBackground({ lvl, yTop, h }) {
    return (
        <div className="absolute left-0 w-full" style={{ top: yTop, height: h }}>
            <div className="absolute left-0 w-full"
                 style={{ top: lvl.strip.top, height: lvl.strip.h, background: lvl.color }} />
        </div>
    );
}

// ─────────────────────────────────────────────────────────────
// LevelForeground: TESTO strip + tasto "+" + input + pallini.
// Vive nel layer z-20 FUORI dal triangolo clippato → click SEMPRE garantiti.
// ─────────────────────────────────────────────────────────────
function LevelForeground({
    lvl, yTop, h, editable, capitaleVoce, statoVoce, onDotClick, onChangeOverride, canRequestQuote,
    customVoci, onAddCustom, onUpdateCustom, onRemoveCustom, onCustomDotClick,
}) {
    const hasRows = Array.isArray(lvl.voci) && lvl.voci.length > 0;
    const canAdd = editable && lvl.customW;
    return (
        <div className="absolute left-0 w-full" style={{ top: yTop, height: h }}
             data-testid={`piramide-livello-${lvl.id}`}>
            {/* Testo strip + pulsante + (nessun bg, il bg è nel LevelBackground) */}
            <div className="absolute left-0 w-full flex items-center justify-center gap-1.5"
                 style={{ top: lvl.strip.top, height: lvl.strip.h }}>
                <span className="text-white font-bold uppercase text-center leading-tight tracking-tight pointer-events-none"
                      style={{ maxWidth: lvl.strip.maxW, fontSize: lvl.strip.font }}>
                    {lvl.titolo}
                </span>
                {canAdd && (
                    <button type="button" onClick={onAddCustom}
                            title="Aggiungi una voce a questa sezione"
                            className="w-[15px] h-[15px] rounded-full bg-white/30 hover:bg-white/70 text-white leading-none flex items-center justify-center transition-colors flex-shrink-0 cursor-pointer"
                            style={{ fontSize: 11 }}
                            data-testid={`piramide-add-voce-${lvl.id}`}>
                        +
                    </button>
                )}
            </div>
            {/* Contenuto interattivo sotto la strip */}
            <div className="absolute left-0 w-full flex flex-col items-center justify-center"
                 style={{ top: lvl.strip.top + lvl.strip.h, height: h - lvl.strip.top - lvl.strip.h }}>
                {hasRows && lvl.voci.map((voce) => {
                    const cap = capitaleVoce(voce.id);
                    const st = statoVoce(voce.id);
                    const clickable = editable || (canRequestQuote && st !== "adeguato");
                    return (
                        <div key={voce.id} className="flex items-center justify-center gap-1.5"
                             style={{ width: 340, padding: "1px 0" }}>
                            <span className="flex-1 text-right uppercase font-medium text-slate-800 pointer-events-none"
                                  style={{ fontSize: 9.5 }}>
                                {voce.label}
                            </span>
                            <input type="text"
                                   value={cap ? fmtEur(cap) : ""}
                                   disabled={!editable}
                                   onChange={(e) => {
                                       const raw = e.target.value.replace(/[^\d]/g, "");
                                       onChangeOverride(voce.id, raw);
                                   }}
                                   className="bg-white border border-slate-500 rounded-sm px-1 py-0.5 text-right font-mono w-24 focus:outline-none focus:ring-2 focus:ring-sky-500"
                                   style={{ fontSize: 9.5, height: 18 }}
                                   data-testid={`piramide-input-${voce.id}`} />
                            <button type="button"
                                    onClick={() => onDotClick(voce)}
                                    title={DOT_LABEL[st] + (editable ? " — clicca per cambiare" : (st !== "adeguato" ? " — clicca per richiedere un preventivo" : ""))}
                                    className={`w-[16px] h-[16px] rounded-full border-2 border-white shadow-sm flex-shrink-0 transition-transform ${clickable ? "cursor-pointer hover:scale-125" : "cursor-default"}`}
                                    style={{ background: DOT_COLORS[st], outline: "1px solid #64748b" }}
                                    data-testid={`piramide-pallino-${voce.id}`} />
                        </div>
                    );
                })}
                {!hasRows && (
                    <input type="text"
                           value={capitaleVoce(lvl.inputVoce) ? fmtEur(capitaleVoce(lvl.inputVoce)) : ""}
                           disabled={!editable}
                           onChange={(e) => {
                               const raw = e.target.value.replace(/[^\d]/g, "");
                               onChangeOverride(lvl.inputVoce, raw);
                           }}
                           placeholder="€"
                           className="bg-white border border-slate-500 rounded-sm px-1 py-0.5 text-center font-mono focus:outline-none focus:ring-2 focus:ring-sky-500"
                           style={{ fontSize: 9.5, height: 20, width: lvl.id === "crescita" ? 68 : 90 }}
                           data-testid={`piramide-input-${lvl.inputVoce}`} />
                )}
                {customVoci.map((voce, idx) => {
                    const st = voce.stato || "assente";
                    const clickable = editable || (canRequestQuote && st !== "adeguato");
                    return (
                        <div key={voce.id || idx} className="flex items-center justify-center gap-1.5"
                             style={{ width: lvl.customW || 340, padding: "1px 0" }}
                             data-testid={`piramide-custom-${lvl.id}-${idx}`}>
                            {editable ? (
                                <input type="text"
                                       value={voce.label || ""}
                                       onChange={(e) => onUpdateCustom(idx, { label: e.target.value })}
                                       placeholder="VOCE PERSONALIZZATA, protetto fino a"
                                       className="flex-1 text-right uppercase font-medium text-slate-800 bg-transparent border-0 border-b border-dashed border-slate-400 focus:outline-none focus:border-sky-500"
                                       style={{ fontSize: 9 }}
                                       data-testid={`piramide-custom-label-${lvl.id}-${idx}`} />
                            ) : (
                                <span className="flex-1 text-right uppercase font-medium text-slate-800 pointer-events-none"
                                      style={{ fontSize: 9.5 }}>
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
                                   className="bg-white border border-slate-500 rounded-sm px-1 py-0.5 text-right font-mono w-20 focus:outline-none focus:ring-2 focus:ring-sky-500"
                                   style={{ fontSize: 9.5, height: 18 }}
                                   data-testid={`piramide-custom-capitale-${lvl.id}-${idx}`} />
                            <button type="button"
                                    onClick={() => onCustomDotClick(idx, voce)}
                                    title={DOT_LABEL[st] + (editable ? " — clicca per cambiare" : "")}
                                    className={`w-[16px] h-[16px] rounded-full border-2 border-white shadow-sm flex-shrink-0 transition-transform ${clickable ? "cursor-pointer hover:scale-125" : "cursor-default"}`}
                                    style={{ background: DOT_COLORS[st], outline: "1px solid #64748b" }}
                                    data-testid={`piramide-custom-pallino-${lvl.id}-${idx}`} />
                            {editable && (
                                <button type="button" onClick={() => onRemoveCustom(idx)}
                                        title="Rimuovi voce"
                                        className="text-slate-400 hover:text-rose-600 font-bold leading-none flex-shrink-0 cursor-pointer"
                                        style={{ fontSize: 11 }}
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
        <div className="flex items-center gap-1">
            <span className="font-semibold text-slate-700 uppercase whitespace-nowrap" style={{ fontSize: 9 }}>{label}:</span>
            <input type="text"
                   value={value ?? ""}
                   disabled={!editable}
                   onChange={(e) => onChange(e.target.value)}
                   className="border border-slate-400 rounded-sm px-1 py-0.5 font-mono text-right flex-1 min-w-0"
                   style={{ fontSize: 9.5 }}
                   data-testid={`piramide-sidebar-${label.toLowerCase().replace(/[^a-z0-9]+/gi, '-')}`} />
        </div>
    );
}
