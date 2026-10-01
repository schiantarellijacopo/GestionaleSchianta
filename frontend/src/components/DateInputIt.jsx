import { useState, useEffect } from "react";
import { Input } from "@/components/ui/input";

// Campo data in formato italiano GG/MM/AAAA, indipendente dalla lingua del browser.
// value / onChange lavorano sempre in ISO (YYYY-MM-DD), come i campi <input type="date">.
const isoToIt = (iso) => {
    if (!iso) return "";
    const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
    return m ? `${m[3]}/${m[2]}/${m[1]}` : "";
};
const itToIso = (s) => {
    const m = /^(\d{1,2})\/(\d{1,2})\/(\d{4})$/.exec((s || "").trim());
    if (!m) return null;
    const d = m[1].padStart(2, "0");
    const mo = m[2].padStart(2, "0");
    const y = m[3];
    const dt = new Date(`${y}-${mo}-${d}T00:00:00`);
    if (isNaN(dt.getTime())) return null;
    return `${y}-${mo}-${d}`;
};

export default function DateInputIt({ value, onChange, className = "", ...props }) {
    const [txt, setTxt] = useState(isoToIt(value));
    useEffect(() => { setTxt(isoToIt(value)); }, [value]);

    const handle = (e) => {
        const digits = e.target.value.replace(/\D/g, "").slice(0, 8);
        let out = digits;
        if (digits.length > 4) out = `${digits.slice(0, 2)}/${digits.slice(2, 4)}/${digits.slice(4)}`;
        else if (digits.length > 2) out = `${digits.slice(0, 2)}/${digits.slice(2)}`;
        setTxt(out);
        if (out === "") { onChange(""); return; }
        const iso = itToIso(out);
        if (iso) onChange(iso);
    };

    return (
        <Input
            value={txt}
            onChange={handle}
            placeholder="gg/mm/aaaa"
            inputMode="numeric"
            maxLength={10}
            className={className}
            {...props}
        />
    );
}
