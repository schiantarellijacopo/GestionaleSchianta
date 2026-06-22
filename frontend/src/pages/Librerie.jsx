import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { PageHeader, Loading, Empty } from "@/components/Shared";
import { Card } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import {
    Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger, DialogFooter,
} from "@/components/ui/dialog";
import RowActions from "@/components/RowActions";
import { Plus, Landmark, Wallet, Package, Tags, Building2, UserCog, Shield } from "lucide-react";
import { toast } from "sonner";

const SECTIONS = [
    { key: "banche", label: "Banche", icon: <Landmark size={14} />, endpoint: "/librerie/banche" },
    { key: "conti-cassa", label: "Conti cassa / Canali", icon: <Wallet size={14} />, endpoint: "/librerie/conti-cassa" },
    { key: "prodotti", label: "Prodotti", icon: <Package size={14} />, endpoint: "/librerie/prodotti" },
    { key: "rami", label: "Rami", icon: <Tags size={14} />, endpoint: "/librerie/rami" },
    { key: "compagnie", label: "Compagnie", icon: <Building2 size={14} />, endpoint: "/compagnie" },
    { key: "utenti", label: "Utenti / Collaboratori", icon: <UserCog size={14} />, endpoint: "/auth/users" },
];

export default function Librerie() {
    return (
        <div data-testid="librerie-page">
            <PageHeader
                title="Librerie / Anagrafiche di sistema"
                subtitle="Banche, conti cassa, prodotti, rami: configurazioni riusate nei moduli"
            />
            <Tabs defaultValue="banche">
                <TabsList className="bg-slate-100">
                    {SECTIONS.map((s) => (
                        <TabsTrigger key={s.key} value={s.key} data-testid={`lib-tab-${s.key}`}>
                            {s.icon}<span className="ml-1.5">{s.label}</span>
                        </TabsTrigger>
                    ))}
                </TabsList>
                {SECTIONS.map((s) => (
                    <TabsContent key={s.key} value={s.key} className="mt-4">
                        <Sezione section={s} />
                    </TabsContent>
                ))}
            </Tabs>
        </div>
    );
}

function Sezione({ section }) {
    const [list, setList] = useState(null);
    const [open, setOpen] = useState(false);
    const [editing, setEditing] = useState(null);

    const load = () => api.get(section.endpoint).then((r) => setList(r.data));
    useEffect(() => { load(); /* eslint-disable-next-line */ }, [section.key]);

    const elimina = async (id) => {
        try {
            await api.delete(`${section.endpoint}/${id}`);
            toast.success("Eliminato"); load();
        } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
    };

    const FormDialog = SECTION_FORMS[section.key];

    return (
        <div>
            <div className="flex items-center justify-between mb-3">
                <span className="text-sm text-slate-500 num">{list ? `${list.length} elementi` : ""}</span>
                <Dialog open={open || !!editing} onOpenChange={(o) => { if (!o) { setOpen(false); setEditing(null); } }}>
                    <DialogTrigger asChild>
                        <Button data-testid={`lib-new-${section.key}`} onClick={() => setOpen(true)} className="bg-sky-700 hover:bg-sky-800">
                            <Plus size={14} className="mr-1" /> Nuovo
                        </Button>
                    </DialogTrigger>
                    <FormDialog
                        section={section}
                        editing={editing}
                        onClose={() => { setOpen(false); setEditing(null); load(); }}
                    />
                </Dialog>
            </div>

            <Card className="border-slate-200 overflow-hidden">
                {list === null ? <Loading /> : list.length === 0 ? <Empty /> :
                    <ListaSezione section={section} list={list} onEdit={setEditing} onDelete={elimina} />
                }
            </Card>
        </div>
    );
}

