import { useEffect, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "@/lib/api";
import { PageHeader, Loading, Empty } from "@/components/Shared";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Card } from "@/components/ui/card";
import { toast } from "sonner";
import { GripVertical, Lock } from "lucide-react";

const ENTITA = [
    { key: "polizze", label: "Polizze", editable: true },
    { key: "sinistri", label: "Sinistri", editable: true },
    { key: "titoli", label: "Titoli", editable: true },
    { key: "clienti", label: "Clienti", editable: false },  // stato calcolato, non modificabile
];

const COL_COLORS = {
    in_emissione: "#0EA5E9", attiva: "#10B981", sospesa: "#F59E0B",
    scaduta: "#EF4444", annullata: "#94A3B8",
    aperto: "#0EA5E9", in_istruttoria: "#F59E0B", liquidato: "#10B981",
    chiuso_senza_seguito: "#94A3B8", respinto: "#EF4444",
    da_incassare: "#F59E0B", insoluto: "#EF4444", incassato: "#10B981", stornato: "#94A3B8",
    prospect: "#94A3B8", nuovo: "#0EA5E9", attivo: "#10B981", top: "#7C3AED",
};

export default function Pipeline() {
    return (
        <div data-testid="pipeline-page">
            <PageHeader
                title="Pipeline"
                subtitle="Vista a colonne (kanban). Trascina le card tra colonne per cambiare stato."
            />
            <Tabs defaultValue="polizze">
                <TabsList className="bg-slate-100">
                    {ENTITA.map((e) => (
                        <TabsTrigger key={e.key} value={e.key} data-testid={`pipeline-tab-${e.key}`}>
                            {e.label}
                            {!e.editable && <Lock size={10} className="ml-1 text-slate-400" />}
                        </TabsTrigger>
                    ))}
                </TabsList>
                {ENTITA.map((e) => (
                    <TabsContent key={e.key} value={e.key} className="mt-4">
                        <PipelineBoard entita={e.key} editable={e.editable} />
                    </TabsContent>
                ))}
            </Tabs>
        </div>
    );
}

