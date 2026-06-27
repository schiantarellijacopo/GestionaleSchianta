/**
 * Selettore UNIFICATO "Tipo Pagamento" — l'unico dropdown usato in:
 *  - DialogIncassoCopertura
 *  - DialogIncasso
 *  - TitoloDialog
 *  - Movimenti Prima Nota
 *  - Estratto Conto Compagnie / Collaboratori
 *  - Giroconti
 *
 * Il valore inviato/salvato è il `label` del TipoPagamento (es.
 * "BONIFICO BPER SONDRIO") per compatibilità col campo legacy
 * `mezzo_pagamento` (string).
 */
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import useTipiPagamento from "@/hooks/useTipiPagamento";

export default function SelectTipoPagamento({
    value, onChange, placeholder = "Seleziona tipo pagamento",
    allowAll = false, allLabel = "Tutti", testid = "tipo-pagamento",
    className,
}) {
    const { tipi } = useTipiPagamento();
    return (
        <Select value={value || ""} onValueChange={onChange}>
            <SelectTrigger className={className} data-testid={testid}>
                <SelectValue placeholder={placeholder} />
            </SelectTrigger>
            <SelectContent>
                {allowAll && <SelectItem value="all">{allLabel}</SelectItem>}
                {tipi.map((t) => (
                    <SelectItem key={t.id} value={t.label}>{t.label}</SelectItem>
                ))}
                {tipi.length === 0 && (
                    <div className="text-xs text-slate-400 px-2 py-2">
                        Nessun tipo pagamento configurato. Vai in Librerie → Tipi pagamento.
                    </div>
                )}
            </SelectContent>
        </Select>
    );
}
