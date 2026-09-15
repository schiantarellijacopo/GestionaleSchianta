import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from "@/components/ui/select";

export const MESI = ["Gen", "Feb", "Mar", "Apr", "Mag", "Giu", "Lug", "Ago", "Set", "Ott", "Nov", "Dic"];
export const CUR = new Date().getFullYear();
export const ALL_COLS = [
    { key: "netto", label: "Premio Netto", cls: "text-sky-700", bar: "#0284c7" },
    { key: "provvigioni", label: "Provvigioni", cls: "text-emerald-700", bar: "#059669" },
    { key: "lordo", label: "Premio Lordo", cls: "text-fuchsia-700", bar: "#c026d3" },
];
export const YEAR_BARS = ["#7c3aed", "#0891b2", "#d97706", "#db2777", "#16a34a"];

export function FSel({ label, value, onChange, opts, tid, w = "w-40" }) {
    return (
        <div>
            <div className="text-[10px] uppercase text-slate-500 mb-1">{label}</div>
            <Select value={value} onValueChange={onChange}>
                <SelectTrigger className={`h-8 ${w} text-xs`} data-testid={tid}><SelectValue /></SelectTrigger>
                <SelectContent>
                    {opts.map(([v, l]) => <SelectItem key={v} value={v}>{l}</SelectItem>)}
                </SelectContent>
            </Select>
        </div>
    );
}

export function MeseRange({ meseDa, setMeseDa, meseA, setMeseA }) {
    return (
        <div>
            <div className="text-[10px] uppercase text-slate-500 mb-1">Periodo (mesi)</div>
            <div className="flex items-center gap-1">
                <Select value={String(meseDa)} onValueChange={(v) => { const n = parseInt(v); setMeseDa(n); if (n > meseA) setMeseA(n); }}>
                    <SelectTrigger className="h-8 w-24 text-xs" data-testid="stat-mese-da"><SelectValue /></SelectTrigger>
                    <SelectContent>{MESI.map((m, i) => <SelectItem key={m} value={String(i + 1)}>{m}</SelectItem>)}</SelectContent>
                </Select>
                <span className="text-xs text-slate-400">→</span>
                <Select value={String(meseA)} onValueChange={(v) => { const n = parseInt(v); setMeseA(n); if (n < meseDa) setMeseDa(n); }}>
                    <SelectTrigger className="h-8 w-24 text-xs" data-testid="stat-mese-a"><SelectValue /></SelectTrigger>
                    <SelectContent>{MESI.map((m, i) => <SelectItem key={m} value={String(i + 1)}>{m}</SelectItem>)}</SelectContent>
                </Select>
            </div>
        </div>
    );
}

export function YearPicker({ sel, setSel }) {
    const quick = [0, 1, 2, 3, 4].map((d) => CUR - d);
    const options = [];
    for (let y = CUR + 1; y >= 2005; y--) options.push(y);
    const toggle = (y) => setSel((s) => s.includes(y) ? s.filter((x) => x !== y) : [...s, y].sort((a, b) => b - a));
    const extra = sel.filter((y) => !quick.includes(y)).sort((a, b) => b - a);
    return (
        <div>
            <div className="text-[10px] uppercase text-slate-500 mb-1">Anni</div>
            <div className="flex items-center gap-1 flex-wrap">
                {quick.map((y) => (
                    <button key={y} onClick={() => toggle(y)} data-testid={`stat-anno-${y}`}
                        className={`text-xs px-2 py-1 rounded border ${sel.includes(y) ? "bg-fuchsia-700 text-white border-fuchsia-700" : "bg-white border-slate-200"}`}>{y}</button>
                ))}
                {extra.map((y) => (
                    <button key={y} onClick={() => toggle(y)} data-testid={`stat-anno-${y}`}
                        className="text-xs px-2 py-1 rounded border bg-fuchsia-700 text-white border-fuchsia-700 flex items-center gap-1">
                        {y} <span className="opacity-70">✕</span>
                    </button>
                ))}
                <Select key={sel.join(",")} value="" onValueChange={(v) => toggle(parseInt(v))}>
                    <SelectTrigger className="h-8 w-28 text-xs" data-testid="stat-add-anno"><SelectValue placeholder="+ Anno" /></SelectTrigger>
                    <SelectContent className="max-h-64">
                        {options.filter((y) => !sel.includes(y)).map((y) => <SelectItem key={y} value={String(y)}>{y}</SelectItem>)}
                    </SelectContent>
                </Select>
            </div>
        </div>
    );
}
