/**
 * OcrProgressBar — barra di avanzamento per le elaborazioni OCR.
 *
 * L'OCR non espone un avanzamento reale (è una singola chiamata), quindi la
 * barra simula un progresso fluido mentre `active` è true e scatta al 100%
 * quando l'elaborazione termina, così l'utente sa che è in lavorazione.
 *
 * Props:
 *   - active: boolean → true mentre l'OCR è in corso
 *   - label: string   → testo mostrato sopra la barra
 */
import { useEffect, useState } from "react";
import { Progress } from "@/components/ui/progress";
import { Sparkles } from "lucide-react";

export default function OcrProgressBar({ active, label = "Analisi OCR in corso…" }) {
    const [value, setValue] = useState(0);
    const [visible, setVisible] = useState(false);

    useEffect(() => {
        let interval;
        let hideTimer;
        if (active) {
            setVisible(true);
            setValue(8);
            interval = setInterval(() => {
                setValue((v) => {
                    if (v >= 92) return v;             // resta sotto il 100% finché non finisce
                    const step = v < 50 ? 7 : v < 75 ? 3 : 1; // rallenta avvicinandosi al top
                    return Math.min(92, v + step);
                });
            }, 500);
        } else if (visible) {
            setValue(100);                             // completamento visibile
            hideTimer = setTimeout(() => { setVisible(false); setValue(0); }, 600);
        }
        return () => { clearInterval(interval); clearTimeout(hideTimer); };
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [active]);

    if (!visible) return null;

    return (
        <div className="w-full space-y-1" data-testid="ocr-progress-bar">
            <div className="flex items-center justify-between text-[11px] font-medium text-violet-700">
                <span className="flex items-center gap-1">
                    <Sparkles size={12} className="animate-pulse" /> {label}
                </span>
                <span data-testid="ocr-progress-value">{value}%</span>
            </div>
            <Progress value={value} className="h-2 bg-violet-100 [&>div]:bg-violet-600 [&>div]:transition-transform [&>div]:duration-500" />
        </div>
    );
}