function ListaSezione({ section, list, onEdit, onDelete }) {
    if (section.key === "banche") {
        return (
            <table className="tbl w-full">
                <thead><tr><th>Nome</th><th>ABI</th><th>Referente</th><th>Note</th><th></th></tr></thead>
                <tbody>
                    {list.map((b) => (
                        <tr key={b.id}>
                            <td className="font-medium">{b.nome}</td>
                            <td className="num text-xs">{b.codice_abi || "-"}</td>
                            <td>{b.referente || "-"}</td>
                            <td className="text-xs text-slate-500">{b.note || ""}</td>
                            <td className="text-right">
                                <RowActions onEdit={() => onEdit(b)} onDelete={() => onDelete(b.id)} label="banca" />
                            </td>
                        </tr>
                    ))}
                </tbody>
            </table>
        );
    }
    if (section.key === "conti-cassa") {
        return (
            <table className="tbl w-full">
                <thead><tr><th>Nome</th><th>Tipo</th><th>IBAN</th><th className="text-right">Saldo iniz.</th><th>Attivo</th><th></th></tr></thead>
                <tbody>
                    {list.map((c) => (
                        <tr key={c.id}>
                            <td className="font-medium">{c.nome}</td>
                            <td><span className="badge badge-neutral">{c.tipo}</span></td>
                            <td className="num text-xs">{c.iban || "-"}</td>
                            <td className="num text-right">{Number(c.saldo_iniziale || 0).toFixed(2)}</td>
                            <td>{c.attivo ? <span className="badge badge-success">sì</span> : <span className="badge badge-neutral">no</span>}</td>
                            <td className="text-right">
                                <RowActions onEdit={() => onEdit(c)} onDelete={() => onDelete(c.id)} label="conto" />
                            </td>
                        </tr>
                    ))}
                </tbody>
            </table>
        );
    }
    if (section.key === "prodotti") {
        return (
            <table className="tbl w-full">
                <thead><tr><th>Nome</th><th>Ramo</th><th>Compagnia</th><th>Descrizione</th><th></th></tr></thead>
                <tbody>
                    {list.map((p) => (
                        <tr key={p.id}>
                            <td className="font-medium">{p.nome}</td>
                            <td><span className="badge badge-neutral">{p.ramo || "-"}</span></td>
                            <td className="text-xs">{p.compagnia_id || "-"}</td>
                            <td className="text-xs text-slate-500">{p.descrizione || ""}</td>
                            <td className="text-right">
                                <RowActions onEdit={() => onEdit(p)} onDelete={() => onDelete(p.id)} label="prodotto" />
                            </td>
                        </tr>
                    ))}
                </tbody>
            </table>
        );
    }
    // rami
    if (section.key === "rami") {
        return (
            <table className="tbl w-full">
                <thead><tr><th>Codice</th><th>Nome</th><th>Descrizione</th><th></th></tr></thead>
                <tbody>
                    {list.map((r) => (
                        <tr key={r.id}>
                            <td className="num font-medium">{r.codice}</td>
                            <td>{r.nome}</td>
                            <td className="text-xs text-slate-500">{r.descrizione || ""}</td>
                            <td className="text-right">
                                <RowActions onEdit={() => onEdit(r)} onDelete={() => onDelete(r.id)} label="ramo" />
                            </td>
                        </tr>
                    ))}
                </tbody>
            </table>
        );
    }
    if (section.key === "compagnie") {
        return (
            <table className="tbl w-full">
                <thead><tr><th>Codice</th><th>Ragione sociale</th><th>Referente</th><th>Email</th><th>Trattiene Provv.</th><th>Attiva</th><th></th></tr></thead>
                <tbody>
                    {list.map((c) => (
                        <tr key={c.id}>
                            <td className="num text-xs">{c.codice}</td>
                            <td className="font-medium">{c.ragione_sociale}</td>
                            <td>{c.referente || "-"}</td>
                            <td className="text-xs">{c.email || "-"}</td>
                            <td>{c.trattiene_provvigioni !== false ? <span className="badge badge-success">sì</span> : <span className="badge badge-neutral">no</span>}</td>
                            <td>{c.attiva ? <span className="badge badge-success">sì</span> : <span className="badge badge-neutral">no</span>}</td>
                            <td className="text-right">
                                <RowActions onEdit={() => onEdit(c)} onDelete={() => onDelete(c.id)} label="compagnia" />
                            </td>
                        </tr>
                    ))}
                </tbody>
            </table>
        );
    }
    // utenti
    const ROLE_COLORS = {
        admin: "badge-danger", collaboratore: "badge-info",
        dipendente: "badge-success", cliente: "badge-neutral",
    };
    return (
        <table className="tbl w-full">
            <thead><tr><th>Nome</th><th>Email</th><th>Ruolo</th><th>Anagrafica collegata</th><th></th></tr></thead>
            <tbody>
                {list.map((u) => (
                    <tr key={u.id}>
                        <td className="font-medium flex items-center gap-2">
                            <div className="w-7 h-7 rounded-full bg-slate-200 text-slate-700 flex items-center justify-center text-xs font-semibold">
                                {(u.name || "?").charAt(0).toUpperCase()}
                            </div>
                            {u.name}
                        </td>
                        <td className="text-xs">{u.email}</td>
                        <td><span className={`badge ${ROLE_COLORS[u.role] || "badge-neutral"} inline-flex items-center gap-1`}>
                            <Shield size={10} /> {u.role}
                        </span></td>
                        <td className="text-xs text-slate-500 num">{u.anagrafica_id ? u.anagrafica_id.slice(0, 8) : "-"}</td>
                        <td className="text-right">
                            <RowActions onEdit={() => onEdit(u)} onDelete={() => onDelete(u.id)} label="utente" />
                        </td>
                    </tr>
                ))}
            </tbody>
        </table>
    );
}