function PipelineBoard({ entita, editable }) {
    const [data, setData] = useState(null);
    const [draggedCard, setDraggedCard] = useState(null);  // { id, fromCol }
    const [dragOverCol, setDragOverCol] = useState(null);
    const nav = useNavigate();

    const load = useCallback(() => {
        setData(null);
        api.get(`/pipeline/${entita}`).then((r) => setData(r.data));
    }, [entita]);

    useEffect(() => { load(); }, [load]);

    const onDragStart = (card, fromCol, ev) => {
        if (!editable) return;
        setDraggedCard({ id: card.id, fromCol, title: card.title });
        ev.dataTransfer.effectAllowed = "move";
        ev.dataTransfer.setData("text/plain", card.id);
    };

    const onDragOver = (colKey, ev) => {
        if (!editable || !draggedCard || draggedCard.fromCol === colKey) return;
        ev.preventDefault();
        ev.dataTransfer.dropEffect = "move";
        setDragOverCol(colKey);
    };

    const onDragLeave = () => setDragOverCol(null);

    const onDrop = async (toCol, ev) => {
        ev.preventDefault();
        setDragOverCol(null);
        if (!editable || !draggedCard || draggedCard.fromCol === toCol) {
            setDraggedCard(null);
            return;
        }
        // Optimistic UI: sposta la card subito
        setData((prev) => {
            if (!prev) return prev;
            const colonne = prev.colonne.map((c) => {
                if (c.key === draggedCard.fromCol) {
                    const idx = c.cards.findIndex((x) => x.id === draggedCard.id);
                    if (idx < 0) return c;
                    const moved = c.cards[idx];
                    return { ...c, cards: c.cards.filter((x) => x.id !== draggedCard.id), count: c.count - 1, _moved: moved };
                }
                return c;
            });
            const movedCard = colonne.find((c) => c._moved)?._moved;
            const out = colonne.map((c) => {
                const { _moved, ...rest } = c;
                if (c.key === toCol && movedCard) {
                    return { ...rest, cards: [movedCard, ...rest.cards], count: rest.count + 1 };
                }
                return rest;
            });
            return { ...prev, colonne: out };
        });
        try {
            await api.post(`/pipeline/${entita}/${draggedCard.id}/move`, { nuovo_stato: toCol });
            toast.success(`Spostato in "${toCol.replace(/_/g, " ")}"`);
        } catch (e) {
            toast.error(e.response?.data?.detail || "Errore spostamento");
            load();  // ricarica per ripristinare lo stato corretto
        }
        setDraggedCard(null);
    };

    if (!data) return <Loading />;

    return (
        <div className="flex gap-4 overflow-x-auto pb-4" data-testid={`board-${entita}`}>
            {data.colonne.map((col) => {
                const isDropTarget = dragOverCol === col.key && draggedCard && draggedCard.fromCol !== col.key;
                return (
                    <div
                        key={col.key}
                        className="w-72 shrink-0"
                        onDragOver={(e) => onDragOver(col.key, e)}
                        onDragLeave={onDragLeave}
                        onDrop={(e) => onDrop(col.key, e)}
                    >
                        <div
                            className="rounded-md px-3 py-2 mb-3 flex items-center justify-between"
                            style={{
                                background: `${COL_COLORS[col.key] || "#64748B"}15`,
                                borderLeft: `3px solid ${COL_COLORS[col.key] || "#64748B"}`,
                            }}
                        >
                            <div className="font-medium text-sm text-slate-800">{col.label}</div>
                            <div className="text-xs font-semibold text-slate-600 num bg-white border border-slate-200 rounded-full px-2 py-0.5">
                                {col.count}
                            </div>
                        </div>
                        <div className={`space-y-2 min-h-[60px] rounded-md p-1 transition-colors ${
                            isDropTarget ? "bg-sky-100 ring-2 ring-sky-400 ring-dashed" : ""
                        }`}>
                            {col.cards.length === 0 ? (
                                <div className="text-xs text-slate-400 text-center py-4">
                                    {isDropTarget ? "Rilascia qui" : "Vuoto"}
                                </div>
                            ) : col.cards.map((c) => (
                                <Card
                                    key={c.id}
                                    draggable={editable}
                                    onDragStart={(e) => onDragStart(c, col.key, e)}
                                    onClick={() => c.link && nav(c.link)}
                                    className={`p-3 hover:border-sky-400 hover:shadow-md transition-all border-slate-200 ${
                                        editable ? "cursor-grab active:cursor-grabbing" : "cursor-pointer"
                                    } ${draggedCard?.id === c.id ? "opacity-40" : ""}`}
                                    data-testid={`card-${c.id}`}
                                >
                                    <div className="flex items-start gap-1.5">
                                        {editable && <GripVertical size={12} className="text-slate-300 mt-0.5 shrink-0" />}
                                        <div className="flex-1 min-w-0">
                                            <div className="font-medium text-sm text-slate-900 truncate">{c.title}</div>
                                            {c.subtitle && <div className="text-xs text-slate-600 truncate mt-0.5">{c.subtitle}</div>}
                                            {c.footer && <div className="text-xs text-slate-500 truncate mt-1">{c.footer}</div>}
                                            <div className="flex items-center justify-between mt-2 pt-2 border-t border-slate-100">
                                                {c.extra && <span className="text-[11px] text-slate-600 num">{c.extra}</span>}
                                                {c.date && <span className="text-[10px] text-slate-400 num">{c.date}</span>}
                                            </div>
                                        </div>
                                    </div>
                                </Card>
                            ))}
                            {col.cards.length === 50 && col.count > 50 && (
                                <div className="text-[10px] text-center text-slate-400">+ {col.count - 50} altri...</div>
                            )}
                        </div>
                    </div>
                );
            })}
            {data.colonne.length === 0 && <Empty />}

            {!editable && (
                <div className="text-xs text-slate-500 fixed bottom-4 right-4 bg-amber-50 border border-amber-200 px-3 py-2 rounded-md shadow">
                    <Lock size={11} className="inline mr-1" /> Lo stato dei clienti è calcolato automaticamente dal numero di polizze.
                </div>
            )}
        </div>
    );
}
