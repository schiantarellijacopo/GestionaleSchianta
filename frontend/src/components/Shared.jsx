export function PageHeader({ title, subtitle, actions }) {
    return (
        <div className="flex items-end justify-between mb-6 pb-4 border-b border-slate-200">
            <div>
                <h1 className="text-3xl font-semibold tracking-tight text-slate-900">{title}</h1>
                {subtitle && (
                    <p className="text-sm text-slate-500 mt-1">{subtitle}</p>
                )}
            </div>
            {actions && <div className="flex items-center gap-2">{actions}</div>}
        </div>
    );
}

export function StatusBadge({ stato }) {
    const map = {
        attiva: "badge-success", incassato: "badge-success", liquidato: "badge-success",
        sospesa: "badge-warning", in_istruttoria: "badge-warning", da_incassare: "badge-warning",
        in_coda: "badge-warning", bozza: "badge-neutral",
        annullata: "badge-danger", scaduta: "badge-danger", insoluto: "badge-danger",
        respinto: "badge-danger", errore: "badge-danger", stornato: "badge-danger",
        aperto: "badge-info", in_emissione: "badge-info", inviata: "badge-info",
        chiuso_senza_seguito: "badge-neutral",
    };
    const cls = map[stato] || "badge-neutral";
    return <span className={`badge ${cls}`}>{(stato || "").replaceAll("_", " ")}</span>;
}

export function Empty({ message = "Nessun risultato" }) {
    return (
        <div className="text-center py-12 text-slate-500 text-sm" data-testid="empty-state">
            {message}
        </div>
    );
}

export function Loading() {
    return <div className="text-center py-10 text-slate-400 text-sm">Caricamento...</div>;
}
