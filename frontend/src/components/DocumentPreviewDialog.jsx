/**
 * DocumentPreviewDialog — visualizzatore documenti in-CRM (PDF/immagini)
 * con zoom e rotazione. Riutilizzabile per anagrafiche, polizze, sinistri, ecc.
 * fileUrl deve essere un URL assoluto già comprensivo di token (serve inline).
 */
import { useState, useEffect } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Eye, Download, ZoomIn, ZoomOut, RotateCw, RotateCcw, Maximize } from "lucide-react";

export default function DocumentPreviewDialog({ open, onOpenChange, fileUrl, nome_file, isImage = false, onDownload }) {
    const [scale, setScale] = useState(1);
    const [rotate, setRotate] = useState(0);

    useEffect(() => { if (open) { setScale(1); setRotate(0); } }, [open, fileUrl]);

    const btn = "p-1.5 rounded border border-slate-300 text-slate-600 hover:bg-slate-100 inline-flex items-center justify-center disabled:opacity-40";
    const swap = rotate % 180 !== 0;
    const transform = `scale(${scale}) rotate(${rotate}deg)`;

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="max-w-5xl w-[96vw]" data-testid="doc-preview-dialog">
                <DialogHeader>
                    <DialogTitle className="flex items-center gap-2 text-base pr-8">
                        <Eye size={16} className="text-sky-600 shrink-0" />
                        <span className="truncate">{nome_file}</span>
                    </DialogTitle>
                </DialogHeader>

                <div className="flex items-center gap-1.5 flex-wrap">
                    <button className={btn} onClick={() => setScale((s) => Math.max(0.3, +(s - 0.2).toFixed(2)))}
                        data-testid="doc-zoom-out" title="Riduci"><ZoomOut size={15} /></button>
                    <span className="text-xs tabular-nums w-12 text-center font-mono">{Math.round(scale * 100)}%</span>
                    <button className={btn} onClick={() => setScale((s) => Math.min(4, +(s + 0.2).toFixed(2)))}
                        data-testid="doc-zoom-in" title="Ingrandisci"><ZoomIn size={15} /></button>
                    <span className="w-px h-5 bg-slate-200 mx-1" />
                    <button className={btn} onClick={() => setRotate((r) => (r - 90 + 360) % 360)}
                        data-testid="doc-rotate-left" title="Ruota a sinistra"><RotateCcw size={15} /></button>
                    <button className={btn} onClick={() => setRotate((r) => (r + 90) % 360)}
                        data-testid="doc-rotate-right" title="Ruota a destra"><RotateCw size={15} /></button>
                    <button className={btn} onClick={() => { setScale(1); setRotate(0); }}
                        data-testid="doc-reset" title="Reimposta"><Maximize size={15} /></button>
                    {onDownload && (
                        <button onClick={onDownload} data-testid="doc-preview-download"
                            className="ml-auto text-xs px-3 py-1.5 rounded bg-sky-700 text-white hover:bg-sky-800 inline-flex items-center gap-1">
                            <Download size={13} /> Scarica
                        </button>
                    )}
                </div>

                <div className="h-[72vh] bg-slate-100 rounded overflow-auto flex items-center justify-center p-2">
                    {!fileUrl ? null : isImage ? (
                        <img src={fileUrl} alt={nome_file} data-testid="doc-preview-image"
                            style={{ transform, transition: "transform 0.15s ease" }}
                            className="max-w-full max-h-full object-contain select-none" />
                    ) : (
                        <div className="flex items-center justify-center"
                            style={{ transform, transition: "transform 0.15s ease",
                                width: swap ? "70vh" : "100%", height: swap ? "90%" : "100%" }}>
                            <iframe title="anteprima-documento" src={fileUrl} data-testid="doc-preview-frame"
                                className="border-0 bg-white"
                                style={{ width: "100%", height: "100%", minHeight: "68vh" }} />
                        </div>
                    )}
                </div>
            </DialogContent>
        </Dialog>
    );
}
