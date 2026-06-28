import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { PageHeader, Loading, Empty } from "@/components/Shared";
import { Card } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import {
    Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger, DialogFooter,
} from "@/components/ui/dialog";
import RowActions from "@/components/RowActions";
import { Plus, Landmark, Wallet, Package, Tags, Building2, UserCog, Shield, Building, Percent, Upload, FileText, Trash2, GraduationCap, RotateCw, Pencil, Mail, Search } from "lucide-react";
import { toast } from "sonner";

const SECTIONS = [
    { key: "azienda", label: "Azienda", icon: <Building size={14} />, endpoint: "/librerie/azienda" },
    { key: "banche", label: "Banche", icon: <Landmark size={14} />, endpoint: "/librerie/banche" },
    { key: "conti-cassa", label: "Conti deposito", icon: <Wallet size={14} />, endpoint: "/librerie/conti-cassa" },
    { key: "mezzi-pagamento", label: "Modalità pagamento", icon: <Wallet size={14} />, endpoint: "/librerie/mezzi-pagamento" },
    { key: "tipi-pagamento", label: "Tipi pagamento", icon: <Wallet size={14} />, endpoint: "/librerie/tipi-pagamento" },
    { key: "comunicazioni", label: "Comunicazioni (Email/SMS/WhatsApp)", icon: <Mail size={14} />, endpoint: "/librerie/comunicazioni", custom: true },
    { key: "modelli", label: "Gestioni Modelli (template)", icon: <FileText size={14} />, endpoint: "/librerie/modelli", custom: true },
    { key: "prodotti", label: "Prodotti", icon: <Package size={14} />, endpoint: "/librerie/prodotti" },
    { key: "rami", label: "Rami", icon: <Tags size={14} />, endpoint: "/librerie/rami" },
    { key: "compagnie", label: "Compagnie", icon: <Building2 size={14} />, endpoint: "/compagnie" },
    { key: "utenti", label: "Utenti / Collaboratori", icon: <UserCog size={14} />, endpoint: "/auth/users" },
    { key: "schema-provvigionale", label: "Sistema provvigionale", icon: <Percent size={14} />, endpoint: "/librerie/schema-provvigionale" },
    { key: "voci-ricorsive", label: "Voci ricorsive collab.", icon: <RotateCw size={14} />, endpoint: "/voci-ricorsive-collab", custom: true },
];

