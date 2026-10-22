import { useRef } from "react";
import { PenTool, Type, Trash2, Plus } from "lucide-react";

// Editor visivo: posiziona campi (firma / dato / libero) sulle pagine di un PDF.
// Le coordinate sono salvate in frazioni 0..1 della pagina (indipendenti dalla risoluzione).
// Props:
//   pages:     [{w,h}]        meta pagine (punti PDF)
//   immagini:  [dataURL]      anteprime pagine
//   campi:     [{id,tipo,chiave,valore,page,x,y,w,h}]
//   onChange:  (campi) => void
//   campiDisp: [{chiave,label}]  per i campi "dato" (libreria)
//   compact:   bool           nasconde la scelta tipo dato (solo firma) se true
export default function FirmaDesigner({ pages = [], immagini = [], campi = [], onChange, campiDisp = [], compact = false }) {
    const pageRefs = useRef({});

    const update = (next) => onChange?.(next);

    const addCampo = (tipo, page = 0) => {
        const nuovo = {
            id: `c_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`,
            tipo,
            chiave: tipo === "dato" ? (campiDisp[0]?.chiave || "nome_cliente") : null,
            valore: tipo === "libero" ? "Testo" : null,
            firmatario: "contraente",
            page,
            x: 0.35, y: 0.45, w: 0.28, h: tipo === "firma" ? 0.07 : 0.035,
            font_size: 11,
        };
        update([...campi, nuovo]);
    };

    const patch = (id, p) => update(campi.map((c) => (c.id === id ? { ...c, ...p } : c)));
    const remove = (id) => update(campi.filter((c) => c.id !== id));

    const startDrag = (e, campo, mode) => {
        e.preventDefault();
        e.stopPropagation();
        const cont = pageRefs.current[campo.page];
        if (!cont) return;
        const rect = cont.getBoundingClientRect();
        const sx = e.clientX;
        const sy = e.clientY;
        const start = { x: campo.x, y: campo.y, w: campo.w, h: campo.h };
        const move = (ev) => {
            const dfx = (ev.clientX - sx) / rect.width;
            const dfy = (ev.clientY - sy) / rect.height;
            if (mode === "move") {
                patch(campo.id, {
                    x: Math.min(Math.max(start.x + dfx, 0), 1 - start.w),
                    y: Math.min(Math.max(start.y + dfy, 0), 1 - start.h),
                });
            } else {
                patch(campo.id, {
                    w: Math.min(Math.max(start.w + dfx, 0.04), 1 - start.x),
                    h: Math.min(Math.max(start.h + dfy, 0.02), 1 - start.y),
                });
            }
        };
        const up = () => {
            window.removeEventListener("mousemove", move);
            window.removeEventListener("mouseup", up);
        };
        window.addEventListener("mousemove", move);
        window.addEventListener("mouseup", up);
    };

    if (!immagini.length) {
        return <div className="text-sm text-slate-400 italic py-6 text-center">Nessuna pagina da mostrare.</div>;
    }

    return (
        <div className="space-y-4" data-testid="firma-designer">
            <div className="flex flex-wrap gap-2">
                <button onClick={() => addCampo("firma", 0)} data-testid="fd-add-firma"
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm bg-violet-600 hover:bg-violet-700 text-white">
                    <PenTool size={14} /> Aggiungi firma
                </button>
                {!compact && (
                    <button onClick={() => addCampo("dato", 0)} data-testid="fd-add-dato"
                        className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm bg-slate-600 hover:bg-slate-700 text-white">
                        <Type size={14} /> Aggiungi campo dato
                    </button>
                )}
                <span className="text-xs text-slate-500 self-center">Trascina il riquadro nella posizione esatta; usa l'angolo per ridimensionarlo.</span>
            </div>

            <div className="space-y-6">
                {immagini.map((img, pi) => {
                    const campiPagina = campi.filter((c) => (c.page || 0) === pi);
                    return (
                        <div key={pi} className="relative inline-block w-full max-w-[720px] mx-auto border border-slate-300 rounded overflow-hidden select-none"
                            ref={(el) => { pageRefs.current[pi] = el; }}
                            data-testid={`fd-page-${pi}`}>
                            <img src={img} alt={`pagina ${pi + 1}`} className="w-full block pointer-events-none" draggable={false} />
                            {campiPagina.map((c) => (
                                <div key={c.id}
                                    onMouseDown={(e) => startDrag(e, c, "move")}
                                    className={`absolute cursor-move group ${c.tipo === "firma" ? "border-2 border-violet-600 bg-violet-200/40" : "border-2 border-amber-500 bg-amber-100/40"}`}
                                    style={{ left: `${c.x * 100}%`, top: `${c.y * 100}%`, width: `${c.w * 100}%`, height: `${c.h * 100}%` }}
                                    data-testid={`fd-box-${c.id}`}>
                                    <div className="absolute -top-5 left-0 text-[10px] font-medium px-1 rounded whitespace-nowrap bg-white/90 border border-slate-300 flex items-center gap-1">
                                        {c.tipo === "firma" ? <><PenTool size={9} className="text-violet-600" /> FIRMA</> : <><Type size={9} className="text-amber-600" /> {c.chiave || c.valore}</>}
                                    </div>
                                    <button onMouseDown={(e) => { e.stopPropagation(); e.preventDefault(); remove(c.id); }}
                                        className="absolute -top-5 -right-1 text-rose-600 bg-white/90 rounded hidden group-hover:block" data-testid={`fd-del-${c.id}`}>
                                        <Trash2 size={11} />
                                    </button>
                                    <div onMouseDown={(e) => startDrag(e, c, "resize")}
                                        className="absolute bottom-0 right-0 w-3 h-3 bg-white border-2 border-slate-600 cursor-se-resize" />
                                </div>
                            ))}
                        </div>
                    );
                })}
            </div>

            {campi.length > 0 && (
                <div className="space-y-1.5">
                    <div className="text-xs font-medium text-slate-600">Campi posizionati ({campi.length})</div>
                    {campi.map((c) => (
                        <div key={c.id} className="flex flex-wrap items-center gap-2 text-xs bg-slate-50 border border-slate-200 rounded px-2 py-1.5" data-testid={`fd-row-${c.id}`}>
                            <span className={`px-1.5 py-0.5 rounded font-medium ${c.tipo === "firma" ? "bg-violet-100 text-violet-700" : "bg-amber-100 text-amber-700"}`}>
                                {c.tipo === "firma" ? "Firma" : c.tipo === "dato" ? "Dato" : "Testo"}
                            </span>
                            <span className="text-slate-500">pag. {(c.page || 0) + 1}</span>
                            {c.tipo === "dato" && (
                                <select value={c.chiave} onChange={(e) => patch(c.id, { chiave: e.target.value })}
                                    className="border border-slate-300 rounded px-1 py-0.5 text-xs" data-testid={`fd-chiave-${c.id}`}>
                                    {campiDisp.map((k) => <option key={k.chiave} value={k.chiave}>{k.label}</option>)}
                                </select>
                            )}
                            {c.tipo === "libero" && (
                                <input value={c.valore || ""} onChange={(e) => patch(c.id, { valore: e.target.value })}
                                    className="border border-slate-300 rounded px-1 py-0.5 text-xs w-40" />
                            )}
                            <span className="text-slate-400 ml-auto">X {Math.round(c.x * 100)}% · Y {Math.round(c.y * 100)}%</span>
                            <button onClick={() => remove(c.id)} className="text-rose-500 hover:text-rose-700"><Trash2 size={12} /></button>
                        </div>
                    ))}
                </div>
            )}
        </div>
    );
}