const SECTION_FORMS = {
    "banche": BancaForm,
    "conti-cassa": ContoForm,
    "prodotti": ProdottoForm,
    "rami": RamoForm,
    "compagnie": CompagniaForm,
    "utenti": UtenteForm,
};

function GenericForm({ section, editing, onClose, fields, defaults }) {
    const [f, setF] = useState(editing || defaults);
    const isEdit = !!editing;
    const set = (k, v) => setF((p) => ({ ...p, [k]: v }));

    const save = async () => {
        try {
            if (isEdit) {
                await api.put(`${section.endpoint}/${editing.id}`, f);
                toast.success("Aggiornato");
            } else {
                await api.post(section.endpoint, f);
                toast.success("Creato");
            }
            onClose();
        } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
    };

    return (
        <DialogContent className="max-w-lg">
            <DialogHeader><DialogTitle>{isEdit ? "Modifica" : "Nuovo"} {section.label.toLowerCase()}</DialogTitle></DialogHeader>
            <div className="space-y-3 py-2">
                {fields(f, set)}
            </div>
            <DialogFooter>
                <Button data-testid={`lib-save-${section.key}`} onClick={save} className="bg-sky-700 hover:bg-sky-800">
                    {isEdit ? "Aggiorna" : "Salva"}
                </Button>
            </DialogFooter>
        </DialogContent>
    );
}

function BancaForm({ section, editing, onClose }) {
    return <GenericForm section={section} editing={editing} onClose={onClose}
        defaults={{ nome: "", codice_abi: "", referente: "", note: "", attiva: true }}
        fields={(f, set) => (
            <>
                <div><Label>Nome banca *</Label><Input value={f.nome || ""} onChange={(e) => set("nome", e.target.value)} /></div>
                <div className="grid grid-cols-2 gap-3">
                    <div><Label>Codice ABI</Label><Input value={f.codice_abi || ""} onChange={(e) => set("codice_abi", e.target.value)} /></div>
                    <div><Label>Referente</Label><Input value={f.referente || ""} onChange={(e) => set("referente", e.target.value)} /></div>
                </div>
                <div><Label>Note</Label><Input value={f.note || ""} onChange={(e) => set("note", e.target.value)} /></div>
            </>
        )}
    />;
}

function ContoForm({ section, editing, onClose }) {
    const [banche, setBanche] = useState([]);
    useEffect(() => { api.get("/librerie/banche").then((r) => setBanche(r.data)); }, []);
    return <GenericForm section={section} editing={editing} onClose={onClose}
        defaults={{ nome: "", tipo: "banca", banca_id: "", iban: "", saldo_iniziale: 0, ordine: 0, attivo: true }}
        fields={(f, set) => (
            <>
                <div><Label>Nome conto *</Label><Input value={f.nome || ""} onChange={(e) => set("nome", e.target.value)} /></div>
                <div className="grid grid-cols-2 gap-3">
                    <div>
                        <Label>Tipo</Label>
                        <Select value={f.tipo || "banca"} onValueChange={(v) => set("tipo", v)}>
                            <SelectTrigger><SelectValue /></SelectTrigger>
                            <SelectContent>
                                <SelectItem value="cassa">Cassa</SelectItem>
                                <SelectItem value="banca">Banca</SelectItem>
                                <SelectItem value="carta">Carta</SelectItem>
                                <SelectItem value="rid">RID / Direzione</SelectItem>
                                <SelectItem value="online">Online</SelectItem>
                                <SelectItem value="altro">Altro</SelectItem>
                            </SelectContent>
                        </Select>
                    </div>
                    <div>
                        <Label>Banca collegata</Label>
                        <Select value={f.banca_id || ""} onValueChange={(v) => set("banca_id", v)}>
                            <SelectTrigger><SelectValue placeholder="-" /></SelectTrigger>
                            <SelectContent>
                                {banche.map((b) => <SelectItem key={b.id} value={b.id}>{b.nome}</SelectItem>)}
                            </SelectContent>
                        </Select>
                    </div>
                </div>
                <div className="grid grid-cols-3 gap-3">
                    <div><Label>IBAN</Label><Input value={f.iban || ""} onChange={(e) => set("iban", e.target.value)} /></div>
                    <div><Label>Saldo iniziale €</Label><Input type="number" step="0.01" value={f.saldo_iniziale || 0} onChange={(e) => set("saldo_iniziale", parseFloat(e.target.value) || 0)} /></div>
                    <div><Label>Ordine</Label><Input type="number" value={f.ordine || 0} onChange={(e) => set("ordine", parseInt(e.target.value) || 0)} /></div>
                </div>
            </>
        )}
    />;
}

