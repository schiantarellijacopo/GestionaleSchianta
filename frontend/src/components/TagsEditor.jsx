import { useEffect, useRef, useState } from "react";
import { X, Plus } from "lucide-react";
import { api } from "@/lib/api";

/**
 * Tag editor con autocomplete basato sui tag esistenti in /api/anagrafiche/tags.
 * Premere Invio o virgola per aggiungere. Click sulla X per rimuovere.
 *
 * Props:
 *  - value: string[] (tag correnti)
 *  - onChange(tags: string[])
 *  - testid (opzionale, default "tags-editor")
 *  - placeholder
 */
export default function TagsEditor({ value = [], onChange, testid = "tags-editor", placeholder = "Aggiungi tag..." }) {
    const [text, setText] = useState("");
    const [suggestions, setSuggestions] = useState([]);
    const [showSugg, setShowSugg] = useState(false);
    const inputRef = useRef(null);

    useEffect(() => {
        // carica tag esistenti per autocomplete
        api.get("/anagrafiche/tags").then((r) => setSuggestions(r.data || [])).catch(() => setSuggestions([]));
    }, []);

    const tags = Array.isArray(value) ? value : [];

    const add = (raw) => {
        const t = (raw || "").trim().toLowerCase().replace(/\s+/g, "_");
        if (!t) return;
        if (tags.includes(t)) return;
        onChange([...tags, t]);
        setText("");
    };

    const remove = (t) => onChange(tags.filter((x) => x !== t));

    const onKey = (e) => {
        if (e.key === "Enter" || e.key === ",") {
            e.preventDefault();
            add(text);
        } else if (e.key === "Backspace" && !text && tags.length) {
            // backspace su input vuoto rimuove ultimo
            remove(tags[tags.length - 1]);
        }
    };

    const filteredSugg = suggestions.filter(
        (s) => s.toLowerCase().includes(text.toLowerCase()) && !tags.includes(s)
    ).slice(0, 10);

    return (
        <div className="mt-1" data-testid={testid}>
            <div className="flex flex-wrap items-center gap-1.5 p-2 rounded-md border border-slate-300 bg-white min-h-[40px]">
                {tags.map((t) => (
                    <span
                        key={t}
                        className="inline-flex items-center gap-1 text-[10px] uppercase tracking-wide px-2 py-0.5 rounded-full bg-sky-100 text-sky-700 border border-sky-200"
                        data-testid={`tag-chip-${t}`}
                    >
                        {t}
                        <button
                            type="button"
                            onClick={() => remove(t)}
                            className="hover:bg-sky-200 rounded-full p-0.5"
                            aria-label={`Rimuovi ${t}`}
                        >
                            <X size={10} />
                        </button>
                    </span>
                ))}
                <input
                    ref={inputRef}
                    className="flex-1 min-w-[120px] text-sm border-0 focus:ring-0 focus:outline-none bg-transparent"
                    value={text}
                    onChange={(e) => { setText(e.target.value); setShowSugg(true); }}
                    onKeyDown={onKey}
                    onFocus={() => setShowSugg(true)}
                    onBlur={() => setTimeout(() => setShowSugg(false), 200)}
                    placeholder={placeholder}
                    data-testid={`${testid}-input`}
                />
                {text && (
                    <button
                        type="button"
                        onClick={() => add(text)}
                        className="text-xs px-2 py-1 rounded bg-sky-600 text-white hover:bg-sky-700"
                        data-testid={`${testid}-add`}
                    >
                        <Plus size={12} className="inline mr-0.5" />Aggiungi
                    </button>
                )}
            </div>
            {showSugg && text && filteredSugg.length > 0 && (
                <div className="mt-1 flex flex-wrap gap-1" data-testid={`${testid}-suggestions`}>
                    <span className="text-[10px] text-slate-500 mr-1">Esistenti:</span>
                    {filteredSugg.map((s) => (
                        <button
                            key={s}
                            type="button"
                            onClick={() => add(s)}
                            className="text-[10px] uppercase tracking-wide px-2 py-0.5 rounded-full bg-slate-100 text-slate-600 border border-slate-200 hover:bg-sky-100 hover:text-sky-700"
                        >
                            {s}
                        </button>
                    ))}
                </div>
            )}
            <div className="mt-1 text-[10px] text-slate-400">
                Premi Invio o virgola per aggiungere · backspace per rimuovere l&apos;ultimo
            </div>
        </div>
    );
}
