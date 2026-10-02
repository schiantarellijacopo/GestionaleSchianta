import { Input } from "@/components/ui/input";
import { Search, X } from "lucide-react";
import DateInputIt from "@/components/DateInputIt";

// Filtra una lista per testo libero (compagnia / descrizione / tipo / importo)
// e per intervallo di date sul campo `data` (ISO YYYY-MM-DD).
export function applyRicercaData(items, { q, dal, al } = {}) {
    let list = items || [];
    const term = (q || "").trim().toLowerCase();
    if (term) {
        const numTerm = term.replace(/\./g, "").replace(",", ".");
        const asNum = parseFloat(numTerm);
        const isNum = /^[0-9.,]+$/.test(term) && !isNaN(asNum);
        list = list.filter((r) => {
            const hay = `${r.compagnia_nome || ""} ${r.compagnia_codice || ""} ${r.descrizione || ""} ${r.note || ""} ${r.collaboratore_nome || ""} ${r.tipo || ""} ${r.anno || ""}`.toLowerCase();
            if (hay.includes(term)) return true;
            const imp = r.importo;
            if (imp != null) {
                const impIt = Math.abs(Number(imp)).toFixed(2).replace(".", ",");
                if (String(Math.abs(imp)).includes(term) || impIt.includes(term)) return true;
                if (isNum && Math.abs(Math.abs(Number(imp)) - asNum) < 0.005) return true;
            }
            return false;
        });
    }
    if (dal) list = list.filter((r) => (r.data || "") >= dal);
    if (al) list = list.filter((r) => (r.data || "") <= al);
    return list;
}

export default function RicercaDateBar({ q, setQ, dal, setDal, al, setAl, placeholder = "Cerca descrizione, compagnia, importo...", testid = "ricerca" }) {
    return (
        <div className="flex flex-wrap items-end gap-3">
            <div className="flex-1 min-w-[220px]">
                <label className="text-[11px] text-slate-500 block mb-1">Cerca</label>
                <div className="relative">
                    <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-400" />
                    <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder={placeholder}
                        className="pl-8 pr-8 h-9" data-testid={`${testid}-search`} />
                    {q && (
                        <button onClick={() => setQ("")} className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600"
                            data-testid={`${testid}-clear`}><X size={14} /></button>
                    )}
                </div>
            </div>
            <div>
                <label className="text-[11px] text-slate-500 block mb-1">Dal</label>
                <DateInputIt value={dal} onChange={setDal} className="h-9 w-32" placeholder="GG/MM/AAAA" data-testid={`${testid}-dal`} />
            </div>
            <div>
                <label className="text-[11px] text-slate-500 block mb-1">Al</label>
                <DateInputIt value={al} onChange={setAl} className="h-9 w-32" placeholder="GG/MM/AAAA" data-testid={`${testid}-al`} />
            </div>
            {(dal || al) && (
                <button onClick={() => { setDal(""); setAl(""); }}
                    className="h-9 px-2 text-xs text-slate-500 hover:text-slate-700 self-end" data-testid={`${testid}-date-clear`}>
                    Azzera date
                </button>
            )}
        </div>
    );
}
