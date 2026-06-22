import { useState } from "react";
import { MoreVertical, Edit, Trash2, FileText, Printer } from "lucide-react";
import {
    DropdownMenu, DropdownMenuTrigger, DropdownMenuContent, DropdownMenuItem,
    DropdownMenuSeparator,
} from "@/components/ui/dropdown-menu";
import {
    AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
    AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";

/** Menu azioni standard per ogni riga di tabella.
 *  Props:
 *    onEdit, onDelete, onView (callback)
 *    canEdit, canDelete (boolean)
 *    label (nome entità: "polizza", "titolo", ...)
 *    extra (array di {label, icon, onClick})
 */
export default function RowActions({
    onEdit, onDelete, onView, canEdit = true, canDelete = true, label = "elemento",
    extra = [], testid,
}) {
    const [confirmOpen, setConfirmOpen] = useState(false);

    return (
        <>
            <DropdownMenu>
                <DropdownMenuTrigger asChild>
                    <button
                        data-testid={testid || "row-actions"}
                        className="p-1 rounded hover:bg-slate-100 text-slate-600"
                        onClick={(e) => e.stopPropagation()}
                    >
                        <MoreVertical size={16} />
                    </button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end" className="w-44">
                    {onView && (
                        <DropdownMenuItem onClick={onView} data-testid="action-view">
                            <FileText size={14} className="mr-2" /> Dettaglio
                        </DropdownMenuItem>
                    )}
                    {onEdit && canEdit && (
                        <DropdownMenuItem onClick={onEdit} data-testid="action-edit">
                            <Edit size={14} className="mr-2" /> Modifica
                        </DropdownMenuItem>
                    )}
                    {extra.map((x, i) => (
                        <DropdownMenuItem key={i} onClick={x.onClick} data-testid={x.testid}>
                            {x.icon && <span className="mr-2">{x.icon}</span>}{x.label}
                        </DropdownMenuItem>
                    ))}
                    {onDelete && canDelete && (
                        <>
                            <DropdownMenuSeparator />
                            <DropdownMenuItem
                                onClick={() => setConfirmOpen(true)}
                                className="text-rose-600 focus:text-rose-700"
                                data-testid="action-delete"
                            >
                                <Trash2 size={14} className="mr-2" /> Elimina
                            </DropdownMenuItem>
                        </>
                    )}
                </DropdownMenuContent>
            </DropdownMenu>

            <AlertDialog open={confirmOpen} onOpenChange={setConfirmOpen}>
                <AlertDialogContent>
                    <AlertDialogHeader>
                        <AlertDialogTitle>Conferma eliminazione</AlertDialogTitle>
                        <AlertDialogDescription>
                            Stai per eliminare definitivamente questo {label}. L&apos;operazione non &egrave; reversibile.
                        </AlertDialogDescription>
                    </AlertDialogHeader>
                    <AlertDialogFooter>
                        <AlertDialogCancel data-testid="confirm-cancel">Annulla</AlertDialogCancel>
                        <AlertDialogAction
                            data-testid="confirm-delete"
                            className="bg-rose-600 hover:bg-rose-700"
                            onClick={() => { setConfirmOpen(false); onDelete?.(); }}
                        >
                            Elimina
                        </AlertDialogAction>
                    </AlertDialogFooter>
                </AlertDialogContent>
            </AlertDialog>
        </>
    );
}

export function PrintButton({ onClick, label = "Stampa PDF", testid = "print-button" }) {
    return (
        <Button variant="outline" onClick={onClick} data-testid={testid}>
            <Printer size={14} className="mr-1" /> {label}
        </Button>
    );
}