function ProdottoForm({ section, editing, onClose }) {
    const [compagnie, setCompagnie] = useState([]);
    const [rami, setRami] = useState([]);
    useEffect(() => {
        api.get("/compagnie").then((r) => setCompagnie(r.data));
        api.get("/librerie/rami").then((r) => setRami(r.data));
    }, []);
    return <GenericForm section={section} editing={editing} onClose={onClose}
        defaults={{ nome: "", ramo: "", compagnia_id: "", descrizione: "", attivo: true }}
        fields={(f, set) => (
            <>
                <div><Label>Nome prodotto *</Label><Input value={f.nome || ""} onChange={(e) => set("nome", e.target.value)} /></div>
                <div className="grid grid-cols-2 gap-3">
                    <div>
                        <Label>Ramo</Label>
                        <Select value={f.ramo || ""} onValueChange={(v) => set("ramo", v)}>
                            <SelectTrigger><SelectValue placeholder="-" /></SelectTrigger>
                            <SelectContent>
                                {rami.map((r) => <SelectItem key={r.id} value={r.codice}>{r.nome}</SelectItem>)}
                            </SelectContent>
                        </Select>
                    </div>
                    <div>
                        <Label>Compagnia</Label>
                        <Select value={f.compagnia_id || ""} onValueChange={(v) => set("compagnia_id", v)}>
                            <SelectTrigger><SelectValue placeholder="-" /></SelectTrigger>
                            <SelectContent>
                                {compagnie.map((c) => <SelectItem key={c.id} value={c.id}>{c.ragione_sociale}</SelectItem>)}
                            </SelectContent>
                        </Select>
                    </div>
                </div>
                <div><Label>Descrizione</Label><Input value={f.descrizione || ""} onChange={(e) => set("descrizione", e.target.value)} /></div>
            </>
        )}
    />;
}

function RamoForm({ section, editing, onClose }) {
    return <GenericForm section={section} editing={editing} onClose={onClose}
        defaults={{ codice: "", nome: "", descrizione: "", attivo: true }}
        fields={(f, set) => (
            <>
                <div className="grid grid-cols-2 gap-3">
                    <div><Label>Codice *</Label><Input value={f.codice || ""} onChange={(e) => set("codice", e.target.value.toUpperCase())} /></div>
                    <div><Label>Nome *</Label><Input value={f.nome || ""} onChange={(e) => set("nome", e.target.value)} /></div>
                </div>
                <div><Label>Descrizione</Label><Input value={f.descrizione || ""} onChange={(e) => set("descrizione", e.target.value)} /></div>
            </>
        )}
    />;
}

function CompagniaForm({ section, editing, onClose }) {
    return <GenericForm section={section} editing={editing} onClose={onClose}
        defaults={{
            codice: "", ragione_sociale: "", referente: "", email: "", telefono: "",
            sito_web: "", mandato: "", trattiene_provvigioni: true, attiva: true,
        }}
        fields={(f, set) => (
            <>
                <div className="grid grid-cols-2 gap-3">
                    <div><Label>Codice *</Label><Input value={f.codice || ""} onChange={(e) => set("codice", e.target.value.toUpperCase())} /></div>
                    <div><Label>Ragione sociale *</Label><Input value={f.ragione_sociale || ""} onChange={(e) => set("ragione_sociale", e.target.value)} /></div>
                </div>
                <div className="grid grid-cols-2 gap-3">
                    <div><Label>Referente</Label><Input value={f.referente || ""} onChange={(e) => set("referente", e.target.value)} /></div>
                    <div><Label>Mandato</Label><Input value={f.mandato || ""} onChange={(e) => set("mandato", e.target.value)} /></div>
                </div>
                <div className="grid grid-cols-2 gap-3">
                    <div><Label>Email</Label><Input value={f.email || ""} onChange={(e) => set("email", e.target.value)} /></div>
                    <div><Label>Telefono</Label><Input value={f.telefono || ""} onChange={(e) => set("telefono", e.target.value)} /></div>
                </div>
                <div><Label>Sito web</Label><Input value={f.sito_web || ""} onChange={(e) => set("sito_web", e.target.value)} /></div>
                <div className="bg-amber-50 border border-amber-200 rounded-md p-3">
                    <div className="flex items-center gap-2">
                        <input
                            type="checkbox"
                            id="trattiene_provv"
                            checked={f.trattiene_provvigioni !== false}
                            onChange={(e) => set("trattiene_provvigioni", e.target.checked)}
                        />
                        <Label htmlFor="trattiene_provv" className="cursor-pointer font-medium">
                            Trattengo le provvigioni all&apos;incasso
                        </Label>
                    </div>
                    <div className="text-xs text-amber-800 mt-1.5">
                        {f.trattiene_provvigioni !== false
                            ? "Verso alla compagnia il PREMIO meno le provvigioni. Saldo cassa compagnia = -(premio - provvigioni)."
                            : "Verso il premio INTERO alla compagnia. Le provvigioni mi vengono accreditate a parte. Saldo cassa = -premio + provvigioni a credito."}
                    </div>
                </div>
                <div className="flex items-center gap-2">
                    <input type="checkbox" id="comp_attiva" checked={f.attiva !== false} onChange={(e) => set("attiva", e.target.checked)} />
                    <Label htmlFor="comp_attiva" className="cursor-pointer">Attiva</Label>
                </div>
            </>
        )}
    />;
}

