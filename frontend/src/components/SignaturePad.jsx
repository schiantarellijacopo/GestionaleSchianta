/**
 * SignaturePad — canvas leggero per firma touch/mouse (no dipendenze extra).
 *
 * Props:
 *  - onChange(b64): callback con la firma in formato data-URL PNG (o null)
 *  - height, width: dimensioni del canvas (default 320x110)
 *  - label: etichetta sopra il canvas
 *  - testid: prefisso data-testid (es "sig-operatore")
 */
import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Eraser } from "lucide-react";

export default function SignaturePad({
    onChange, height = 110, width = 320, label = "Firma",
    testid = "signature-pad", initial = null,
}) {
    const canvasRef = useRef(null);
    const drawing = useRef(false);
    const last = useRef({ x: 0, y: 0 });
    const [empty, setEmpty] = useState(!initial);

    // Setup canvas + load initial signature (se passata)
    useEffect(() => {
        const c = canvasRef.current;
        if (!c) return;
        const ratio = window.devicePixelRatio || 1;
        c.width = width * ratio;
        c.height = height * ratio;
        c.style.width = `${width}px`;
        c.style.height = `${height}px`;
        const ctx = c.getContext("2d");
        ctx.scale(ratio, ratio);
        ctx.lineWidth = 2;
        ctx.lineCap = "round";
        ctx.lineJoin = "round";
        ctx.strokeStyle = "#0f172a";
        ctx.fillStyle = "#ffffff";
        ctx.fillRect(0, 0, width, height);
        if (initial) {
            const img = new Image();
            img.onload = () => ctx.drawImage(img, 0, 0, width, height);
            img.src = initial;
        }
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    const getPos = (e) => {
        const c = canvasRef.current;
        const rect = c.getBoundingClientRect();
        const t = e.touches ? e.touches[0] : e;
        return { x: t.clientX - rect.left, y: t.clientY - rect.top };
    };

    const start = (e) => {
        e.preventDefault();
        drawing.current = true;
        last.current = getPos(e);
    };
    const move = (e) => {
        if (!drawing.current) return;
        e.preventDefault();
        const ctx = canvasRef.current.getContext("2d");
        const p = getPos(e);
        ctx.beginPath();
        ctx.moveTo(last.current.x, last.current.y);
        ctx.lineTo(p.x, p.y);
        ctx.stroke();
        last.current = p;
        if (empty) setEmpty(false);
    };
    const stop = () => {
        if (!drawing.current) return;
        drawing.current = false;
        const c = canvasRef.current;
        const b64 = c.toDataURL("image/png");
        onChange?.(b64);
    };

    const clear = () => {
        const c = canvasRef.current;
        const ctx = c.getContext("2d");
        ctx.fillStyle = "#ffffff";
        ctx.fillRect(0, 0, width, height);
        setEmpty(true);
        onChange?.(null);
    };

    return (
        <div className="flex flex-col gap-2" data-testid={testid}>
            <div className="flex items-center justify-between">
                <span className="text-xs font-medium text-slate-700">{label}</span>
                <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    onClick={clear}
                    className="h-7 text-xs text-slate-500 hover:text-rose-600"
                    data-testid={`${testid}-clear`}
                >
                    <Eraser size={12} className="mr-1" /> Pulisci
                </Button>
            </div>
            <div className="border border-slate-300 rounded-md bg-white shadow-inner touch-none">
                <canvas
                    ref={canvasRef}
                    style={{ touchAction: "none", display: "block" }}
                    onMouseDown={start}
                    onMouseMove={move}
                    onMouseUp={stop}
                    onMouseLeave={stop}
                    onTouchStart={start}
                    onTouchMove={move}
                    onTouchEnd={stop}
                    data-testid={`${testid}-canvas`}
                />
            </div>
            {empty && (
                <div className="text-[10px] text-slate-400 italic">Firma qui sopra (tocca/clicca e trascina)</div>
            )}
        </div>
    );
}