export default function Librerie() {
    return (
        <div data-testid="librerie-page">
            <PageHeader
                title="Librerie / Anagrafiche di sistema"
                subtitle="Banche, conti cassa, prodotti, rami: configurazioni riusate nei moduli"
            />
            <Tabs defaultValue="azienda">
                <TabsList className="bg-slate-100 flex-wrap h-auto">
                    {SECTIONS.map((s) => (
                        <TabsTrigger key={s.key} value={s.key} data-testid={`lib-tab-${s.key}`}>
                            {s.icon}<span className="ml-1.5">{s.label}</span>
                        </TabsTrigger>
                    ))}
                </TabsList>
                {SECTIONS.map((s) => (
                    <TabsContent key={s.key} value={s.key} className="mt-4">
                        {s.key === "azienda" ? <AziendaSezione />
                            : s.key === "voci-ricorsive" ? <VociRicorsiveSezione />
                            : s.key === "comunicazioni" ? <ComunicazioniSezione />
                            : s.key === "modelli" ? <ModelliSezione />
                            : <Sezione section={s} />}
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

    const applicaMapping = async () => {
        if (!window.confirm("Applicare il mapping a TUTTE le polizze esistenti?")) return;
        try {
            const url = section.key === "mapping-garanzie"
                ? "/librerie/mapping-garanzie/applica-a-polizze"
                : "/librerie/mapping-operatori/applica-a-polizze";
            const r = await api.post(url);
            toast.success(`${r.data.polizze_aggiornate} polizze aggiornate`);
        } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
    };

    const showApplica = section.key === "mapping-garanzie" || section.key === "mapping-operatori";

    return (
        <div>
            <div className="flex items-center justify-between mb-3">
                <span className="text-sm text-slate-500 num">{list ? `${list.length} elementi` : ""}</span>
                <div className="flex gap-2">
                    {showApplica && (
                        <Button variant="outline" size="sm" onClick={applicaMapping} data-testid={`lib-apply-${section.key}`}>
                            Applica a polizze esistenti
                        </Button>
                    )}
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
                <thead><tr><th>Nome</th><th>Tipo</th><th>IBAN</th><th className="text-right">Saldo iniz.</th><th>Attivo</th><th title="Non mostrare in Prima Nota">PN</th><th title="Escludi da calcolo liquidità">Liq</th><th></th></tr></thead>
                <tbody>
                    {list.map((c) => (
                        <tr key={c.id}>
                            <td className="font-medium">{c.nome}</td>
                            <td><span className="badge badge-neutral">{c.tipo}</span></td>
                            <td className="num text-xs">{c.iban || "-"}</td>
                            <td className="num text-right">{Number(c.saldo_iniziale || 0).toFixed(2)}</td>
                            <td>{c.attivo ? <span className="badge badge-success">sì</span> : <span className="badge badge-neutral">no</span>}</td>
                            <td>{c.nascondi_prima_nota ? <span className="badge badge-warning">nascosto</span> : <span className="text-slate-400 text-xs">—</span>}</td>
                            <td>{c.escludi_da_liquidita ? <span className="badge badge-warning">escluso</span> : <span className="text-slate-400 text-xs">—</span>}</td>
                            <td className="text-right">
                                <RowActions onEdit={() => onEdit(c)} onDelete={() => onDelete(c.id)} label="conto" />
                            </td>
                        </tr>
                    ))}
                </tbody>
            </table>
        );
    }
    if (section.key === "tipi-pagamento") {
        return (
            <table className="tbl w-full">
                <thead><tr><th>Label</th><th>Modalità</th><th>Conto deposito</th><th className="text-right">Ordine</th><th>Attivo</th><th></th></tr></thead>
                <tbody>
                    {list.map((t) => (
                        <tr key={t.id}>
                            <td className="font-semibold uppercase">{t.label}</td>
                            <td className="text-xs"><span className="badge badge-neutral">{t.modalita_codice}</span></td>
                            <td className="text-xs text-slate-600">{t.conto_id ? <span className="num font-mono text-[10px]">{t.conto_id.slice(0,8)}</span> : <span className="italic text-slate-400">—</span>}</td>
                            <td className="num text-right">{t.ordine}</td>
                            <td>{t.attivo ? <span className="badge badge-success">sì</span> : <span className="badge badge-neutral">no</span>}</td>
                            <td className="text-right">
                                <RowActions onEdit={() => onEdit(t)} onDelete={() => onDelete(t.id)} label="tipo pagamento" />
                            </td>
                        </tr>
                    ))}
                </tbody>
            </table>
        );
    }
    if (section.key === "mezzi-pagamento") {
        return (
            <table className="tbl w-full">
                <thead><tr><th>Codice</th><th>Etichetta</th><th>Tipo conto</th><th className="text-right">Ordine</th><th>Attivo</th><th></th></tr></thead>
                <tbody>
                    {list.map((m) => (
                        <tr key={m.id}>
                            <td className="num font-mono text-xs">{m.codice}</td>
                            <td className="font-medium">{m.label}</td>
                            <td><span className="badge badge-neutral">{m.tipo_conto}</span></td>
                            <td className="num text-right">{m.ordine}</td>
                            <td>{m.attivo ? <span className="badge badge-success">sì</span> : <span className="badge badge-neutral">no</span>}</td>
                            <td className="text-right">
                                <RowActions onEdit={() => onEdit(m)} onDelete={() => onDelete(m.id)} label="mezzo pagamento" />
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
                <thead><tr><th>Nome</th><th>Ramo</th><th>Compagnia</th><th className="text-right">Mora (gg)</th><th>Descrizione</th><th></th></tr></thead>
                <tbody>
                    {list.map((p) => (
                        <tr key={p.id}>
                            <td className="font-medium">
                                {p.nome}
                                {p.is_libro_matricola && (
                                    <span className="ml-2 inline-block bg-amber-100 text-amber-800 text-[9px] font-bold px-1.5 py-0.5 rounded uppercase">L.M.</span>
                                )}
                            </td>
                            <td><span className="badge badge-neutral">{p.ramo || "-"}</span></td>
                            <td className="text-xs">{p.compagnia_id || "-"}</td>
                            <td className="num text-right font-medium">{p.termini_mora_giorni ?? 15}</td>
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
    if (section.key === "schema-provvigionale") {
        return (
            <table className="tbl w-full">
                <thead><tr><th>Nome</th><th>Collaboratore</th><th>Compagnia</th><th>Ramo</th><th className="text-right">% Collab</th><th className="text-right">% Premio</th><th>Attivo</th><th></th></tr></thead>
                <tbody>
                    {list.map((s) => (
                        <tr key={s.id}>
                            <td className="font-medium">{s.nome}</td>
                            <td className="text-xs">{s.collaboratore_nome || <span className="text-slate-400">tutti</span>}</td>
                            <td className="text-xs">{s.compagnia_nome || <span className="text-slate-400">tutte</span>}</td>
                            <td><span className="badge badge-neutral">{s.ramo || "tutti"}</span></td>
                            <td className="num text-right font-semibold text-emerald-700">{s.percentuale_collaboratore}%</td>
                            <td className="num text-right text-slate-600">{s.percentuale_su_premio}%</td>
                            <td>{s.attivo ? <span className="badge badge-success">sì</span> : <span className="badge badge-neutral">no</span>}</td>
                            <td className="text-right">
                                <RowActions onEdit={() => onEdit(s)} onDelete={() => onDelete(s.id)} label="schema" />
                            </td>
                        </tr>
                    ))}
                </tbody>
            </table>
        );
    }
    // mapping garanzie ANIA → nome personalizzato
    if (section.key === "mapping-garanzie") {
        return (
            <table className="tbl w-full">
                <thead><tr><th>Codice ANIA</th><th>Descrizione originale (ANIA)</th><th>Nome personalizzato</th><th>Note</th><th></th></tr></thead>
                <tbody>
                    {list.length === 0 && <tr><td colSpan="5" className="text-center text-slate-400 py-6">Nessun mapping. Le voci si creano automaticamente all&apos;import ANIA.</td></tr>}
                    {list.map((m) => (
                        <tr key={m.id}>
                            <td className="num font-medium">{m.codice_ania}</td>
                            <td className="text-xs">{m.descrizione_ania || "-"}</td>
                            <td className="font-medium text-sky-700">{m.nome_personalizzato || <span className="text-slate-400 italic">da mappare</span>}</td>
                            <td className="text-xs text-slate-500">{m.note || ""}</td>
                            <td className="text-right">
                                <RowActions onEdit={() => onEdit(m)} onDelete={() => onDelete(m.id)} label="mapping" />
                            </td>
                        </tr>
                    ))}
                </tbody>
            </table>
        );
    }
    // mapping operatori ANIA → user app
    if (section.key === "mapping-operatori") {
        return (
            <table className="tbl w-full">
                <thead><tr><th>Codice ANIA</th><th>Nome operatore (ANIA)</th><th>Utente collegato</th><th></th></tr></thead>
                <tbody>
                    {list.length === 0 && <tr><td colSpan="4" className="text-center text-slate-400 py-6">Nessun mapping. Le voci si creano automaticamente all&apos;import ANIA.</td></tr>}
                    {list.map((m) => (
                        <tr key={m.id}>
                            <td className="num font-medium">{m.codice_ania}</td>
                            <td className="text-xs">{m.descrizione_ania || m.nome_ania || "-"}</td>
                            <td>
                                {m.user
                                    ? <><span className="font-medium">{m.user.name}</span> <span className="text-[10px] text-slate-500">({m.user.role})</span></>
                                    : <span className="text-slate-400 italic">da mappare</span>}
                            </td>
                            <td className="text-right">
                                <RowActions onEdit={() => onEdit(m)} onDelete={() => onDelete(m.id)} label="mapping" />
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
    "mezzi-pagamento": MezzoPagamentoForm,
    "tipi-pagamento": TipoPagamentoForm,
    "prodotti": ProdottoForm,
    "rami": RamoForm,
    "compagnie": CompagniaForm,
    "utenti": UtenteForm,
    "schema-provvigionale": SchemaProvvForm,
    "mapping-garanzie": MappingGaranziaForm,
    "mapping-operatori": MappingOperatoreForm,
};

function MappingGaranziaForm({ section, editing, onClose }) {
    return <GenericForm section={section} editing={editing} onClose={onClose}
        defaults={{ codice_ania: "", descrizione_ania: "", nome_personalizzato: "", note: "" }}
        fields={(f, set) => (
            <>
                <div><Label>Codice ANIA *</Label><Input value={f.codice_ania || ""} onChange={(e) => set("codice_ania", e.target.value.toUpperCase())} data-testid="mg-codice" /></div>
                <div><Label>Descrizione originale (ANIA)</Label><Input value={f.descrizione_ania || ""} onChange={(e) => set("descrizione_ania", e.target.value)} placeholder="Auto-popolato all'import" /></div>
                <div><Label>Nome personalizzato</Label><Input value={f.nome_personalizzato || ""} onChange={(e) => set("nome_personalizzato", e.target.value)} placeholder="Come vuoi chiamarla nel CRM (es. 'RCA Standard')" data-testid="mg-nome" /></div>
                <div><Label>Note</Label><Input value={f.note || ""} onChange={(e) => set("note", e.target.value)} /></div>
            </>
        )}
    />;
}

function MappingOperatoreForm({ section, editing, onClose }) {
    const [users, setUsers] = useState([]);
    useEffect(() => {
        api.get("/auth/users").then((r) => setUsers(r.data.filter((u) => u.role !== "cliente")));
    }, []);
    return <GenericForm section={section} editing={editing} onClose={onClose}
        defaults={{ codice_ania: "", descrizione_ania: "", user_id: "" }}
        fields={(f, set) => (
            <>
                <div><Label>Codice operatore ANIA *</Label><Input value={f.codice_ania || ""} onChange={(e) => set("codice_ania", e.target.value)} data-testid="mo-codice" /></div>
                <div><Label>Nome operatore (ANIA)</Label><Input value={f.descrizione_ania || ""} onChange={(e) => set("descrizione_ania", e.target.value)} placeholder="Auto-popolato all'import" /></div>
                <div>
                    <Label>Utente del CRM collegato</Label>
                    <Select value={f.user_id || ""} onValueChange={(v) => set("user_id", v)}>
                        <SelectTrigger data-testid="mo-user-select"><SelectValue placeholder="Seleziona utente" /></SelectTrigger>
                        <SelectContent>
                            {users.map((u) => <SelectItem key={u.id} value={u.id}>{u.name} ({u.role})</SelectItem>)}
                        </SelectContent>
                    </Select>
                </div>
                <div className="text-xs text-slate-500 bg-sky-50 border border-sky-200 rounded p-2">
                    Dopo aver mappato gli operatori puoi cliccare il pulsante <b>&quot;Applica a polizze esistenti&quot;</b> (sotto la tabella) per rinominare/riassegnare in massa.
                </div>
            </>
        )}
    />;
}

function GenericForm({ section, editing, onClose, fields, defaults, dialogClass }) {
    const [f, setF] = useState(editing || defaults);
    const isEdit = !!editing;
    const set = (k, v) => setF((p) => ({ ...p, [k]: v }));

    // FIX: ricarica il form quando cambia editing (es. apertura dialog su voce diversa).
    // Senza questo, lo state resta legato alla PRIMA voce ed Edit mostrerebbe i campi vuoti.
    useEffect(() => {
        if (editing) setF({ ...defaults, ...editing });
        else setF(defaults);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [editing]);

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
        <DialogContent className={dialogClass || "max-w-lg"}>
            <DialogHeader><DialogTitle>{isEdit ? "Modifica" : "Nuovo"} {section.label.toLowerCase()}</DialogTitle></DialogHeader>
            <div className="space-y-3 py-2 max-h-[70vh] overflow-y-auto">
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
        defaults={{ nome: "", tipo: "banca", banca_id: "", iban: "", saldo_iniziale: 0, ordine: 0, attivo: true, nascondi_prima_nota: false, escludi_da_liquidita: false }}
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
                <div className="border-t pt-3 mt-2 space-y-2">
                    <div className="text-xs font-medium text-slate-600 uppercase">Opzioni operative</div>
                    <label className="flex items-start gap-2 text-sm cursor-pointer">
                        <input
                            type="checkbox"
                            checked={!!f.nascondi_prima_nota}
                            onChange={(e) => set("nascondi_prima_nota", e.target.checked)}
                            data-testid="conto-flag-nascondi-pn"
                            className="mt-0.5"
                        />
                        <span>
                            <strong>Non mostrare più in Prima Nota</strong>
                            <div className="text-[10px] text-slate-500">Utile per conti dismessi senza eliminarli.</div>
                        </span>
                    </label>
                    <label className="flex items-start gap-2 text-sm cursor-pointer">
                        <input
                            type="checkbox"
                            checked={!!f.escludi_da_liquidita}
                            onChange={(e) => set("escludi_da_liquidita", e.target.checked)}
                            data-testid="conto-flag-escludi-liq"
                            className="mt-0.5"
                        />
                        <span>
                            <strong>Escludi dal calcolo della liquidità (anche postera)</strong>
                            <div className="text-[10px] text-slate-500">Es. conti tecnici, prelievi soci, partite di giro.</div>
                        </span>
                    </label>
                </div>
            </>
        )}
    />;
}

function TipoPagamentoForm({ section, editing, onClose }) {
    const [modalita, setModalita] = useState([]);
    const [conti, setConti] = useState([]);
    useEffect(() => {
        api.get("/librerie/mezzi-pagamento").then((r) => setModalita(r.data || []));
        api.get("/librerie/conti-cassa", { params: { attivi: true } })
            .then((r) => setConti(r.data || []));
    }, []);
    return <GenericForm section={section} editing={editing} onClose={onClose}
        defaults={{
            label: "", modalita_codice: "", conto_id: "",
            ordine: 0, attivo: true, note: "",
        }}
        fields={(f, set) => {
            const autoLabel = () => {
                const mod = modalita.find((m) => m.codice === f.modalita_codice);
                const conto = conti.find((c) => c.id === f.conto_id);
                const lbl = [mod?.label || mod?.codice || "", conto?.nome || ""]
                    .filter(Boolean).join(" ").toUpperCase();
                set("label", lbl);
            };
            return (
                <>
                    <div className="grid grid-cols-2 gap-3">
                        <div>
                            <Label>Modalità *</Label>
                            <select
                                className="w-full border rounded h-9 px-2 text-sm"
                                value={f.modalita_codice || ""}
                                onChange={(e) => set("modalita_codice", e.target.value)}
                                data-testid="tp-modalita"
                            >
                                <option value="">— seleziona —</option>
                                {modalita.map((m) => (
                                    <option key={m.codice} value={m.codice}>{m.label}</option>
                                ))}
                            </select>
                        </div>
                        <div>
                            <Label>Conto deposito</Label>
                            <select
                                className="w-full border rounded h-9 px-2 text-sm"
                                value={f.conto_id || ""}
                                onChange={(e) => set("conto_id", e.target.value)}
                                data-testid="tp-conto"
                            >
                                <option value="">— nessuno —</option>
                                {conti.map((c) => (
                                    <option key={c.id} value={c.id}>{c.nome}</option>
                                ))}
                            </select>
                        </div>
                    </div>
                    <div>
                        <div className="flex items-center justify-between mb-1">
                            <Label>Label visualizzata *</Label>
                            <button
                                type="button" onClick={autoLabel}
                                className="text-[10px] text-sky-700 hover:text-sky-900 underline"
                                data-testid="tp-auto-label"
                            >Auto-componi</button>
                        </div>
                        <Input
                            placeholder="es. BONIFICO BPER SONDRIO"
                            value={f.label || ""}
                            onChange={(e) => set("label", e.target.value)}
                            data-testid="tp-label"
                        />
                    </div>
                    <div className="grid grid-cols-2 gap-3">
                        <div>
                            <Label>Ordine</Label>
                            <Input type="number" value={f.ordine || 0}
                                onChange={(e) => set("ordine", parseInt(e.target.value, 10) || 0)}
                            />
                        </div>
                        <div className="flex items-end">
                            <label className="flex items-center gap-2 text-sm">
                                <input
                                    type="checkbox"
                                    checked={f.attivo !== false}
                                    onChange={(e) => set("attivo", e.target.checked)}
                                />
                                Attivo
                            </label>
                        </div>
                    </div>
                    <div>
                        <Label>Note</Label>
                        <Input value={f.note || ""} onChange={(e) => set("note", e.target.value)} />
                    </div>
                </>
            );
        }}
    />;
}

function MezzoPagamentoForm({ section, editing, onClose }) {
    const [conti, setConti] = useState([]);
    useEffect(() => {
        api.get("/librerie/conti-cassa", { params: { attivi: true } })
            .then((r) => setConti(r.data || []));
    }, []);
    return <GenericForm section={section} editing={editing} onClose={onClose}
        defaults={{
            codice: "", label: "",
            tipo_conto: "altro", conto_default_id: "",
            icona: "", ordine: 0, attivo: true,
        }}
        fields={(f, set) => (
            <>
                <div className="grid grid-cols-2 gap-3">
                    <div>
                        <Label>Codice * (univoco, lowercase)</Label>
                        <Input
                            placeholder="es. bonifico, contanti"
                            value={f.codice}
                            onChange={(e) => set("codice", e.target.value)}
                            data-testid="mezzo-codice"
                        />
                    </div>
                    <div>
                        <Label>Etichetta visualizzata *</Label>
                        <Input
                            placeholder="es. Bonifico bancario"
                            value={f.label}
                            onChange={(e) => set("label", e.target.value)}
                            data-testid="mezzo-label"
                        />
                    </div>
                    <div>
                        <Label>Tipo conto associato</Label>
                        <select
                            className="w-full border rounded h-9 px-2 text-sm"
                            value={f.tipo_conto}
                            onChange={(e) => set("tipo_conto", e.target.value)}
                            data-testid="mezzo-tipo"
                        >
                            <option value="cassa">Cassa</option>
                            <option value="banca">Banca</option>
                            <option value="carta">Carta / POS</option>
                            <option value="rid">RID / SDD</option>
                            <option value="online">Online</option>
                            <option value="altro">Altro</option>
                        </select>
                    </div>
                    <div>
                        <Label>Conto default (opzionale)</Label>
                        <select
                            className="w-full border rounded h-9 px-2 text-sm"
                            value={f.conto_default_id || ""}
                            onChange={(e) => set("conto_default_id", e.target.value)}
                            data-testid="mezzo-conto-default"
                        >
                            <option value="">— auto (primo del tipo) —</option>
                            {conti.map((c) => (
                                <option key={c.id} value={c.id}>{c.nome} ({c.tipo})</option>
                            ))}
                        </select>
                    </div>
                    <div>
                        <Label>Ordine</Label>
                        <Input
                            type="number"
                            value={f.ordine}
                            onChange={(e) => set("ordine", e.target.value)}
                        />
                    </div>
                    <div className="flex items-end">
                        <label className="flex items-center gap-2 text-sm">
                            <input
                                type="checkbox"
                                checked={!!f.attivo}
                                onChange={(e) => set("attivo", e.target.checked)}
                            />
                            Attivo
                        </label>
                    </div>
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
    // Default mora: 30gg per Vita, 15gg per gli altri
    const defaultMoraFor = (ramo) => {
        if (!ramo) return 15;
        const r = String(ramo).toUpperCase();
        return ["VITA", "VITA_RC", "PREVIDENZA"].includes(r) ? 30 : 15;
    };
    return <GenericForm section={section} editing={editing} onClose={onClose}
        defaults={{ nome: "", ramo: "", compagnia_id: "", descrizione: "", termini_mora_giorni: 15, is_libro_matricola: false, attivo: true }}
        fields={(f, set) => {
            const ramoUpper = String(f.ramo || "").toUpperCase();
            const isRcAuto = ramoUpper.includes("RCA") || ramoUpper.includes("AUTO");
            return (
            <>
                <div><Label>Nome prodotto *</Label><Input value={f.nome || ""} onChange={(e) => set("nome", e.target.value)} /></div>
                <div className="grid grid-cols-2 gap-3">
                    <div>
                        <Label>Ramo</Label>
                        <Select value={f.ramo || ""} onValueChange={(v) => {
                            set("ramo", v);
                            if (!editing) set("termini_mora_giorni", defaultMoraFor(v));
                        }}>
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
                <div className="grid grid-cols-2 gap-3">
                    <div>
                        <Label>Termini di mora (gg) *</Label>
                        <Input
                            type="number" min="0" max="365"
                            value={f.termini_mora_giorni ?? 15}
                            onChange={(e) => set("termini_mora_giorni", parseInt(e.target.value || 0, 10))}
                            data-testid="prodotto-termini-mora"
                        />
                        <div className="text-[10px] text-slate-500 mt-1">
                            Default: 15 gg · Vita = 30 gg.
                        </div>
                    </div>
                    {isRcAuto && (
                        <div className="bg-amber-50 border border-amber-200 rounded p-2">
                            <label className="flex items-center gap-2 cursor-pointer">
                                <input
                                    type="checkbox"
                                    checked={!!f.is_libro_matricola}
                                    onChange={(e) => set("is_libro_matricola", e.target.checked)}
                                    data-testid="prodotto-libro-matricola"
                                />
                                <span className="text-sm font-medium text-amber-900">È Libro Matricola?</span>
                            </label>
                            <div className="text-[10px] text-amber-700 mt-1">
                                Solo per polizze RCA flotta: le polizze con questo prodotto avranno una tab &quot;Libro Matricola&quot; con applicazioni per veicolo.
                            </div>
                        </div>
                    )}
                    <div className="bg-sky-50 border border-sky-200 rounded p-2">
                        <label className="flex items-center gap-2 cursor-pointer">
                            <input
                                type="checkbox"
                                checked={!!f.mostra_sezione_veicolo}
                                onChange={(e) => set("mostra_sezione_veicolo", e.target.checked)}
                                data-testid="prodotto-mostra-veicolo"
                            />
                            <span className="text-sm font-medium text-sky-900">Mostra sezione &quot;Dati veicolo&quot;?</span>
                        </label>
                        <div className="text-[10px] text-sky-700 mt-1">
                            Spunta per prodotti che gestiscono un veicolo (es. RCA, Kasko, ARD, infortuni conducente). Per ramo <b>RCAuto</b> la sezione viene mostrata sempre, anche se non spuntato.
                        </div>
                    </div>
                </div>
                <div><Label>Descrizione</Label><Input value={f.descrizione || ""} onChange={(e) => set("descrizione", e.target.value)} /></div>
            </>
            );
        }}
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
    return <GenericForm section={section} editing={editing} onClose={onClose} dialogClass="max-w-3xl"
        defaults={{
            name: "", email: "", password: "", role: "dipendente", anagrafica_id: null,
            codice_fiscale: "", partita_iva: "", iban: "", indirizzo: "", telefono: "",
            perc_provvigione_default: 0, perc_ritenuta_acconto: 0, perc_inps_inarcassa: 0,
            note_fiscali: "", note_interne: "", attivo: true, email_aliases: [],
        }}
        fields={(f, set) => (
            <Tabs defaultValue="anagrafica" className="w-full">
                <TabsList className="bg-slate-100">
                    <TabsTrigger value="anagrafica">Anagrafica</TabsTrigger>
                    <TabsTrigger value="fiscale">Dati fiscali / IBAN</TabsTrigger>
                    {editing && f.role !== "cliente" && <TabsTrigger value="documenti">Documenti</TabsTrigger>}
                    {editing && f.role !== "cliente" && <TabsTrigger value="corsi">Corsi</TabsTrigger>}
                </TabsList>

                <TabsContent value="anagrafica" className="space-y-3 mt-4">
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
                    {f.role !== "cliente" && (
                        <div className="grid grid-cols-2 gap-3">
                            <div><Label>Telefono</Label><Input value={f.telefono || ""} onChange={(e) => set("telefono", e.target.value)} /></div>
                            <div><Label>Indirizzo</Label><Input value={f.indirizzo || ""} onChange={(e) => set("indirizzo", e.target.value.toUpperCase())} /></div>
                        </div>
                    )}
                </TabsContent>

                <TabsContent value="fiscale" className="space-y-3 mt-4">
                    <div className="grid grid-cols-2 gap-3">
                        <div><Label>Codice fiscale</Label><Input value={f.codice_fiscale || ""} onChange={(e) => set("codice_fiscale", e.target.value.toUpperCase())} /></div>
                        <div><Label>Partita IVA</Label><Input value={f.partita_iva || ""} onChange={(e) => set("partita_iva", e.target.value)} /></div>
                    </div>
                    <div><Label>IBAN</Label><Input value={f.iban || ""} onChange={(e) => set("iban", e.target.value.toUpperCase())} /></div>
                    <div className="grid grid-cols-3 gap-3 bg-amber-50 border border-amber-200 rounded-md p-3">
                        <div>
                            <Label>% Provvigione default</Label>
                            <Input type="number" step="0.01" value={f.perc_provvigione_default || 0} onChange={(e) => set("perc_provvigione_default", parseFloat(e.target.value) || 0)} />
                        </div>
                        <div>
                            <Label>% Ritenuta d&apos;acconto</Label>
                            <Input type="number" step="0.01" value={f.perc_ritenuta_acconto || 0} onChange={(e) => set("perc_ritenuta_acconto", parseFloat(e.target.value) || 0)} />
                        </div>
                        <div>
                            <Label>% INPS / Inarcassa</Label>
                            <Input type="number" step="0.01" value={f.perc_inps_inarcassa || 0} onChange={(e) => set("perc_inps_inarcassa", parseFloat(e.target.value) || 0)} />
                        </div>
                        <div className="col-span-3 text-xs text-amber-800">
                            Valori di default usati nei pagamenti provvigioni. Le regole specifiche per compagnia/ramo si gestiscono in <strong>Sistema provvigionale</strong>.
                        </div>
                    </div>
                    <div><Label>Note fiscali</Label><Input value={f.note_fiscali || ""} onChange={(e) => set("note_fiscali", e.target.value)} /></div>
                    <div><Label>Note interne (visibili solo admin)</Label><Input value={f.note_interne || ""} onChange={(e) => set("note_interne", e.target.value)} /></div>
                </TabsContent>

                {editing && f.role !== "cliente" && (
                    <TabsContent value="documenti" className="space-y-3 mt-4">
                        <DocumentiCollaboratore userId={editing.id} user={f} onChange={(updates) => Object.entries(updates).forEach(([k, v]) => set(k, v))} />
                    </TabsContent>
                )}

                {editing && f.role !== "cliente" && (
                    <TabsContent value="corsi" className="space-y-3 mt-4">
                        <CorsiCollaboratore userId={editing.id} corsi={f.corsi || []} onChange={(nuovi) => set("corsi", nuovi)} />
                    </TabsContent>
                )}

                <div className="bg-slate-50 border border-slate-200 rounded-md p-3 text-xs space-y-1 mt-4">
                    <div className="font-semibold text-slate-700 mb-1">Livelli di visibilità:</div>
                    <div><span className="badge badge-danger">admin</span> Accesso completo, gestione utenti, eliminazioni</div>
                    <div><span className="badge badge-info">collaboratore</span> Vede e gestisce tutto, no eliminazioni critiche</div>
                    <div><span className="badge badge-success">dipendente</span> Operatività su clienti/polizze/sinistri, no librerie</div>
                    <div><span className="badge badge-neutral">cliente</span> Vede solo le proprie polizze e i propri sinistri</div>
                </div>
            </Tabs>
        )}
    />;
}


// =================== AZIENDA (Singleton) ===================
function AziendaSezione() {
    const [f, setF] = useState(null);
    const [logoFile, setLogoFile] = useState(null);
    const [saving, setSaving] = useState(false);
    const load = () => api.get("/librerie/azienda").then((r) => setF(r.data));
    useEffect(() => { load(); }, []);

    if (!f) return <Loading />;
    const set = (k, v) => setF((p) => ({ ...p, [k]: v }));

    const salva = async () => {
        setSaving(true);
        try {
            await api.put("/librerie/azienda", f);
            if (logoFile) {
                const fd = new FormData();
                fd.append("file", logoFile);
                const r = await api.post("/librerie/azienda/logo", fd, { headers: { "Content-Type": "multipart/form-data" } });
                set("logo_url", r.data.logo_url);
                setLogoFile(null);
            }
            toast.success("Dati azienda salvati");
            load();
        } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
        finally { setSaving(false); }
    };

    return (
        <Card className="border-slate-200 p-6">
            <div className="flex items-center justify-between mb-5">
                <div>
                    <div className="text-base font-semibold text-slate-800">Dati Azienda</div>
                    <div className="text-xs text-slate-500">Utilizzati come intestazione su tutte le stampe (PDF, brogliaccio, estratti)</div>
                </div>
                <Button onClick={salva} disabled={saving} className="bg-sky-700 hover:bg-sky-800" data-testid="azienda-save">
                    {saving ? "Salvataggio..." : "Salva"}
                </Button>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                <div className="md:col-span-1">
                    <Label>Logo agenzia</Label>
                    <div className="mt-2 border border-dashed border-slate-300 rounded-md p-4 text-center bg-slate-50">
                        {(f.logo_url || logoFile) ? (
                            <div>
                                {logoFile ? (
                                    <img alt="logo preview" src={URL.createObjectURL(logoFile)} className="max-h-32 mx-auto mb-2 rounded" />
                                ) : (
                                    <img alt="logo" src={f.logo_url} className="max-h-32 mx-auto mb-2 rounded" />
                                )}
                                <div className="text-xs text-slate-500">{logoFile ? "(non ancora salvato)" : "Logo attuale"}</div>
                            </div>
                        ) : (
                            <div className="text-xs text-slate-500 py-6">Nessun logo caricato</div>
                        )}
                        <input
                            type="file"
                            accept="image/*"
                            id="logo-upload"
                            data-testid="azienda-logo-input"
                            onChange={(e) => setLogoFile(e.target.files?.[0] || null)}
                            className="hidden"
                        />
                        <label htmlFor="logo-upload" className="cursor-pointer mt-3 inline-flex items-center gap-1 text-xs text-sky-700 hover:underline">
                            <Upload size={12} /> Scegli logo (PNG/JPG, max 5MB)
                        </label>
                    </div>
                </div>

                <div className="md:col-span-2 space-y-3">
                    <div className="grid grid-cols-2 gap-3">
                        <div><Label>Ragione sociale *</Label><Input value={f.ragione_sociale || ""} onChange={(e) => set("ragione_sociale", e.target.value.toUpperCase())} data-testid="azienda-ragione" /></div>
                        <div><Label>Forma giuridica</Label><Input value={f.forma_giuridica || ""} onChange={(e) => set("forma_giuridica", e.target.value.toUpperCase())} placeholder="SRL / SAS / SNC / ditta individuale" /></div>
                    </div>
                    <div className="grid grid-cols-2 gap-3">
                        <div><Label>Partita IVA</Label><Input value={f.partita_iva || ""} onChange={(e) => set("partita_iva", e.target.value)} /></div>
                        <div><Label>Codice fiscale</Label><Input value={f.codice_fiscale || ""} onChange={(e) => set("codice_fiscale", e.target.value.toUpperCase())} /></div>
                    </div>
                    <div className="grid grid-cols-3 gap-3">
                        <div><Label>N° iscr. RUI</Label><Input value={f.rui || ""} onChange={(e) => set("rui", e.target.value.toUpperCase())} /></div>
                        <div><Label>Sezione RUI</Label><Input value={f.rui_sezione || ""} onChange={(e) => set("rui_sezione", e.target.value.toUpperCase())} placeholder="A/B/E..." /></div>
                        <div><Label>Data iscr. RUI</Label><Input type="date" value={f.data_iscrizione_rui || ""} onChange={(e) => set("data_iscrizione_rui", e.target.value)} /></div>
                    </div>
                    <div className="grid grid-cols-2 gap-3">
                        <div><Label>REA</Label><Input value={f.rea || ""} onChange={(e) => set("rea", e.target.value.toUpperCase())} /></div>
                        <div><Label>Capitale sociale</Label><Input value={f.capitale_sociale || ""} onChange={(e) => set("capitale_sociale", e.target.value)} /></div>
                    </div>

                    <div className="text-xs uppercase tracking-widest font-semibold text-slate-500 pt-2 border-t border-slate-100">Sede legale</div>
                    <div><Label>Indirizzo</Label><Input value={f.indirizzo || ""} onChange={(e) => set("indirizzo", e.target.value.toUpperCase())} /></div>
                    <div className="grid grid-cols-3 gap-3">
                        <div className="col-span-2"><Label>Comune</Label><Input value={f.comune || ""} onChange={(e) => set("comune", e.target.value.toUpperCase())} /></div>
                        <div><Label>Provincia</Label><Input value={f.provincia || ""} onChange={(e) => set("provincia", e.target.value.toUpperCase())} maxLength={2} /></div>
                    </div>
                    <div className="grid grid-cols-2 gap-3">
                        <div><Label>CAP</Label><Input value={f.cap || ""} onChange={(e) => set("cap", e.target.value)} /></div>
                        <div><Label>Nazione</Label><Input value={f.nazione || ""} onChange={(e) => set("nazione", e.target.value.toUpperCase())} /></div>
                    </div>

                    <div className="text-xs uppercase tracking-widest font-semibold text-slate-500 pt-2 border-t border-slate-100">Contatti</div>
                    <div className="grid grid-cols-2 gap-3">
                        <div><Label>Telefono</Label><Input value={f.telefono || ""} onChange={(e) => set("telefono", e.target.value)} /></div>
                        <div><Label>Fax</Label><Input value={f.fax || ""} onChange={(e) => set("fax", e.target.value)} /></div>
                    </div>
                    <div className="grid grid-cols-2 gap-3">
                        <div><Label>Email</Label><Input value={f.email || ""} onChange={(e) => set("email", e.target.value.toLowerCase())} /></div>
                        <div><Label>PEC</Label><Input value={f.pec || ""} onChange={(e) => set("pec", e.target.value.toLowerCase())} /></div>
                    </div>
                    <div><Label>Sito web</Label><Input value={f.sito_web || ""} onChange={(e) => set("sito_web", e.target.value)} /></div>

                    <div className="text-xs uppercase tracking-widest font-semibold text-slate-500 pt-2 border-t border-slate-100">Coordinate bancarie</div>
                    <div className="grid grid-cols-2 gap-3">
                        <div><Label>Banca</Label><Input value={f.banca || ""} onChange={(e) => set("banca", e.target.value.toUpperCase())} /></div>
                        <div><Label>IBAN</Label><Input value={f.iban || ""} onChange={(e) => set("iban", e.target.value.toUpperCase())} /></div>
                    </div>

                    <div><Label>Note in calce alle stampe</Label>
                        <textarea
                            className="w-full border border-slate-300 rounded-md px-3 py-2 text-sm"
                            rows={2}
                            value={f.note_footer_stampe || ""}
                            onChange={(e) => set("note_footer_stampe", e.target.value)}
                            placeholder="Es: Polizza assicurazione professionale, autorizzazione IVASS..."
                        />
                    </div>

                    {/* Sezione Commercialista */}
                    <div className="mt-6 pt-4 border-t border-slate-200">
                        <h3 className="text-sm font-semibold text-slate-700 uppercase tracking-wider mb-3">
                            Commercialista (invio Prima Nota chiusa)
                        </h3>
                        <div className="grid grid-cols-2 gap-3">
                            <div>
                                <Label>Nome commercialista</Label>
                                <Input
                                    value={f.nome_commercialista || ""}
                                    onChange={(e) => set("nome_commercialista", e.target.value)}
                                    placeholder="Es. Dott. Mario Rossi"
                                    data-testid="azienda-nome-commercialista"
                                />
                            </div>
                            <div>
                                <Label>Email commercialista</Label>
                                <Input
                                    type="email"
                                    value={f.email_commercialista || ""}
                                    onChange={(e) => set("email_commercialista", e.target.value)}
                                    placeholder="commercialista@studio.it"
                                    data-testid="azienda-email-commercialista"
                                />
                            </div>
                            <div className="col-span-2 flex items-center gap-2">
                                <input
                                    type="checkbox"
                                    id="auto-chiusura"
                                    checked={!!f.invio_automatico_chiusura}
                                    onChange={(e) => set("invio_automatico_chiusura", e.target.checked)}
                                    data-testid="azienda-auto-chiusura"
                                />
                                <Label htmlFor="auto-chiusura" className="cursor-pointer text-xs">
                                    Suggerisci l&apos;invio automatico al commercialista alla chiusura di ogni giornata
                                </Label>
                            </div>
                        </div>
                    </div>

                    {/* Sezione SMTP */}
                    <div className="mt-4 pt-4 border-t border-slate-200">
                        <h3 className="text-sm font-semibold text-slate-700 uppercase tracking-wider mb-3">
                            SMTP - Invio email (Prima Nota, ecc.)
                        </h3>
                        <div className="text-xs text-slate-500 mb-3">
                            Configurazione del server SMTP per inviare email dall&apos;applicazione (es. brogliaccio al commercialista). Per Gmail: <code>smtp.gmail.com:587</code> con password applicazione.
                        </div>
                        <div className="grid grid-cols-3 gap-3">
                            <div className="col-span-2">
                                <Label>SMTP Host</Label>
                                <Input
                                    value={f.smtp_host || ""}
                                    onChange={(e) => set("smtp_host", e.target.value)}
                                    placeholder="smtp.gmail.com"
                                    data-testid="azienda-smtp-host"
                                />
                            </div>
                            <div>
                                <Label>Porta</Label>
                                <Input
                                    type="number"
                                    value={f.smtp_port || 587}
                                    onChange={(e) => set("smtp_port", parseInt(e.target.value || 0))}
                                    placeholder="587"
                                    data-testid="azienda-smtp-port"
                                />
                            </div>
                            <div>
                                <Label>SMTP User (email)</Label>
                                <Input
                                    value={f.smtp_user || ""}
                                    onChange={(e) => set("smtp_user", e.target.value)}
                                    placeholder="account@gmail.com"
                                    data-testid="azienda-smtp-user"
                                />
                            </div>
                            <div>
                                <Label>SMTP Password</Label>
                                <Input
                                    type="password"
                                    value={f.smtp_password || ""}
                                    onChange={(e) => set("smtp_password", e.target.value)}
                                    placeholder="password app"
                                    data-testid="azienda-smtp-password"
                                />
                            </div>
                            <div>
                                <Label>From (mittente)</Label>
                                <Input
                                    value={f.smtp_from || ""}
                                    onChange={(e) => set("smtp_from", e.target.value)}
                                    placeholder="Assicura <noreply@assicura.it>"
                                />
                            </div>
                            <div className="col-span-3 flex items-center gap-2">
                                <input
                                    type="checkbox"
                                    id="smtp-tls"
                                    checked={f.smtp_use_tls !== false}
                                    onChange={(e) => set("smtp_use_tls", e.target.checked)}
                                />
                                <Label htmlFor="smtp-tls" className="cursor-pointer text-xs">
                                    Usa STARTTLS (consigliato per porta 587). Disabilita per SSL diretto su porta 465.
                                </Label>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </Card>
    );
}

// =================== SCHEMA PROVVIGIONALE ===================
function SchemaProvvForm({ section, editing, onClose }) {
    const [collab, setCollab] = useState([]);
    const [compagnie, setCompagnie] = useState([]);
    const [rami, setRami] = useState([]);
    useEffect(() => {
        api.get("/collaboratori").then((r) => setCollab(r.data));
        api.get("/compagnie").then((r) => setCompagnie(r.data));
        api.get("/librerie/rami").then((r) => setRami(r.data));
    }, []);
    return <GenericForm section={section} editing={editing} onClose={onClose}
        defaults={{ nome: "", collaboratore_id: null, compagnia_id: null, ramo: null,
                    percentuale_collaboratore: 0, percentuale_su_premio: 0,
                    descrizione: "", attivo: true }}
        fields={(f, set) => (
            <>
                <div><Label>Nome regola *</Label><Input value={f.nome || ""} onChange={(e) => set("nome", e.target.value)} placeholder="Es: Mario Rossi - RCA UnipolSai" /></div>
                <div className="grid grid-cols-3 gap-3">
                    <div>
                        <Label>Collaboratore</Label>
                        <Select value={f.collaboratore_id || "__null__"} onValueChange={(v) => set("collaboratore_id", v === "__null__" ? null : v)}>
                            <SelectTrigger><SelectValue /></SelectTrigger>
                            <SelectContent>
                                <SelectItem value="__null__">— tutti —</SelectItem>
                                {collab.map((c) => <SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>)}
                            </SelectContent>
                        </Select>
                    </div>
                    <div>
                        <Label>Compagnia</Label>
                        <Select value={f.compagnia_id || "__null__"} onValueChange={(v) => set("compagnia_id", v === "__null__" ? null : v)}>
                            <SelectTrigger><SelectValue /></SelectTrigger>
                            <SelectContent>
                                <SelectItem value="__null__">— tutte —</SelectItem>
                                {compagnie.map((c) => <SelectItem key={c.id} value={c.id}>{c.ragione_sociale}</SelectItem>)}
                            </SelectContent>
                        </Select>
                    </div>
                    <div>
                        <Label>Ramo</Label>
                        <Select value={f.ramo || "__null__"} onValueChange={(v) => set("ramo", v === "__null__" ? null : v)}>
                            <SelectTrigger><SelectValue /></SelectTrigger>
                            <SelectContent>
                                <SelectItem value="__null__">— tutti —</SelectItem>
                                {rami.map((r) => <SelectItem key={r.id} value={r.codice}>{r.nome}</SelectItem>)}
                            </SelectContent>
                        </Select>
                    </div>
                </div>
                <div className="grid grid-cols-2 gap-3 bg-emerald-50 border border-emerald-200 rounded-md p-3">
                    <div>
                        <Label>% Provvigione al collaboratore *</Label>
                        <Input type="number" step="0.01" value={f.percentuale_collaboratore || 0}
                               onChange={(e) => set("percentuale_collaboratore", parseFloat(e.target.value) || 0)} />
                        <div className="text-[10px] text-emerald-800 mt-1">Sul totale provvigione incassata dalla polizza</div>
                    </div>
                    <div>
                        <Label>% Provvigione su premio lordo</Label>
                        <Input type="number" step="0.01" value={f.percentuale_su_premio || 0}
                               onChange={(e) => set("percentuale_su_premio", parseFloat(e.target.value) || 0)} />
                        <div className="text-[10px] text-emerald-800 mt-1">Solo se non importata da ANIA</div>
                    </div>
                </div>
                <div><Label>Descrizione / note</Label><Input value={f.descrizione || ""} onChange={(e) => set("descrizione", e.target.value)} /></div>
                <div className="flex items-center gap-2">
                    <input type="checkbox" id="sp_attivo" checked={f.attivo !== false} onChange={(e) => set("attivo", e.target.checked)} />
                    <Label htmlFor="sp_attivo" className="cursor-pointer">Regola attiva</Label>
                </div>
                <div className="bg-slate-50 border border-slate-200 rounded-md p-3 text-xs text-slate-600">
                    <strong>Risoluzione:</strong> la regola più specifica (collaboratore + compagnia + ramo) prevale sulle regole generiche.
                    Lascia &quot;— tutti —&quot; per creare regole di default valide per più collaboratori / compagnie.
                </div>
            </>
        )}
    />;
}

// =================== DOCUMENTI COLLABORATORE ===================
const DOC_TIPI = [
    { key: "firma_digitale", label: "Firma digitale", urlField: "firma_digitale_url" },
    { key: "carta_identita", label: "Carta d'identità", urlField: "carta_identita_url" },
    { key: "casellario", label: "Casellario giudiziale", urlField: "casellario_url" },
    { key: "carichi_pendenti", label: "Carichi pendenti", urlField: "carichi_pendenti_url" },
    { key: "documento_iban", label: "Documento IBAN", urlField: "documento_iban_url" },
];

function DocumentiCollaboratore({ userId, user, onChange }) {
    const upload = async (tipo, file) => {
        if (!file) return;
        const fd = new FormData();
        fd.append("file", file);
        try {
            const r = await api.post(`/auth/users/${userId}/documenti/${tipo}`, fd,
                { headers: { "Content-Type": "multipart/form-data" } });
            onChange(r.data);
            toast.success("Documento caricato");
        } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
    };
    const del = async (tipo) => {
        if (!window.confirm("Eliminare il documento?")) return;
        const f = DOC_TIPI.find((d) => d.key === tipo);
        try {
            await api.delete(`/auth/users/${userId}/documenti/${tipo}`);
            onChange({ [f.urlField]: null });
            toast.success("Eliminato");
        } catch (e) { toast.error("Errore"); }
    };
    return (
        <div className="space-y-2">
            {DOC_TIPI.map((d) => {
                const url = user[d.urlField];
                return (
                    <div key={d.key} className="flex items-center justify-between border border-slate-200 rounded-md p-3 bg-slate-50">
                        <div className="flex items-center gap-2">
                            <FileText size={14} className="text-slate-500" />
                            <div>
                                <div className="text-sm font-medium">{d.label}</div>
                                <div className="text-xs text-slate-500">
                                    {url ? <a href={url} target="_blank" rel="noreferrer" className="text-sky-700 hover:underline">Visualizza documento</a> : "Nessun file caricato"}
                                </div>
                            </div>
                        </div>
                        <div className="flex items-center gap-2">
                            <input
                                type="file"
                                id={`doc-${d.key}`}
                                className="hidden"
                                data-testid={`doc-input-${d.key}`}
                                onChange={(e) => upload(d.key, e.target.files?.[0])}
                            />
                            <label htmlFor={`doc-${d.key}`} className="cursor-pointer text-xs px-3 py-1.5 bg-sky-700 hover:bg-sky-800 text-white rounded-md inline-flex items-center gap-1">
                                <Upload size={11} /> {url ? "Sostituisci" : "Carica"}
                            </label>
                            {url && (
                                <button onClick={() => del(d.key)} className="text-red-600 hover:bg-red-50 p-1.5 rounded">
                                    <Trash2 size={13} />
                                </button>
                            )}
                        </div>
                    </div>
                );
            })}
        </div>
    );
}

// =================== CORSI COLLABORATORE ===================
function CorsiCollaboratore({ userId, corsi, onChange }) {
    const [titolo, setTitolo] = useState("");
    const [ente, setEnte] = useState("");
    const [scadenza, setScadenza] = useState("");
    const [file, setFile] = useState(null);

    const aggiungi = async () => {
        if (!titolo && !file) { toast.error("Inserisci almeno titolo o attestato"); return; }
        try {
            let r;
            if (file) {
                const fd = new FormData();
                fd.append("file", file);
                fd.append("titolo", titolo);
                fd.append("ente", ente);
                fd.append("data_scadenza", scadenza);
                r = await api.post(`/auth/users/${userId}/corsi/upload`, fd,
                    { headers: { "Content-Type": "multipart/form-data" } });
            } else {
                r = await api.post(`/auth/users/${userId}/corsi`,
                    { titolo, ente, data_scadenza: scadenza || null });
            }
            onChange([...(corsi || []), r.data]);
            setTitolo(""); setEnte(""); setScadenza(""); setFile(null);
            toast.success("Corso aggiunto");
        } catch (e) { toast.error("Errore"); }
    };
    const rimuovi = async (corsoId) => {
        try {
            await api.delete(`/auth/users/${userId}/corsi/${corsoId}`);
            onChange((corsi || []).filter((c) => c.id !== corsoId));
        } catch (e) { toast.error("Errore"); }
    };

    return (
        <div className="space-y-3">
            <div className="border border-slate-200 rounded-md p-3 bg-slate-50">
                <div className="text-xs font-semibold text-slate-600 mb-2 flex items-center gap-1">
                    <GraduationCap size={13} /> Aggiungi corso / attestato
                </div>
                <div className="grid grid-cols-2 gap-2">
                    <div><Label className="text-xs">Titolo</Label><Input value={titolo} onChange={(e) => setTitolo(e.target.value)} placeholder="Es: IVASS 60h 2024" /></div>
                    <div><Label className="text-xs">Ente</Label><Input value={ente} onChange={(e) => setEnte(e.target.value)} placeholder="Es: IVASS" /></div>
                    <div><Label className="text-xs">Scadenza</Label><Input type="date" value={scadenza} onChange={(e) => setScadenza(e.target.value)} /></div>
                    <div>
                        <Label className="text-xs">Attestato (PDF/IMG, opz.)</Label>
                        <Input type="file" onChange={(e) => setFile(e.target.files?.[0] || null)} accept=".pdf,image/*" />
                    </div>
                </div>
                <Button size="sm" className="mt-2 bg-sky-700 hover:bg-sky-800" onClick={aggiungi}>
                    <Plus size={12} className="mr-1" /> Aggiungi
                </Button>
            </div>

            {(!corsi || corsi.length === 0) ? (
                <div className="text-center text-xs text-slate-400 py-4">Nessun corso registrato</div>
            ) : (
                <table className="tbl w-full">
                    <thead><tr><th>Titolo</th><th>Ente</th><th>Scadenza</th><th>Attestato</th><th></th></tr></thead>
                    <tbody>
                        {corsi.map((c) => (
                            <tr key={c.id}>
                                <td className="font-medium">{c.titolo}</td>
                                <td>{c.ente || "—"}</td>
                                <td className="num">{c.data_scadenza || "—"}</td>
                                <td>{c.url_attestato ? <a className="text-sky-700 hover:underline text-xs" href={c.url_attestato} target="_blank" rel="noreferrer">Apri</a> : "—"}</td>
                                <td className="text-right">
                                    <button onClick={() => rimuovi(c.id)} className="text-red-600 hover:bg-red-50 p-1 rounded"><Trash2 size={12} /></button>
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            )}
        </div>
    );
}


function _detectEmailProvider(host) {
    const h = (host || "").toLowerCase();
    if (h.includes("gmail") || h.includes("google")) return "google";
    if (h.includes("office365") || h.includes("outlook") || h.includes("microsoft")) return "microsoft";
    if (h) return "smtp";
    return "google";  // default
}

const EMAIL_PRESETS = {
    google: { smtp_host: "smtp.gmail.com", smtp_port: 587, smtp_use_tls: true },
    microsoft: { smtp_host: "smtp.office365.com", smtp_port: 587, smtp_use_tls: true },
    smtp: {},
};

function EmailSection({ f, set, onSet }) {
    const [provider, setProvider] = useState(_detectEmailProvider(f.smtp_host));
    const [testDest, setTestDest] = useState("");
    const [testing, setTesting] = useState(false);
    const [testPassato, setTestPassato] = useState(false);
    const attivo = !!(f.smtp_host && f.smtp_user && (f.smtp_password_set || f.smtp_password));

    const cambiaProvider = (p) => {
        setProvider(p);
        const preset = EMAIL_PRESETS[p] || {};
        onSet((prev) => ({ ...prev, ...preset }));
    };

    const inviaTest = async () => {
        setTesting(true);
        try {
            const dest = (testDest || f.smtp_user || "").trim();
            if (!dest) { toast.error("Inserisci un destinatario"); setTesting(false); return; }
            // salva prima eventuali modifiche pendenti
            const payload = { ...f };
            if (payload.smtp_password === "••••••••") delete payload.smtp_password;
            if (payload.twilio_auth_token === "••••••••") delete payload.twilio_auth_token;
            await api.put("/librerie/comunicazioni", payload);
            await api.post("/librerie/comunicazioni/test", {
                canale: "email", destinatario: dest,
            });
            toast.success(`Email test inviata a ${dest}`);
            setTestPassato(true);
        } catch (e) {
            toast.error(e.response?.data?.detail || "Errore invio test");
            setTestPassato(false);
        }
        setTesting(false);
    };

    return (
        <section data-testid="lib-com-email" className="border border-slate-200 rounded-lg p-4 bg-white">
            {/* Header con badge stato */}
            <div className="flex items-start gap-3 mb-3">
                <div className="bg-sky-100 text-sky-700 p-2 rounded-md mt-0.5">
                    <Mail size={18} />
                </div>
                <div className="flex-1">
                    <div className="flex items-center gap-2 flex-wrap">
                        <h4 className="text-base font-semibold text-slate-800">Email</h4>
                        {attivo && (
                            <span className="inline-flex items-center gap-1 text-[11px] px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200" data-testid="email-badge-attivo">
                                <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" /> Attivo
                            </span>
                        )}
                        {testPassato && (
                            <span className="inline-flex items-center gap-1 text-[11px] px-2 py-0.5 rounded-full bg-sky-50 text-sky-700 border border-sky-200">
                                ✓ Test passato
                            </span>
                        )}
                    </div>
                    <p className="text-xs text-slate-500 mt-1">
                        Invia notifiche via email da qualsiasi provider SMTP. <strong>Preset Google e Microsoft con un click.</strong>
                    </p>
                </div>
            </div>

            {/* Provider selector */}
            <div className="mb-4">
                <Label className="text-xs uppercase tracking-wide text-slate-500 font-semibold">Provider</Label>
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 mt-1.5">
                    {[
                        { v: "google", l: "Google (Gmail / Workspace)" },
                        { v: "microsoft", l: "Microsoft (Outlook / Office 365)" },
                        { v: "smtp", l: "SMTP personalizzato" },
                    ].map((p) => (
                        <button
                            key={p.v}
                            type="button"
                            onClick={() => cambiaProvider(p.v)}
                            className={`px-3 py-2.5 text-sm rounded-md border transition-all ${
                                provider === p.v
                                    ? "border-sky-500 ring-2 ring-sky-200 bg-sky-50 text-sky-900 font-medium"
                                    : "border-slate-200 bg-white text-slate-700 hover:border-slate-300"
                            }`}
                            data-testid={`com-email-provider-${p.v}`}
                        >
                            {p.l}
                        </button>
                    ))}
                </div>
                <p className="text-[11px] text-slate-500 mt-2">
                    {provider === "google" && (
                        <>Email aziendale Google. Crea una App Password su{" "}
                            <a href="https://myaccount.google.com/apppasswords" target="_blank" rel="noreferrer" className="text-sky-700 underline">
                                myaccount.google.com → Security → 2-Step → App passwords
                            </a>.
                        </>
                    )}
                    {provider === "microsoft" && (
                        <>Outlook/Office 365. Se hai 2FA attiva crea una{" "}
                            <a href="https://account.live.com/proofs/AppPassword" target="_blank" rel="noreferrer" className="text-sky-700 underline">
                                App Password
                            </a>{" "}da account.live.com.
                        </>
                    )}
                    {provider === "smtp" && (
                        <>Inserisci manualmente host SMTP, porta e credenziali del tuo provider (es. Aruba, Register.it, OVH, mailbox.org, ecc.).</>
                    )}
                </p>
            </div>

            {/* Campi base (sempre visibili) */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <div>
                    <Label>Indirizzo email <span className="text-rose-500">*</span></Label>
                    <Input placeholder="nome@dominio.it" value={f.smtp_user || ""}
                        onChange={(e) => set("smtp_user", e.target.value)}
                        data-testid="com-smtp-user" />
                </div>
                <div>
                    <Label>
                        {provider === "smtp" ? "Password" : "Password app"} <span className="text-rose-500">*</span>
                        {provider === "google" && (
                            <a href="https://myaccount.google.com/apppasswords" target="_blank" rel="noreferrer"
                                className="ml-2 text-[11px] text-sky-700 underline font-normal">crea su Google ↗</a>
                        )}
                        {provider === "microsoft" && (
                            <a href="https://account.live.com/proofs/AppPassword" target="_blank" rel="noreferrer"
                                className="ml-2 text-[11px] text-sky-700 underline font-normal">crea su Microsoft ↗</a>
                        )}
                    </Label>
                    <Input type="password"
                        placeholder={f.smtp_password_set ? "•••• salvata" : "Password"}
                        value={f.smtp_password || ""}
                        onChange={(e) => set("smtp_password", e.target.value)}
                        data-testid="com-smtp-pass" />
                </div>
                <div className="md:col-span-2">
                    <Label>Mittente (display name)</Label>
                    <Input placeholder="Assicurazioni Schiantarelli"
                        value={f.smtp_from || ""}
                        onChange={(e) => set("smtp_from", e.target.value)}
                        data-testid="com-smtp-from" />
                </div>
                {/* Campi avanzati solo per "SMTP personalizzato" */}
                {provider === "smtp" && (
                    <>
                        <div>
                            <Label>Server SMTP <span className="text-rose-500">*</span></Label>
                            <Input placeholder="smtp.example.com"
                                value={f.smtp_host || ""}
                                onChange={(e) => set("smtp_host", e.target.value)}
                                data-testid="com-smtp-host" />
                        </div>
                        <div>
                            <Label>Porta</Label>
                            <Input type="number" placeholder="587"
                                value={f.smtp_port ?? ""}
                                onChange={(e) => set("smtp_port", parseInt(e.target.value, 10) || null)}
                                data-testid="com-smtp-port" />
                        </div>
                        <div className="md:col-span-2 flex items-center">
                            <label className="flex items-center gap-2 text-sm cursor-pointer">
                                <input type="checkbox"
                                    checked={!!f.smtp_use_tls}
                                    onChange={(e) => set("smtp_use_tls", e.target.checked)}
                                    data-testid="com-smtp-tls" />
                                Usa STARTTLS (porta 587) — disabilita solo per SSL su porta 465
                            </label>
                        </div>
                    </>
                )}
            </div>

            {/* Test invio inline */}
            <div className="mt-5 pt-4 border-t border-slate-100">
                <Label className="text-xs uppercase tracking-wide text-slate-500 font-semibold">Test invio</Label>
                <div className="flex flex-col sm:flex-row gap-2 mt-1.5">
                    <Input
                        placeholder={`Invia email di test a… (vuoto = ${f.smtp_user || "tua email"})`}
                        value={testDest}
                        onChange={(e) => setTestDest(e.target.value)}
                        data-testid="com-test-dest"
                        className="flex-1"
                    />
                    <Button
                        onClick={inviaTest}
                        disabled={testing}
                        variant="outline"
                        className="border-slate-300"
                        data-testid="com-test-invia"
                    >
                        {testing ? "Invio…" : "✈ Invia test"}
                    </Button>
                </div>
            </div>
        </section>
    );
}


const IMAP_PRESETS = {
    google: { imap_host: "imap.gmail.com", imap_port: 993, imap_use_ssl: true },
    microsoft: { imap_host: "outlook.office365.com", imap_port: 993, imap_use_ssl: true },
    imap: {},
};

function ImapSection({ f, set, onSet }) {
    const [provider, setProvider] = useState(_detectEmailProvider(f.imap_host || f.smtp_host));
    const [testing, setTesting] = useState(false);
    const [risultato, setRisultato] = useState(null);
    const attivo = !!(f.imap_host && f.imap_user && (f.imap_password_set || f.imap_password));

    const cambiaProvider = (p) => {
        setProvider(p);
        const preset = IMAP_PRESETS[p] || {};
        onSet((prev) => ({ ...prev, ...preset }));
    };

    const copiaSMTP = () => {
        // shortcut: usa email/password SMTP anche per IMAP (lo stesso account su Gmail/M365)
        onSet((prev) => ({
            ...prev,
            imap_user: prev.smtp_user || prev.imap_user,
            imap_password: prev.smtp_password === "••••••••" ? prev.imap_password : prev.smtp_password,
        }));
        toast.info("Account SMTP copiato in IMAP. Salva e poi testa.");
    };

    const testConnessione = async () => {
        setTesting(true); setRisultato(null);
        try {
            // salva prima eventuali modifiche pendenti
            const payload = { ...f };
            if (payload.smtp_password === "••••••••") delete payload.smtp_password;
            if (payload.imap_password === "••••••••") delete payload.imap_password;
            if (payload.twilio_auth_token === "••••••••") delete payload.twilio_auth_token;
            await api.put("/librerie/comunicazioni", payload);
            const r = await api.post("/librerie/comunicazioni/test-imap");
            setRisultato(r.data);
            toast.success(`IMAP OK: ${r.data.messaggi_totali} messaggi totali nella cartella ${r.data.folder}`);
        } catch (e) {
            const msg = e.response?.data?.detail || "Errore connessione IMAP";
            setRisultato({ error: msg });
            toast.error(msg);
        }
        setTesting(false);
    };

    return (
        <section data-testid="lib-com-imap" className="border border-slate-200 rounded-lg p-4 bg-white">
            <div className="flex items-start gap-3 mb-3">
                <div className="bg-violet-100 text-violet-700 p-2 rounded-md mt-0.5">
                    <Mail size={18} />
                </div>
                <div className="flex-1">
                    <div className="flex items-center gap-2 flex-wrap">
                        <h4 className="text-base font-semibold text-slate-800">Posta in arrivo — IMAP</h4>
                        {attivo && (
                            <span className="inline-flex items-center gap-1 text-[11px] px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200">
                                <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" /> Attivo
                            </span>
                        )}
                        {risultato?.ok && (
                            <span className="inline-flex items-center gap-1 text-[11px] px-2 py-0.5 rounded-full bg-sky-50 text-sky-700 border border-sky-200">
                                ✓ Connesso ({risultato.messaggi_totali} msg)
                            </span>
                        )}
                        {/* CTA: attiva subito IMAP usando stesso account SMTP */}
                        {f.smtp_user && (f.smtp_user === f.imap_user || !f.imap_user) && !attivo && (
                            <Button
                                type="button"
                                size="sm"
                                onClick={copiaSMTP}
                                className="ml-auto bg-emerald-600 hover:bg-emerald-700 text-white"
                                data-testid="com-imap-attiva-smtp"
                            >
                                <Mail size={12} className="mr-1" />Attiva con email SMTP ({f.smtp_user})
                            </Button>
                        )}
                    </div>
                    <p className="text-xs text-slate-500 mt-1">
                        Legge la cassetta condivisa <strong>assicurazioni@…</strong> e <strong>smista automaticamente</strong> ogni email in base all'alias destinatario: la posta inviata a un alias personale (es. <em>alessia.balzarolo@…</em>) sarà visibile solo a quel collaboratore.
                    </p>
                </div>
            </div>

            <div className="mb-4">
                <Label className="text-xs uppercase tracking-wide text-slate-500 font-semibold">Provider</Label>
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 mt-1.5">
                    {[
                        { v: "google", l: "Google (Gmail / Workspace)" },
                        { v: "microsoft", l: "Microsoft (Outlook / Office 365)" },
                        { v: "imap", l: "IMAP personalizzato" },
                    ].map((p) => (
                        <button
                            key={p.v}
                            type="button"
                            onClick={() => cambiaProvider(p.v)}
                            className={`px-3 py-2.5 text-sm rounded-md border transition-all ${
                                provider === p.v
                                    ? "border-violet-500 ring-2 ring-violet-200 bg-violet-50 text-violet-900 font-medium"
                                    : "border-slate-200 bg-white text-slate-700 hover:border-slate-300"
                            }`}
                            data-testid={`com-imap-provider-${p.v}`}
                        >
                            {p.l}
                        </button>
                    ))}
                </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <div>
                    <Label>Indirizzo email (cassetta principale) <span className="text-rose-500">*</span></Label>
                    <Input placeholder="assicurazioni@schiantarelli.it"
                        value={f.imap_user || ""}
                        onChange={(e) => set("imap_user", e.target.value)}
                        data-testid="com-imap-user" />
                </div>
                <div>
                    <Label>Password app <span className="text-rose-500">*</span></Label>
                    <Input type="password"
                        placeholder={f.imap_password_set ? "•••• salvata" : "App Password"}
                        value={f.imap_password || ""}
                        onChange={(e) => set("imap_password", e.target.value)}
                        data-testid="com-imap-pass" />
                </div>
                <div>
                    <Label>Cartella</Label>
                    <Input placeholder="INBOX" value={f.imap_folder || "INBOX"}
                        onChange={(e) => set("imap_folder", e.target.value || "INBOX")}
                        data-testid="com-imap-folder" />
                </div>
                <div className="flex items-end">
                    <label className="flex items-center gap-2 text-sm cursor-pointer">
                        <input type="checkbox"
                            checked={f.imap_use_ssl !== false}
                            onChange={(e) => set("imap_use_ssl", e.target.checked)}
                            data-testid="com-imap-ssl" />
                        Usa SSL (porta 993, consigliato)
                    </label>
                </div>
                {provider === "imap" && (
                    <>
                        <div>
                            <Label>Server IMAP</Label>
                            <Input placeholder="imap.example.com"
                                value={f.imap_host || ""}
                                onChange={(e) => set("imap_host", e.target.value)}
                                data-testid="com-imap-host" />
                        </div>
                        <div>
                            <Label>Porta</Label>
                            <Input type="number" placeholder="993"
                                value={f.imap_port ?? ""}
                                onChange={(e) => set("imap_port", parseInt(e.target.value, 10) || null)}
                                data-testid="com-imap-port" />
                        </div>
                    </>
                )}
            </div>

            <div className="mt-4 pt-3 border-t border-slate-100 flex flex-wrap gap-2">
                <Button onClick={testConnessione} disabled={testing}
                    className="bg-violet-700 hover:bg-violet-800"
                    data-testid="com-imap-test">
                    {testing ? "Connessione…" : "🔌 Test connessione IMAP"}
                </Button>
                <Button onClick={copiaSMTP} variant="outline" size="sm" data-testid="com-imap-copia-smtp">
                    Usa stesso account SMTP
                </Button>
            </div>

            {/* POLLER: avvio/stop scheduler smistamento email */}
            <ImapPollerControl />

            {risultato?.error && (
                <div className="mt-3 p-3 bg-rose-50 border border-rose-200 rounded text-xs text-rose-900">
                    <strong>Errore:</strong> {risultato.error}
                </div>
            )}
            {risultato?.ok && risultato.ultimi?.length > 0 && (
                <div className="mt-3 p-3 bg-slate-50 border border-slate-200 rounded text-xs">
                    <div className="font-semibold text-slate-700 mb-2">Anteprima ultime {risultato.ultimi.length} email</div>
                    <ul className="space-y-1.5">
                        {risultato.ultimi.map((m, i) => (
                            <li key={i} className="text-slate-700">
                                <div className="font-medium truncate">{m.subject || "(senza oggetto)"}</div>
                                <div className="text-[10px] text-slate-500">Da: {m.from} · A: {m.to} · {m.date}</div>
                            </li>
                        ))}
                    </ul>
                </div>
            )}
        </section>
    );
}


function ImapPollerControl() {
    const [s, setS] = useState(null);
    const [busy, setBusy] = useState(false);
    const [minutes, setMinutes] = useState(5);

    const refresh = async () => {
        try {
            const r = await api.get("/email/poller/status");
            setS(r.data);
            if (r.data.minutes) setMinutes(r.data.minutes);
        } catch (e) { /* admin only */ }
    };
    useEffect(() => { refresh(); const t = setInterval(refresh, 8000); return () => clearInterval(t); }, []);

    const start = async () => {
        setBusy(true);
        try {
            await api.post("/email/poller/start", { minutes });
            toast.success(`Poller IMAP avviato (ogni ${minutes} min)`);
            refresh();
        } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
        setBusy(false);
    };
    const stop = async () => {
        setBusy(true);
        try {
            await api.post("/email/poller/stop");
            toast.success("Poller IMAP fermato");
            refresh();
        } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
        setBusy(false);
    };
    const runNow = async () => {
        setBusy(true);
        try {
            const r = await api.post("/email/poller/run-now");
            if (r.data.ok) {
                toast.success(`Polling completato: ${r.data.nuovi || 0} nuove · ${r.data.saltati || 0} già presenti`);
            } else {
                toast.error(r.data.errore || "Errore polling");
            }
            refresh();
        } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
        setBusy(false);
    };

    if (!s) return null;
    return (
        <div className="mt-4 p-3 bg-violet-50/40 border border-violet-200 rounded-md" data-testid="imap-poller-ctrl">
            <div className="flex flex-wrap items-center gap-3">
                <div className="flex items-center gap-2">
                    <span className={`inline-block w-2 h-2 rounded-full ${s.running ? "bg-emerald-500 animate-pulse" : "bg-slate-300"}`} />
                    <span className="text-sm font-semibold text-slate-800">
                        Smistamento automatico email: {s.running ? "ATTIVO" : "FERMO"}
                    </span>
                </div>
                <div className="flex items-center gap-1.5 ml-auto">
                    <Label className="text-xs whitespace-nowrap">Frequenza</Label>
                    <Input type="number" min={1} max={60} value={minutes}
                        onChange={(e) => setMinutes(parseInt(e.target.value) || 5)}
                        className="w-16 h-8 text-sm" data-testid="poller-minutes" />
                    <span className="text-xs text-slate-500">min</span>
                </div>
                {!s.running ? (
                    <Button size="sm" onClick={start} disabled={busy} className="bg-emerald-600 hover:bg-emerald-700" data-testid="poller-start">
                        ▶ Avvia
                    </Button>
                ) : (
                    <Button size="sm" variant="outline" onClick={stop} disabled={busy} className="border-rose-300 text-rose-700 hover:bg-rose-50" data-testid="poller-stop">
                        ⏸ Ferma
                    </Button>
                )}
                <Button size="sm" variant="outline" onClick={runNow} disabled={busy} data-testid="poller-run-now">
                    ⚡ Esegui ora
                </Button>
            </div>
            {s.last_run && (
                <div className="text-[11px] text-slate-500 mt-2">
                    Ultima esecuzione: {new Date(s.last_run).toLocaleString("it-IT")} · UID processato: {s.last_uid || "—"}
                </div>
            )}
        </div>
    );
}


function ComunicazioniSezione() {
    const [f, setF] = useState(null);
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);
    const [testCanale, setTestCanale] = useState("email");
    const [testDest, setTestDest] = useState("");
    const [testMsg, setTestMsg] = useState("");
    const [testing, setTesting] = useState(false);

    const load = async () => {
        setLoading(true);
        try {
            const r = await api.get("/librerie/comunicazioni");
            setF(r.data);
        } catch (e) {
            toast.error(e.response?.data?.detail || "Errore caricamento");
        }
        setLoading(false);
    };
    useEffect(() => { load(); }, []);

    const set = (k, v) => setF((p) => ({ ...p, [k]: v }));

    const salva = async () => {
        setSaving(true);
        try {
            const payload = { ...f };
            // Non inviare placeholder mascherato (se non modificato)
            if (payload.smtp_password === "••••••••") delete payload.smtp_password;
            if (payload.twilio_auth_token === "••••••••") delete payload.twilio_auth_token;
            const r = await api.put("/librerie/comunicazioni", payload);
            setF(r.data);
            toast.success("Configurazione salvata");
        } catch (e) {
            toast.error(e.response?.data?.detail || "Errore salvataggio");
        }
        setSaving(false);
    };

    const inviaTest = async () => {
        if (!testDest) { toast.error("Destinatario obbligatorio"); return; }
        setTesting(true);
        try {
            const r = await api.post("/librerie/comunicazioni/test", {
                canale: testCanale, destinatario: testDest, messaggio: testMsg || undefined,
            });
            toast.success(`Test ${r.data.canale} inviato a ${r.data.destinatario}`);
        } catch (e) {
            toast.error(e.response?.data?.detail || "Errore invio test");
        }
        setTesting(false);
    };

    if (loading || !f) {
        return <Card className="p-6 border-slate-200">Caricamento…</Card>;
    }
    return (
        <Card className="p-5 border-slate-200 space-y-6" data-testid="lib-comunicazioni">
            <div className="border-b border-slate-200 pb-2">
                <h3 className="text-base font-semibold text-slate-900">Configurazione comunicazioni</h3>
                <p className="text-xs text-slate-500 mt-0.5">
                    Configurazione unica per <strong>Email (SMTP)</strong>, <strong>SMS</strong> e <strong>WhatsApp</strong>.
                    Sarà usata da: Avvisi scadenze, Marketing, Notifiche, Sollecitazioni, Pipeline Email.
                </p>
            </div>

            {/* EMAIL — Provider con preset (Google / Microsoft / SMTP personalizzato) */}
            <EmailSection f={f} set={set} onSet={setF} />

            {/* IMAP — Ricezione email + smistamento per alias */}
            <ImapSection f={f} set={set} onSet={setF} />

            {/* TWILIO SMS + WHATSAPP */}
            <section data-testid="lib-com-twilio">
                <div className="flex items-center gap-2 mb-3">
                    <Building2 size={16} className="text-rose-600" />
                    <h4 className="text-sm font-semibold text-slate-800">SMS &amp; WhatsApp — Twilio</h4>
                </div>
                <div className="text-[11px] text-slate-500 mb-3">
                    Provider consigliato per SMS + WhatsApp Business.
                    {" "}<a href="https://console.twilio.com/" target="_blank" rel="noreferrer"
                        className="text-sky-700 underline">Apri console Twilio</a>{" "}
                    per ottenere SID/Token e i numeri verificati.
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    <div>
                        <Label>Account SID</Label>
                        <Input placeholder="ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
                            value={f.twilio_account_sid || ""}
                            onChange={(e) => set("twilio_account_sid", e.target.value)}
                            data-testid="com-twilio-sid" />
                    </div>
                    <div>
                        <Label>Auth Token</Label>
                        <Input type="password"
                            placeholder={f.twilio_auth_token_set ? "Token salvato (modifica per cambiare)" : "Token"}
                            value={f.twilio_auth_token || ""}
                            onChange={(e) => set("twilio_auth_token", e.target.value)}
                            data-testid="com-twilio-token" />
                    </div>
                    <div>
                        <Label>Numero SMS mittente</Label>
                        <Input placeholder="+39…"
                            value={f.twilio_sms_from || ""}
                            onChange={(e) => set("twilio_sms_from", e.target.value)}
                            data-testid="com-twilio-sms" />
                    </div>
                    <div>
                        <Label>Numero WhatsApp Business</Label>
                        <Input placeholder="whatsapp:+14155238886"
                            value={f.twilio_whatsapp_from || ""}
                            onChange={(e) => set("twilio_whatsapp_from", e.target.value)}
                            data-testid="com-twilio-wa" />
                    </div>
                </div>
            </section>

            {/* SAVE + TEST */}
            <div className="flex flex-wrap items-center justify-between gap-3 pt-2 border-t border-slate-200">
                <Button onClick={salva} disabled={saving}
                    className="bg-sky-700 hover:bg-sky-800"
                    data-testid="com-salva">
                    {saving ? "Salvataggio…" : "Salva configurazione"}
                </Button>
            </div>

            <section className="bg-slate-50 rounded-md p-3 border border-slate-200">
                <h4 className="text-sm font-semibold text-slate-800 mb-2">Invio di prova</h4>
                <div className="grid grid-cols-1 md:grid-cols-4 gap-2">
                    <Select value={testCanale} onValueChange={setTestCanale}>
                        <SelectTrigger data-testid="com-test-canale"><SelectValue /></SelectTrigger>
                        <SelectContent>
                            <SelectItem value="email">Email</SelectItem>
                            <SelectItem value="sms">SMS</SelectItem>
                            <SelectItem value="whatsapp">WhatsApp</SelectItem>
                        </SelectContent>
                    </Select>
                    <Input placeholder={testCanale === "email" ? "email@destinatario.it" : "+39…"}
                        value={testDest} onChange={(e) => setTestDest(e.target.value)}
                        data-testid="com-test-dest" />
                    <Input placeholder="Messaggio (opzionale)"
                        value={testMsg} onChange={(e) => setTestMsg(e.target.value)}
                        data-testid="com-test-msg" />
                    <Button onClick={inviaTest} disabled={testing}
                        className="bg-emerald-600 hover:bg-emerald-700"
                        data-testid="com-test-invia">
                        {testing ? "Invio…" : "Invia test"}
                    </Button>
                </div>
            </section>
        </Card>
    );
}


function VociRicorsiveSezione() {
    const [items, setItems] = useState(null);
    const [collabs, setCollabs] = useState([]);
    const [open, setOpen] = useState(false);
    const [editing, setEditing] = useState(null);

    const load = () => {
        api.get("/voci-ricorsive-collab").then((r) => setItems(r.data || []));
    };
    useEffect(() => {
        load();
        api.get("/auth/users").then((r) => {
            setCollabs((r.data || []).filter(
                (u) => ["collaboratore", "dipendente"].includes(u.role) && u.attivo !== false,
            ));
        });
    }, []);

    const elimina = async (r) => {
        if (!window.confirm(
            `Eliminare la regola "${r.causale}"?\nVerranno cancellate anche le voci non ancora pagate generate da questa regola.`,
        )) return;
        try {
            await api.delete(`/voci-ricorsive-collab/${r.id}`, { params: { elimina_voci_non_pagate: true } });
            toast.success("Regola eliminata");
            load();
        } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
    };
    const apriEdit = (r) => { setEditing(r); setOpen(true); };
    const apriNuovo = () => { setEditing(null); setOpen(true); };

    return (
        <Card className="p-4 border-slate-200" data-testid="lib-voci-ricorsive">
            <div className="flex items-start justify-between mb-3">
                <div>
                    <h2 className="font-semibold text-slate-900">
                        <RotateCw size={14} className="inline mr-1.5 text-fuchsia-600" />
                        Voci ricorsive collaboratori
                    </h2>
                    <p className="text-xs text-slate-500 mt-1 max-w-2xl">
                        Bonus o trattenute periodiche (mensili/annuali) che vengono generate
                        automaticamente nell'estratto conto del collaboratore alle date previste.
                        L'importo è positivo (bonus) o negativo (trattenuta).
                    </p>
                </div>
                <Button onClick={apriNuovo} className="bg-fuchsia-700 hover:bg-fuchsia-800" data-testid="vr-new">
                    <Plus size={14} className="mr-1" /> Nuova regola
                </Button>
            </div>
            {items === null ? <Loading /> : items.length === 0 ? (
                <Empty message="Nessuna regola ricorsiva. Aggiungine una per automatizzare bonus/trattenute." />
            ) : (
                <table className="tbl w-full">
                    <thead>
                        <tr>
                            <th>Collaboratore</th>
                            <th>Causale</th>
                            <th>Periodicità</th>
                            <th>Quando</th>
                            <th>Da → A</th>
                            <th className="text-right">Importo €</th>
                            <th>Stato</th>
                            <th className="w-24"></th>
                        </tr>
                    </thead>
                    <tbody>
                        {items.map((r) => (
                            <tr key={r.id} data-testid={`vr-row-${r.id}`}>
                                <td className="font-medium">{r.collaboratore_nome}</td>
                                <td>{r.causale}</td>
                                <td className="text-xs">
                                    <span className={`badge ${r.periodicita === "mensile" ? "badge-info" : "badge-warning"}`}>
                                        {r.periodicita}
                                    </span>
                                </td>
                                <td className="text-xs num">
                                    {r.periodicita === "mensile"
                                        ? `giorno ${r.giorno_mese} di ogni mese`
                                        : `${r.giorno_mese}/${r.mese_anno || "?"} di ogni anno`}
                                </td>
                                <td className="text-xs num">
                                    {r.data_inizio} → {r.data_fine || "—"}
                                </td>
                                <td className={`num text-right font-semibold ${r.importo >= 0 ? "text-emerald-700" : "text-rose-700"}`}>
                                    {r.importo >= 0 ? "+" : ""}{r.importo.toFixed(2)}
                                </td>
                                <td>
                                    {r.attiva
                                        ? <span className="badge badge-success">attiva</span>
                                        : <span className="badge badge-warning">disattiva</span>}
                                </td>
                                <td className="text-right">
                                    <button
                                        onClick={() => apriEdit(r)}
                                        className="inline-flex items-center justify-center h-7 w-7 rounded border border-slate-200 hover:bg-slate-100 mr-1"
                                        title="Modifica" data-testid={`vr-edit-${r.id}`}
                                    >
                                        <Pencil size={12} />
                                    </button>
                                    <button
                                        onClick={() => elimina(r)}
                                        className="inline-flex items-center justify-center h-7 w-7 rounded border border-rose-200 hover:bg-rose-50 text-rose-600"
                                        title="Elimina" data-testid={`vr-del-${r.id}`}
                                    >
                                        <Trash2 size={12} />
                                    </button>
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            )}
            {open && (
                <VoceRicorsivaDialog
                    voce={editing}
                    collabs={collabs}
                    onClose={(refresh) => {
                        setOpen(false); setEditing(null);
                        if (refresh) load();
                    }}
                />
            )}
        </Card>
    );
}

function VoceRicorsivaDialog({ voce, collabs, onClose }) {
    const today = new Date().toISOString().slice(0, 10);
    const [f, setF] = useState(() => voce ? {
        collaboratore_id: voce.collaboratore_id,
        causale: voce.causale,
        importo: String(voce.importo),
        periodicita: voce.periodicita,
        giorno_mese: voce.giorno_mese || 1,
        mese_anno: voce.mese_anno || 1,
        data_inizio: voce.data_inizio,
        data_fine: voce.data_fine || "",
        note: voce.note || "",
        attiva: voce.attiva !== false,
    } : {
        collaboratore_id: "",
        causale: "",
        importo: "",
        periodicita: "mensile",
        giorno_mese: 1,
        mese_anno: 1,
        data_inizio: today,
        data_fine: "",
        note: "",
        attiva: true,
    });
    const [saving, setSaving] = useState(false);
    const set = (k, v) => setF((p) => ({ ...p, [k]: v }));

    const save = async () => {
        if (!f.collaboratore_id) { toast.error("Seleziona il collaboratore (o 'Tutti')"); return; }
        if (!f.causale) { toast.error("Inserisci la causale"); return; }
        const imp = parseFloat(f.importo);
        if (isNaN(imp) || imp === 0) { toast.error("Importo deve essere ≠ 0"); return; }
        setSaving(true);
        try {
            const body = {
                collaboratore_id: f.collaboratore_id,
                causale: f.causale,
                importo: imp,
                periodicita: f.periodicita,
                giorno_mese: parseInt(f.giorno_mese, 10) || 1,
                mese_anno: f.periodicita === "annuale" ? (parseInt(f.mese_anno, 10) || 1) : null,
                data_inizio: f.data_inizio,
                data_fine: f.data_fine || null,
                note: f.note || null,
                attiva: !!f.attiva,
            };
            if (voce) {
                await api.put(`/voci-ricorsive-collab/${voce.id}`, body);
                toast.success("Regola aggiornata");
            } else {
                const r = await api.post("/voci-ricorsive-collab", body);
                toast.success(`Regola creata · ${r.data.voci_generate || 0} voci generate`);
            }
            onClose(true);
        } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
        finally { setSaving(false); }
    };

    return (
        <Dialog open onOpenChange={(o) => !o && onClose(false)}>
            <DialogContent className="max-w-lg" data-testid="vr-dialog">
                <DialogHeader>
                    <DialogTitle>{voce ? "Modifica regola ricorsiva" : "Nuova regola ricorsiva"}</DialogTitle>
                </DialogHeader>
                <div className="space-y-3 py-2">
                    <div>
                        <Label>Collaboratore *</Label>
                        <Select value={f.collaboratore_id} onValueChange={(v) => set("collaboratore_id", v)}>
                            <SelectTrigger data-testid="vr-collab"><SelectValue placeholder="Seleziona" /></SelectTrigger>
                            <SelectContent>
                                <SelectItem value="__all__">Tutti i collaboratori (broadcast)</SelectItem>
                                {collabs.map((c) => (
                                    <SelectItem key={c.id} value={c.id}>{c.name || c.email}</SelectItem>
                                ))}
                            </SelectContent>
                        </Select>
                    </div>
                    <div className="grid grid-cols-2 gap-3">
                        <div className="col-span-1">
                            <Label>Causale *</Label>
                            <Input
                                placeholder="es. Bonus presenza, Trattenuta auto..."
                                value={f.causale}
                                onChange={(e) => set("causale", e.target.value)}
                                data-testid="vr-causale"
                            />
                        </div>
                        <div className="col-span-1">
                            <Label>Importo € *</Label>
                            <Input
                                type="number" step="0.01"
                                placeholder="+100 bonus / -50 trattenuta"
                                value={f.importo}
                                onChange={(e) => set("importo", e.target.value)}
                                data-testid="vr-importo"
                            />
                        </div>
                    </div>
                    <div className="grid grid-cols-3 gap-3">
                        <div>
                            <Label>Periodicità</Label>
                            <Select value={f.periodicita} onValueChange={(v) => set("periodicita", v)}>
                                <SelectTrigger data-testid="vr-period"><SelectValue /></SelectTrigger>
                                <SelectContent>
                                    <SelectItem value="mensile">Mensile</SelectItem>
                                    <SelectItem value="annuale">Annuale</SelectItem>
                                </SelectContent>
                            </Select>
                        </div>
                        <div>
                            <Label>Giorno (1-28)</Label>
                            <Input
                                type="number" min="1" max="28"
                                value={f.giorno_mese}
                                onChange={(e) => set("giorno_mese", e.target.value)}
                                data-testid="vr-giorno"
                            />
                        </div>
                        {f.periodicita === "annuale" && (
                            <div>
                                <Label>Mese (1-12)</Label>
                                <Input
                                    type="number" min="1" max="12"
                                    value={f.mese_anno}
                                    onChange={(e) => set("mese_anno", e.target.value)}
                                    data-testid="vr-mese"
                                />
                            </div>
                        )}
                    </div>
                    <div className="grid grid-cols-2 gap-3">
                        <div>
                            <Label>Da *</Label>
                            <Input
                                type="date" value={f.data_inizio}
                                onChange={(e) => set("data_inizio", e.target.value)}
                                data-testid="vr-dal"
                            />
                        </div>
                        <div>
                            <Label>A (opzionale)</Label>
                            <Input
                                type="date" value={f.data_fine}
                                onChange={(e) => set("data_fine", e.target.value)}
                                data-testid="vr-al"
                            />
                        </div>
                    </div>
                    <div>
                        <Label>Note (opzionali)</Label>
                        <Input value={f.note} onChange={(e) => set("note", e.target.value)} />
                    </div>
                    <label className="flex items-center gap-2 text-sm">
                        <input
                            type="checkbox" checked={f.attiva}
                            onChange={(e) => set("attiva", e.target.checked)}
                            data-testid="vr-attiva"
                        />
                        Regola attiva (genera voci automaticamente)
                    </label>
                    <div className="text-[11px] text-fuchsia-700 bg-fuchsia-50 border border-fuchsia-200 rounded p-2">
                        Le voci verranno generate automaticamente nell'estratto conto del
                        collaboratore alle date previste, fino ad oggi.
                    </div>
                </div>
                <DialogFooter>
                    <Button variant="outline" onClick={() => onClose(false)}>Annulla</Button>
                    <Button
                        onClick={save} disabled={saving}
                        className="bg-fuchsia-700 hover:bg-fuchsia-800"
                        data-testid="vr-save"
                    >
                        {saving ? "Salvataggio…" : (voce ? "Aggiorna" : "Crea regola")}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}


// ============================================================
// EMAIL ALIASES — gestione lista alias per collaboratore (UtenteForm)
// ============================================================
function EmailAliasesEditor({ value, onChange, mainEmail }) {
    const [newAlias, setNewAlias] = useState("");
    const add = () => {
        const a = newAlias.trim().toLowerCase();
        if (!a) return;
        if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(a)) {
            toast.error("Formato email non valido");
            return;
        }
        if ((value || []).includes(a)) {
            toast.info("Alias già presente");
            return;
        }
        onChange([...(value || []), a]);
        setNewAlias("");
    };
    const remove = (a) => onChange((value || []).filter((x) => x !== a));
    const usaMain = () => {
        const e = (mainEmail || "").toLowerCase().trim();
        if (!e) { toast.error("Email principale non impostata"); return; }
        if ((value || []).includes(e)) { toast.info("Email principale già negli alias"); return; }
        onChange([...(value || []), e]);
        toast.success("Email principale aggiunta come alias");
    };
    const mainAlreadyAlias = mainEmail && (value || []).includes((mainEmail || "").toLowerCase().trim());
    return (
        <div className="mt-2 p-3 bg-violet-50/40 border border-violet-200 rounded-md">
            <Label className="text-xs font-semibold text-violet-900 uppercase tracking-wide">
                Alias email (smistamento Posta in arrivo)
            </Label>
            <div className="text-[11px] text-slate-600 mt-1 mb-2">
                Indirizzi a cui può essere indirizzata la posta. Le email destinate a uno di
                questi alias verranno smistate automaticamente nella casella personale del
                collaboratore. Più collaboratori possono condividere lo stesso alias (es. <code>sinistri@</code>).
            </div>
            <div className="flex flex-wrap gap-1.5 mb-2">
                {(value || []).map((a) => (
                    <span key={a} className="inline-flex items-center gap-1.5 px-2 py-0.5 bg-white border border-violet-300 rounded-md text-xs">
                        <Mail size={11} className="text-violet-700" />
                        {a}
                        <button type="button" onClick={() => remove(a)} className="text-rose-500 hover:text-rose-700 ml-1" data-testid={`alias-rm-${a}`}>
                            <Trash2 size={11} />
                        </button>
                    </span>
                ))}
                {(value || []).length === 0 && (
                    <span className="text-xs text-slate-400 italic">Nessun alias configurato</span>
                )}
            </div>
            <div className="flex gap-1.5">
                <Input
                    type="email"
                    placeholder="es. alessia.balzarolo@schiantarelli.it"
                    value={newAlias}
                    onChange={(e) => setNewAlias(e.target.value)}
                    onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); add(); } }}
                    className="h-8 text-sm"
                    data-testid="alias-new-input"
                />
                <Button type="button" size="sm" onClick={add} className="bg-violet-700 hover:bg-violet-800" data-testid="alias-add-btn">
                    <Plus size={12} className="mr-1" />Aggiungi
                </Button>
                {mainEmail && !mainAlreadyAlias && (
                    <Button type="button" size="sm" variant="outline" onClick={usaMain} title={`Usa ${mainEmail} come alias`} data-testid="alias-use-main">
                        <Mail size={12} className="mr-1" />Usa email principale
                    </Button>
                )}
            </div>
        </div>
    );
}


// ============================================================
// GESTIONI MODELLI — libreria template editabili
// ============================================================
const MODELLI_TIPI = [
    { v: "email", label: "Email" },
    { v: "whatsapp", label: "WhatsApp" },
    { v: "sms", label: "SMS" },
    { v: "pdf_avviso", label: "PDF · Avviso scadenza" },
    { v: "pdf_lettera_abbuono", label: "PDF · Lettera di Abbuono" },
    { v: "pdf_brogliaccio", label: "PDF · Brogliaccio" },
    { v: "pdf_diagnosi", label: "PDF · Diagnosi assicurativa" },
    { v: "pdf_prima_nota", label: "PDF · Prima Nota" },
    { v: "pdf_altro", label: "PDF · Altro" },
];

const PLACEHOLDERS_DOC = [
    { k: "cliente_nome", desc: "Nome contraente" },
    { k: "cliente_indirizzo", desc: "Indirizzo del cliente" },
    { k: "cliente_comune", desc: "Comune" },
    { k: "cliente_cap", desc: "CAP" },
    { k: "cliente_provincia", desc: "Provincia" },
    { k: "azienda_nome", desc: "Ragione sociale agenzia" },
    { k: "azienda_iban", desc: "IBAN agenzia" },
    { k: "azienda_telefono", desc: "Telefono agenzia" },
    { k: "azienda_email", desc: "Email agenzia" },
    { k: "totale", desc: "Importo totale (€)" },
    { k: "numero_titoli", desc: "Numero titoli" },
    { k: "data_oggi", desc: "Data odierna (gg-mm-aaaa)" },
    { k: "numero_polizza", desc: "Numero polizza (singola)" },
    { k: "numero_titolo", desc: "Numero titolo" },
    { k: "scadenza", desc: "Data scadenza" },
    { k: "importo_abbuono", desc: "Importo abbuono (€)" },
];

function ModelliSezione() {
    const [items, setItems] = useState(null);
    const [filtroTipo, setFiltroTipo] = useState("all");
    const [editing, setEditing] = useState(null);
    const [open, setOpen] = useState(false);
    const [q, setQ] = useState("");

    const load = () => api.get("/librerie/modelli").then((r) => setItems(r.data || []));
    useEffect(() => { load(); }, []);

    const filtrati = (items || [])
        .filter((m) => filtroTipo === "all" || m.tipo === filtroTipo)
        .filter((m) => !q || (m.nome || "").toLowerCase().includes(q.toLowerCase()));

    const elimina = async (m) => {
        if (!window.confirm(`Eliminare il modello "${m.nome}"?`)) return;
        try {
            await api.delete(`/librerie/modelli/${m.id}`);
            toast.success("Modello eliminato"); load();
        } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
    };

    return (
        <Card className="p-4 border-slate-200" data-testid="lib-modelli">
            <div className="flex flex-wrap items-center gap-3 mb-3">
                <div>
                    <h2 className="font-semibold text-slate-900 flex items-center gap-2">
                        <FileText size={16} className="text-violet-700" />
                        Gestioni Modelli
                    </h2>
                    <p className="text-xs text-slate-500 mt-0.5 max-w-2xl">
                        Personalizza il testo (HTML/markdown) usato per Email, WhatsApp, SMS e PDF.
                        Usa <code>{"{placeholder}"}</code> per inserire dati dinamici.
                    </p>
                </div>
                <div className="ml-auto flex items-center gap-2">
                    <div className="relative">
                        <Search size={12} className="absolute left-2 top-1/2 -translate-y-1/2 text-slate-400" />
                        <Input placeholder="Cerca modello…" value={q}
                            onChange={(e) => setQ(e.target.value)}
                            className="pl-7 h-8 w-48 text-sm"
                            data-testid="modelli-search" />
                    </div>
                    <Select value={filtroTipo} onValueChange={setFiltroTipo}>
                        <SelectTrigger className="w-48 h-8" data-testid="modelli-filter-tipo"><SelectValue /></SelectTrigger>
                        <SelectContent>
                            <SelectItem value="all">Tutti i tipi</SelectItem>
                            {MODELLI_TIPI.map((t) => <SelectItem key={t.v} value={t.v}>{t.label}</SelectItem>)}
                        </SelectContent>
                    </Select>
                    <Button onClick={() => { setEditing(null); setOpen(true); }}
                        className="bg-violet-700 hover:bg-violet-800" data-testid="modelli-new">
                        <Plus size={14} className="mr-1" />Nuovo modello
                    </Button>
                </div>
            </div>

            {items === null ? <Loading /> : filtrati.length === 0 ? (
                <Empty message="Nessun modello. Creane uno per personalizzare le comunicazioni." />
            ) : (
                <table className="tbl w-full">
                    <thead><tr>
                        <th>Tipo</th><th>Nome</th><th>Categoria</th>
                        <th className="text-center">Default</th><th className="text-center">Stato</th>
                        <th>Placeholder</th><th className="w-24"></th>
                    </tr></thead>
                    <tbody>
                        {filtrati.map((m) => (
                            <tr key={m.id} data-testid={`modello-row-${m.id}`}>
                                <td className="text-xs"><span className="badge badge-info">{m.tipo}</span></td>
                                <td className="font-medium">{m.nome}</td>
                                <td className="text-xs text-slate-500">{m.categoria || "—"}</td>
                                <td className="text-center">
                                    {m.default && <span className="badge badge-success">✓ default</span>}
                                </td>
                                <td className="text-center">
                                    {m.attivo
                                        ? <span className="badge badge-success">attivo</span>
                                        : <span className="badge badge-warning">disattivo</span>}
                                </td>
                                <td className="text-[10px] text-slate-500 font-mono">
                                    {(m.placeholders || []).slice(0, 6).map((p) => `{${p}}`).join(" ")}
                                    {(m.placeholders || []).length > 6 ? "…" : ""}
                                </td>
                                <td className="text-right">
                                    <button onClick={() => { setEditing(m); setOpen(true); }}
                                        className="inline-flex items-center justify-center h-7 w-7 rounded border border-slate-200 hover:bg-slate-100 mr-1"
                                        title="Modifica" data-testid={`modello-edit-${m.id}`}>
                                        <Pencil size={12} />
                                    </button>
                                    <button onClick={() => elimina(m)}
                                        className="inline-flex items-center justify-center h-7 w-7 rounded border border-rose-200 hover:bg-rose-50 text-rose-600"
                                        title="Elimina" data-testid={`modello-del-${m.id}`}>
                                        <Trash2 size={12} />
                                    </button>
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            )}

            {open && (
                <ModelloFormDialog
                    editing={editing}
                    onClose={(reload) => { setOpen(false); setEditing(null); if (reload) load(); }}
                />
            )}
        </Card>
    );
}

function ModelloFormDialog({ editing, onClose }) {
    const [f, setF] = useState(editing || {
        tipo: "email", nome: "", oggetto: "", corpo: "", sezioni: [],
        categoria: "", default: false, attivo: true, note: "",
    });
    const [saving, setSaving] = useState(false);
    const isPdf = (f.tipo || "").startsWith("pdf_");
    const isEmail = f.tipo === "email";

    const set = (k, v) => setF((p) => ({ ...p, [k]: v }));

    const insertPlaceholder = (ph) => {
        set("corpo", (f.corpo || "") + `{${ph}}`);
    };

    const save = async () => {
        if (!f.nome?.trim()) { toast.error("Nome obbligatorio"); return; }
        setSaving(true);
        try {
            const payload = {
                tipo: f.tipo, nome: f.nome.trim(),
                oggetto: f.oggetto || null, corpo: f.corpo || "",
                sezioni: f.sezioni || [],
                categoria: f.categoria || null, default: !!f.default,
                attivo: f.attivo !== false, note: f.note || null,
            };
            if (editing?.id) {
                await api.put(`/librerie/modelli/${editing.id}`, payload);
                toast.success("Modello aggiornato");
            } else {
                await api.post("/librerie/modelli", payload);
                toast.success("Modello creato");
            }
            onClose(true);
        } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
        setSaving(false);
    };

    // Gestione sezioni dinamiche (per pdf_avviso e simili)
    const addSezione = () => set("sezioni", [...(f.sezioni || []), {
        ordine: (f.sezioni || []).length + 1, attiva: true, titolo: "", contenuto: "",
    }]);
    const updSezione = (i, k, v) => {
        const arr = [...(f.sezioni || [])];
        arr[i] = { ...arr[i], [k]: v };
        set("sezioni", arr);
    };
    const delSezione = (i) => set("sezioni", (f.sezioni || []).filter((_, idx) => idx !== i));

    return (
        <Dialog open onOpenChange={(o) => !o && onClose(false)}>
            <DialogContent className="max-w-4xl max-h-[90vh] overflow-y-auto" data-testid="modello-form">
                <DialogHeader>
                    <DialogTitle>{editing ? "Modifica modello" : "Nuovo modello"}</DialogTitle>
                </DialogHeader>
                <div className="space-y-3">
                    <div className="grid grid-cols-2 gap-3">
                        <div>
                            <Label>Tipo *</Label>
                            <Select value={f.tipo} onValueChange={(v) => set("tipo", v)} disabled={!!editing}>
                                <SelectTrigger data-testid="modello-tipo"><SelectValue /></SelectTrigger>
                                <SelectContent>
                                    {MODELLI_TIPI.map((t) => <SelectItem key={t.v} value={t.v}>{t.label}</SelectItem>)}
                                </SelectContent>
                            </Select>
                        </div>
                        <div>
                            <Label>Nome *</Label>
                            <Input value={f.nome || ""} onChange={(e) => set("nome", e.target.value)} data-testid="modello-nome" />
                        </div>
                        <div>
                            <Label>Categoria</Label>
                            <Input value={f.categoria || ""}
                                placeholder="es. scadenze, marketing, fiscale"
                                onChange={(e) => set("categoria", e.target.value)} data-testid="modello-cat" />
                        </div>
                        <div className="flex items-end gap-4">
                            <label className="flex items-center gap-1.5 text-sm">
                                <input type="checkbox" checked={f.default} onChange={(e) => set("default", e.target.checked)} data-testid="modello-default" />
                                Default per questo tipo
                            </label>
                            <label className="flex items-center gap-1.5 text-sm">
                                <input type="checkbox" checked={f.attivo !== false} onChange={(e) => set("attivo", e.target.checked)} data-testid="modello-attivo" />
                                Attivo
                            </label>
                        </div>
                    </div>

                    {(isEmail || isPdf) && (
                        <div>
                            <Label>{isPdf ? "Saluto (es. 'Gentile Cliente,')" : "Oggetto email"}</Label>
                            <Input value={f.oggetto || ""} onChange={(e) => set("oggetto", e.target.value)} data-testid="modello-oggetto" />
                        </div>
                    )}

                    <div>
                        <Label>Corpo del messaggio</Label>
                        <Textarea
                            value={f.corpo || ""} onChange={(e) => set("corpo", e.target.value)}
                            rows={isPdf ? 8 : 6}
                            className="font-mono text-xs"
                            placeholder={isPdf ? "Testo introduttivo del PDF…" : "Testo del messaggio…"}
                            data-testid="modello-corpo"
                        />
                        <div className="text-[10px] text-slate-500 mt-1">
                            Usa <code className="bg-slate-100 px-1 rounded">{"{placeholder}"}</code> per dati dinamici (vedi pulsanti sotto).
                        </div>
                    </div>

                    <div className="bg-slate-50 border border-slate-200 rounded-md p-2">
                        <Label className="text-[11px] uppercase tracking-wider text-slate-500">Inserisci placeholder</Label>
                        <div className="flex flex-wrap gap-1 mt-1.5">
                            {PLACEHOLDERS_DOC.map((p) => (
                                <button key={p.k} type="button" onClick={() => insertPlaceholder(p.k)}
                                    title={p.desc}
                                    className="text-[11px] px-2 py-0.5 rounded border border-slate-300 bg-white hover:bg-sky-50 hover:border-sky-300 font-mono"
                                    data-testid={`ph-${p.k}`}>
                                    {`{${p.k}}`}
                                </button>
                            ))}
                        </div>
                    </div>

                    {isPdf && (
                        <div className="bg-violet-50/40 border border-violet-200 rounded-md p-3">
                            <div className="flex items-center justify-between mb-2">
                                <Label className="text-sm font-semibold text-violet-900">Sezioni dinamiche (callout / blocchi commerciali)</Label>
                                <Button type="button" size="sm" variant="outline" onClick={addSezione} data-testid="sez-add">
                                    <Plus size={12} className="mr-1" />Aggiungi sezione
                                </Button>
                            </div>
                            {(f.sezioni || []).length === 0 && (
                                <div className="text-xs text-slate-500 italic">Nessuna sezione. Aggiungi blocchi opzionali (es. promo Tutela Legale).</div>
                            )}
                            {(f.sezioni || []).map((sez, i) => (
                                <div key={i} className="bg-white border border-violet-200 rounded p-2 mb-2" data-testid={`sez-${i}`}>
                                    <div className="grid grid-cols-12 gap-2 items-start">
                                        <div className="col-span-1">
                                            <Label className="text-[10px]">Ord.</Label>
                                            <Input type="number" value={sez.ordine || i + 1}
                                                onChange={(e) => updSezione(i, "ordine", parseInt(e.target.value) || 0)}
                                                className="h-8" />
                                        </div>
                                        <div className="col-span-9">
                                            <Label className="text-[10px]">Titolo</Label>
                                            <Input value={sez.titolo || ""}
                                                onChange={(e) => updSezione(i, "titolo", e.target.value)}
                                                className="h-8" />
                                        </div>
                                        <div className="col-span-1 flex items-end justify-center">
                                            <label className="flex items-center gap-1 text-[10px] mt-2">
                                                <input type="checkbox" checked={sez.attiva !== false}
                                                    onChange={(e) => updSezione(i, "attiva", e.target.checked)} />
                                                attiva
                                            </label>
                                        </div>
                                        <div className="col-span-1 flex items-end justify-end">
                                            <button type="button" onClick={() => delSezione(i)}
                                                className="h-8 w-8 rounded border border-rose-200 hover:bg-rose-50 text-rose-600 flex items-center justify-center">
                                                <Trash2 size={12} />
                                            </button>
                                        </div>
                                        <div className="col-span-12">
                                            <Label className="text-[10px]">Contenuto</Label>
                                            <Textarea rows={3} value={sez.contenuto || ""}
                                                onChange={(e) => updSezione(i, "contenuto", e.target.value)}
                                                className="font-mono text-xs" />
                                        </div>
                                    </div>
                                </div>
                            ))}
                        </div>
                    )}

                    <div>
                        <Label>Note interne</Label>
                        <Input value={f.note || ""} onChange={(e) => set("note", e.target.value)} placeholder="Promemoria d'uso interno" data-testid="modello-note" />
                    </div>
                </div>
                <DialogFooter>
                    <Button variant="outline" onClick={() => onClose(false)}>Annulla</Button>
                    <Button onClick={save} disabled={saving} className="bg-violet-700 hover:bg-violet-800" data-testid="modello-save">
                        {saving ? "Salvataggio…" : (editing ? "Aggiorna" : "Crea modello")}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}