function UtenteForm({ section, editing, onClose }) {
    const [anagrafiche, setAnagrafiche] = useState([]);
    useEffect(() => { api.get("/anagrafiche").then((r) => setAnagrafiche(r.data)); }, []);
    return <GenericForm section={section} editing={editing} onClose={onClose}
        defaults={{ name: "", email: "", password: "", role: "dipendente", anagrafica_id: null }}
        fields={(f, set) => (
            <>
                <div className="grid grid-cols-2 gap-3">
                    <div><Label>Nome *</Label><Input value={f.name || ""} onChange={(e) => set("name", e.target.value)} /></div>
                    <div><Label>Email *</Label><Input type="email" value={f.email || ""} onChange={(e) => set("email", e.target.value.toLowerCase())} /></div>
                </div>
                <div>
                    <Label>{editing ? "Nuova password (lasciare vuoto per non cambiare)" : "Password *"}</Label>
                    <Input
                        type="password"
                        value={f.password || ""}
                        onChange={(e) => set("password", e.target.value)}
                        placeholder={editing ? "•••••••• (invariata)" : ""}
                    />
                </div>
                <div>
                    <Label>Ruolo *</Label>
                    <Select value={f.role || "dipendente"} onValueChange={(v) => set("role", v)}>
                        <SelectTrigger data-testid="utente-role"><SelectValue /></SelectTrigger>
                        <SelectContent>
                            <SelectItem value="admin">Amministratore - vede e modifica tutto</SelectItem>
                            <SelectItem value="collaboratore">Collaboratore - vede tutto, no cancellazioni</SelectItem>
                            <SelectItem value="dipendente">Dipendente - vede tutto, no compagnie/import</SelectItem>
                            <SelectItem value="cliente">Cliente - vede solo i propri dati</SelectItem>
                        </SelectContent>
                    </Select>
                </div>
                {f.role === "cliente" && (
                    <div>
                        <Label>Anagrafica cliente collegata *</Label>
                        <Select value={f.anagrafica_id || ""} onValueChange={(v) => set("anagrafica_id", v)}>
                            <SelectTrigger><SelectValue placeholder="Seleziona anagrafica..." /></SelectTrigger>
                            <SelectContent>
                                {anagrafiche.map((a) => <SelectItem key={a.id} value={a.id}>{a.ragione_sociale}</SelectItem>)}
                            </SelectContent>
                        </Select>
                        <div className="text-xs text-slate-500 mt-1">Il cliente vedrà solo le polizze/sinistri legati a questa anagrafica.</div>
                    </div>
                )}
                <div className="bg-slate-50 border border-slate-200 rounded-md p-3 text-xs space-y-1">
                    <div className="font-semibold text-slate-700 mb-1">Livelli di visibilità:</div>
                    <div><span className="badge badge-danger">admin</span> Accesso completo, gestione utenti, eliminazioni</div>
                    <div><span className="badge badge-info">collaboratore</span> Vede e gestisce tutto, no eliminazioni critiche</div>
                    <div><span className="badge badge-success">dipendente</span> Operatività su clienti/polizze/sinistri, no librerie</div>
                    <div><span className="badge badge-neutral">cliente</span> Vede solo le proprie polizze e i propri sinistri</div>
                </div>
            </>
        )}
    />;
}
