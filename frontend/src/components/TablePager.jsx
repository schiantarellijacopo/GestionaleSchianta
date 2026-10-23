/**
 * useTablePager + <TablePager/>
 *
 * Paginazione client-side riusabile per QUALSIASI tabella del programma.
 * Set righe per pagina: 25 · 50 · 100 · 200 · Tutte.
 *
 *   const { paged, page, setPage, pageSize, setPageSize, pages, total } = useTablePager(sortedRows, 50);
 *   ...render paged...
 *   <TablePager page={page} setPage={setPage} pageSize={pageSize} setPageSize={setPageSize} pages={pages} total={total} />
 */
import { useEffect, useMemo, useState } from "react";
import { Button } from "@/components/ui/button";

export const PAGE_SIZE_OPTIONS = [25, 50, 100, 200, "all"];

export function useTablePager(items, defaultSize = 50) {
    const [pageSize, setPageSize] = useState(defaultSize);
    const [page, setPage] = useState(1);
    const total = Array.isArray(items) ? items.length : 0;
    const isAll = pageSize === "all";
    const pages = isAll ? 1 : Math.max(1, Math.ceil(total / (pageSize || 1)));

    // Se cambia il filtro/l'ordinamento e la pagina corrente non esiste più, torna alla 1
    useEffect(() => {
        if (page > pages) setPage(1);
    }, [pages, page]);
    // Reset a pagina 1 quando cambia la dimensione pagina
    useEffect(() => {
        setPage(1);
    }, [pageSize]);

    const paged = useMemo(() => {
        if (!Array.isArray(items)) return items;
        if (isAll) return items;
        const start = (page - 1) * pageSize;
        return items.slice(start, start + pageSize);
    }, [items, page, pageSize, isAll]);

    return { paged, page, setPage, pageSize, setPageSize, pages, total };
}

export default function TablePager({
    page, setPage, pageSize, setPageSize, pages, total,
    label = "righe", testid = "table",
}) {
    if (!total) return null;
    return (
        <div
            className="flex flex-wrap items-center justify-center gap-3 px-4 py-2.5 border-t border-slate-100 bg-white"
            data-testid={`${testid}-pager`}
        >
            <Button variant="outline" size="sm" disabled={page <= 1}
                    onClick={() => setPage((p) => Math.max(1, p - 1))}
                    data-testid={`${testid}-page-prev`}>‹ Prec.</Button>
            <span className="text-xs text-slate-600">
                Pagina {page} di {pages} · {total} {label}
            </span>
            <Button variant="outline" size="sm" disabled={page >= pages}
                    onClick={() => setPage((p) => Math.min(pages, p + 1))}
                    data-testid={`${testid}-page-next`}>Succ. ›</Button>
            <select value={pageSize} onChange={(e) => {
                        const v = e.target.value;
                        setPageSize(v === "all" ? "all" : Number(v));
                    }}
                    className="ml-2 text-xs border border-slate-200 rounded px-2 py-1 bg-white"
                    data-testid={`${testid}-page-size`}>
                <option value={25}>25 / pagina</option>
                <option value={50}>50 / pagina</option>
                <option value={100}>100 / pagina</option>
                <option value={200}>200 / pagina</option>
                <option value="all">Tutte</option>
            </select>
        </div>
    );
}
