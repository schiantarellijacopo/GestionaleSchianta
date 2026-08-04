/**
 * Selettore UNIFICATO "Conto / Banca" — l'unico dropdown pagamenti usato in:
 *  - DialogIncassoCopertura
 *  - DialogIncasso
 *  - TitoloDialog
 *  - Movimenti Prima Nota
 *  - Estratto Conto Compagnie / Collaboratori
 *  - Giroconti
 *
 * Elenca i conti_cassa attivi (Librerie → Conti / Banche). Il valore
 * inviato/salvato è il NOME del conto (es. "BPER Sondrio") per
 * compatibilità col campo legacy `mezzo_pagamento` (string); il backend
 * risolve il conto_cassa_id dal nome.
 */
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import useTipiPagamento from "@/hooks/useTipiPagamento";

export default function SelectTipoPagamento({
    value, onChange, placeholder = "Seleziona conto / banca",
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
                        Nessun conto configurato. Vai in Librerie → Conti / Banche.
                    </div>
                )}
            </SelectContent>
        </Select>
    );
}
