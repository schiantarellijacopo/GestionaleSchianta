import { useState } from "react";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Input } from "@/components/ui/input";

const EMOJI_SET = [
    "📄", "📜", "📕", "📘", "📗", "📙", "📚", "🗂️", "📁", "📂", "🗃️", "🗄️",
    "📋", "📝", "🗒️", "🧾", "📑", "🖊️", "✍️", "✒️", "🖋️", "➕", "🖼️", "📸",
    "📎", "📌", "🔖", "🏷️", "🪪", "🆔", "🚗", "🚙", "🏍️", "🚚", "🛵", "⛵",
    "🏠", "🏢", "🏦", "🏛️", "❤️", "🩺", "💊", "👪", "👤", "🔎", "🔍", "🧮",
    "📊", "📈", "📉", "💰", "💶", "💳", "🧰", "⚖️", "🛡️", "⚠️", "🚨", "🔥",
    "💧", "🌊", "🌪️", "⭐", "✅", "❗", "📥", "📤", "📦", "🔑", "🗝️", "📅",
];

export default function EmojiPicker({ value, onChange, size = "md" }) {
    const [open, setOpen] = useState(false);
    const [custom, setCustom] = useState("");
    const btnSize = size === "sm" ? "h-7 w-7 text-base" : "h-8 w-8 text-lg";
    return (
        <Popover open={open} onOpenChange={setOpen}>
            <PopoverTrigger asChild>
                <button type="button"
                    className={`shrink-0 flex items-center justify-center rounded-md border border-slate-200 bg-white hover:bg-slate-50 ${btnSize}`}
                    title="Scegli icona" data-testid="emoji-picker-trigger">
                    <span className="leading-none">{value || "📄"}</span>
                </button>
            </PopoverTrigger>
            <PopoverContent className="w-64 p-2" align="start" data-testid="emoji-picker-content">
                <div className="grid grid-cols-8 gap-1 max-h-48 overflow-auto">
                    {EMOJI_SET.map((e) => (
                        <button key={e} type="button"
                            onClick={() => { onChange(e); setOpen(false); }}
                            className={`h-7 w-7 flex items-center justify-center rounded hover:bg-sky-100 text-base ${value === e ? "bg-sky-100 ring-1 ring-sky-400" : ""}`}
                            data-testid={`emoji-opt-${e}`}>
                            {e}
                        </button>
                    ))}
                </div>
                <div className="mt-2 pt-2 border-t border-slate-100 flex items-center gap-1.5">
                    <Input value={custom} onChange={(ev) => setCustom(ev.target.value.slice(0, 4))}
                        placeholder="Carattere libero…" className="h-7 text-sm"
                        onKeyDown={(ev) => { if (ev.key === "Enter" && custom.trim()) { onChange(custom.trim()); setCustom(""); setOpen(false); } }}
                        data-testid="emoji-custom-input" />
                    <button type="button" disabled={!custom.trim()}
                        onClick={() => { onChange(custom.trim()); setCustom(""); setOpen(false); }}
                        className="h-7 px-2 text-xs rounded bg-sky-700 text-white disabled:opacity-40"
                        data-testid="emoji-custom-ok">OK</button>
                </div>
            </PopoverContent>
        </Popover>
    );
}
