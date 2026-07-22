/**
 * PatrimonioTab — Gestione immobili del cliente con mappa Leaflet + CRUD + PDF report.
 * Riusa il pattern di caricamento Leaflet CDN di MappaClienti.
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "@/lib/api";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Home, Plus, Edit, Trash2, MapPin, FileText, Building2, Warehouse, TreePine, Store } from "lucide-react";
import { toast } from "sonner";

// Riuso pattern MappaClienti per caricare Leaflet
function useLeaflet() {
    const [ready, setReady] = useState(!!window.L);
    useEffect(() => {
        if (window.L) { setReady(true); return; }
        const addCss = (href) => {
            if (document.querySelector(`link[href="${href}"]`)) return;
            const l = document.createElement("link");
            l.rel = "stylesheet"; l.href = href; document.head.appendChild(l);
        };
        const addScript = (src) => new Promise((resolve, reject) => {
            const existing = document.querySelector(`script[src="${src}"]`);
            if (existing) { existing.addEventListener("load", resolve); if (existing.dataset.loaded) resolve(); return; }
            const s = document.createElement("script");
            s.src = src; s.async = false;
            s.onload = () => { s.dataset.loaded = "1"; resolve(); };
            s.onerror = reject;
            document.body.appendChild(s);
        });
        addCss("https://unpkg.com/leaflet@1.9.4/dist/leaflet.css");
        addScript("https://unpkg.com/leaflet@1.9.4/dist/leaflet.js").then(() => setReady(true));
    }, []);
    return ready;
}

const TIPI_ICONS = {
    abitativo: Home, commerciale: Store, ufficio: Building2,
    garage: Warehouse, terreno: TreePine, altro: Home,
};

const TIPO_COLORS = {
    abitativo: "#0ea5e9", commerciale: "#f59e0b", ufficio: "#8b5cf6",
    garage: "#64748b", terreno: "#10b981", altro: "#94a3b8",
};

const fmtEur = (v) => v == null ? "—"
    : new Intl.NumberFormat("it-IT", { style: "currency", currency: "EUR" }).format(Number(v) || 0);


export default function PatrimonioTab({ ana, canEdit }) {
    const [immobili, setImmobili] = useState([]);
    const [editing, setEditing] = useState(null);  // ImmobileItem or "new"
    const [loading, setLoading] = useState(true);
    const mapRef = useRef(null);
    const mapDivRef = useRef(null);
    const markersRef = useRef([]);
    const leafletReady = useLeaflet();

    const load = async () => {
        setLoading(true);
        try {
            const r = await api.get(`/anagrafiche/${ana.id}/immobili`);
            setImmobili(r.data || []);
        } catch { setImmobili([]); }
        setLoading(false);
    };

    useEffect(() => { load(); /* eslint-disable-next-line */ }, [ana.id]);

    // Setup mappa
    useEffect(() => {
        if (!leafletReady || !mapDivRef.current || mapRef.current) return;
        const L = window.L;
        const first = immobili.find((i) => i.latitude && i.longitude);
        const center = first ? [first.latitude, first.longitude] : [41.9028, 12.4964];
        const zoom = first ? 13 : 6;
        const map = L.map(mapDivRef.current, { zoomControl: true }).setView(center, zoom);
        L.tileLayer("https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png", {
            attribution: "&copy; OSM &middot; &copy; CARTO", maxZoom: 20,
        }).addTo(map);
        mapRef.current = map;
        return () => {
            if (mapRef.current) { mapRef.current.remove(); mapRef.current = null; }
        };
    }, [leafletReady]);  // eslint-disable-line

    // Redraw markers ogni volta che cambiano immobili
    useEffect(() => {
        if (!mapRef.current || !window.L) return;
        const L = window.L;
        // Rimuovi vecchi
        markersRef.current.forEach((m) => m.remove());
        markersRef.current = [];
        // Aggiungi nuovi
        const geoImm = immobili.filter((i) => i.latitude && i.longitude);
        geoImm.forEach((im) => {
            const color = TIPO_COLORS[im.tipo] || "#0ea5e9";
            const iconHtml = `<div style="background:${color};width:24px;height:24px;border-radius:50%;border:3px solid white;box-shadow:0 2px 6px rgba(0,0,0,.3);"></div>`;
            const icon = L.divIcon({ html: iconHtml, className: "patrimonio-marker", iconSize: [24, 24], iconAnchor: [12, 12] });
            const m = L.marker([im.latitude, im.longitude], { icon }).addTo(mapRef.current);
            m.bindPopup(`
                <div style="font-family:system-ui;font-size:12px">
                    <b>${im.tipo.charAt(0).toUpperCase() + im.tipo.slice(1)}</b><br/>
                    ${im.indirizzo || ""}<br/>
                    ${im.comune || ""} ${im.provincia || ""}<br/>
                    <span style="color:#059669">Valore: ${fmtEur(im.valore_commerciale)}</span>
                </div>
            `);
            markersRef.current.push(m);
        });
        // Fit bounds
        if (geoImm.length > 0) {
            const bounds = L.latLngBounds(geoImm.map((i) => [i.latitude, i.longitude]));
            mapRef.current.fitBounds(bounds.pad(0.3), { maxZoom: 14 });
        }
    }, [immobili]);

    const del = async (id) => {
        if (!window.confirm("Eliminare l'immobile?")) return;
        try {
            await api.delete(`/anagrafiche/${ana.id}/immobili/${id}`);
            toast.success("Immobile eliminato");
            load();
        } catch (e) { toast.error(e.response?.data?.detail || "Errore"); }
    };

    const geocodeSingle = async (id) => {
        try {
            const r = await api.post(`/anagrafiche/${ana.id}/immobili/${id}/geocode`);
            toast.success(`Localizzato: ${r.data.address || 'OK'}`);
            load();
        } catch (e) { toast.error(e.response?.data?.detail || "Non trovato"); }
    };

    const scaricaPDF = () => {
        const t = localStorage.getItem("token");
        const url = `${process.env.REACT_APP_BACKEND_URL}/api/anagrafiche/${ana.id}/immobili/report.pdf`;
        fetch(url, { headers: { Authorization: `Bearer ${t}` } })
            .then((r) => r.blob())
            .then((b) => {
                const link = document.createElement("a");
                link.href = URL.createObjectURL(b);
                link.download = `patrimonio_${ana.cognome || ana.ragione_sociale || ana.id}.pdf`;
                link.click();
            })
            .catch(() => toast.error("Errore scaricamento PDF"));
    };

    const totali = useMemo(() => {
        return {
            n: immobili.length,
            commerciale: immobili.reduce((s, i) => s + (Number(i.valore_commerciale) || 0), 0),
            ricostruzione: immobili.reduce((s, i) => s + (Number(i.valore_ricostruzione) || 0), 0),
            superficie: immobili.reduce((s, i) => s + (Number(i.superficie_mq) || 0), 0),
        };
    }, [immobili]);

    return (
        <div className="space-y-4 mt-4" data-testid="patrimonio-tab">
            {/* KPI summary */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                <KpiBox label="Immobili" value={totali.n} icon={Home} color="sky" />
                <KpiBox label="Superficie totale" value={`${totali.superficie.toLocaleString("it-IT")} mq`} icon={Building2} color="violet" />
                <KpiBox label="Valore commerciale" value={fmtEur(totali.commerciale)} icon={FileText} color="emerald" />
                <KpiBox label="Valore ricostruzione" value={fmtEur(totali.ricostruzione)} icon={Warehouse} color="amber" />
            </div>

            {/* Mappa + Lista side-by-side */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                {/* Mappa */}
                <Card className="overflow-hidden border-slate-200">
                    <div className="p-2 border-b bg-slate-50 flex items-center justify-between">
                        <div className="text-xs font-medium text-slate-700 flex items-center gap-1">
                            <MapPin size={12} /> Mappa immobili
                        </div>
                        <div className="text-[10px] text-slate-500">
                            {immobili.filter((i) => i.latitude).length} / {immobili.length} geolocalizzati
                        </div>
                    </div>
                    <div ref={mapDivRef} style={{ height: 420, width: "100%" }} data-testid="patrimonio-map" />
                </Card>

                {/* Lista */}
                <Card className="p-4 border-slate-200">
                    <div className="flex items-center justify-between mb-3">
                        <h3 className="font-semibold text-slate-800">Immobili ({immobili.length})</h3>
                        <div className="flex gap-2">
                            {immobili.length > 0 && (
                                <Button size="sm" variant="outline" onClick={scaricaPDF} data-testid="patrimonio-pdf">
                                    <FileText size={13} className="mr-1" /> PDF Report
                                </Button>
                            )}
                            {canEdit && (
                                <Button size="sm" onClick={() => setEditing("new")} className="bg-sky-700 hover:bg-sky-800" data-testid="patrimonio-add">
                                    <Plus size={13} className="mr-1" /> Aggiungi
                                </Button>
                            )}
                        </div>
                    </div>
                    <div className="space-y-2 max-h-[380px] overflow-y-auto">
                        {loading ? <div className="text-center text-slate-400 py-8 text-sm">Caricamento…</div>
                            : immobili.length === 0 ? (
                                <div className="text-center py-8 text-sm text-slate-500 bg-slate-50 rounded border-2 border-dashed border-slate-200">
                                    Nessun immobile registrato.<br />
                                    {canEdit && <span>Clicca "Aggiungi" per iniziare.</span>}
                                </div>
                            ) : immobili.map((im) => {
                                const Icon = TIPI_ICONS[im.tipo] || Home;
                                const valoreAttuale = Number(im.valore_ricostruzione || 0) *
                                    (1 - (Number(im.percentuale_degrado || 0) / 100));
                                return (
                                    <div key={im.id} className="border border-slate-200 rounded p-2.5 hover:border-sky-300 hover:bg-sky-50/30 transition-colors" data-testid={`patrimonio-item-${im.id}`}>
                                        <div className="flex items-start gap-2">
                                            <Icon size={16} className="text-sky-600 mt-0.5" style={{ color: TIPO_COLORS[im.tipo] }} />
                                            <div className="flex-1 min-w-0">
                                                <div className="font-medium text-sm">
                                                    {im.tipo.charAt(0).toUpperCase() + im.tipo.slice(1)}
                                                    {im.categoria_catastale && <span className="ml-2 text-xs text-slate-500 font-mono">({im.categoria_catastale})</span>}
                                                    {im.latitude && <span className="ml-2 text-emerald-600" title="Geolocalizzato">📍</span>}
                                                </div>
                                                <div className="text-xs text-slate-600 truncate">{im.indirizzo}</div>
                                                <div className="text-[11px] text-slate-500">
                                                    {im.comune} {im.provincia && `(${im.provincia})`}
                                                    {im.superficie_mq > 0 && ` · ${im.superficie_mq} mq`}
                                                </div>
                                                <div className="mt-1 flex items-center gap-3 text-[11px]">
                                                    <span className="text-emerald-700">💰 {fmtEur(im.valore_commerciale)}</span>
                                                    {im.valore_ricostruzione > 0 && (
                                                        <span className="text-amber-700" title={`Nuovo: ${fmtEur(im.valore_ricostruzione)} · Degrado: ${im.percentuale_degrado}%`}>
                                                            🔧 attuale {fmtEur(valoreAttuale)}
                                                        </span>
                                                    )}
                                                </div>
                                            </div>
                                            {canEdit && (
                                                <div className="flex flex-col gap-1">
                                                    {!im.latitude && (
                                                        <Button size="sm" variant="ghost" className="h-6 px-1.5" title="Geocodifica"
                                                            onClick={() => geocodeSingle(im.id)}
                                                            data-testid={`patrimonio-geo-${im.id}`}>
                                                            <MapPin size={11} />
                                                        </Button>
                                                    )}
                                                    <Button size="sm" variant="ghost" className="h-6 px-1.5" title="Modifica"
                                                        onClick={() => setEditing(im)}
                                                        data-testid={`patrimonio-edit-${im.id}`}>
                                                        <Edit size={11} />
                                                    </Button>
                                                    <Button size="sm" variant="ghost" className="h-6 px-1.5 text-rose-600 hover:bg-rose-50" title="Elimina"
                                                        onClick={() => del(im.id)}
                                                        data-testid={`patrimonio-del-${im.id}`}>
                                                        <Trash2 size={11} />
                                                    </Button>
                                                </div>
                                            )}
                                        </div>
                                        {im.note && <div className="mt-1 text-[10px] text-slate-500 italic pl-6">{im.note}</div>}
                                    </div>
                                );
                            })}
                    </div>
                </Card>
            </div>

            {editing && (
                <ImmobileDialog
                    aid={ana.id} item={editing === "new" ? null : editing}
                    onClose={() => setEditing(null)}
                    onSaved={() => { setEditing(null); load(); }}
                />
            )}
        </div>
    );
}


function KpiBox({ label, value, icon: Icon, color }) {
    const CLS = {
        sky: "border-sky-200 bg-sky-50 text-sky-700",
        violet: "border-violet-200 bg-violet-50 text-violet-700",
        emerald: "border-emerald-200 bg-emerald-50 text-emerald-700",
        amber: "border-amber-200 bg-amber-50 text-amber-700",
    };
    return (
        <div className={`border rounded p-3 ${CLS[color]}`}>
            <div className="flex items-center gap-2 text-[10px] uppercase tracking-wider font-medium">
                <Icon size={12} /> {label}
            </div>
            <div className="text-lg font-bold mt-1">{value}</div>
        </div>
    );
}


function ImmobileDialog({ aid, item, onClose, onSaved }) {
    const [f, setF] = useState({
        tipo: item?.tipo || "abitativo",
        indirizzo: item?.indirizzo || "",
        comune: item?.comune || "",
        provincia: item?.provincia || "",
        cap: item?.cap || "",
        foglio: item?.foglio || "",
        particella: item?.particella || "",
        sub: item?.sub || "",
        categoria_catastale: item?.categoria_catastale || "",
        rendita_catastale: item?.rendita_catastale || 0,
        valore_commerciale: item?.valore_commerciale || 0,
        superficie_mq: item?.superficie_mq || 0,
        valore_ricostruzione: item?.valore_ricostruzione || 0,
        percentuale_degrado: item?.percentuale_degrado || 0,
        anno_costruzione: item?.anno_costruzione || "",
        titolo: item?.titolo || "proprieta",
        percentuale_proprieta: item?.percentuale_proprieta || 100,
        note: item?.note || "",
    });
    const [busy, setBusy] = useState(false);
    const set = (k, v) => setF((p) => ({ ...p, [k]: v }));

    const save = async () => {
        setBusy(true);
        try {
            const body = { ...f };
            // Casting numeri
            ["rendita_catastale", "valore_commerciale", "superficie_mq", "valore_ricostruzione", "percentuale_degrado", "percentuale_proprieta"].forEach((k) => {
                body[k] = parseFloat(body[k]) || 0;
            });
            if (body.anno_costruzione) body.anno_costruzione = parseInt(body.anno_costruzione) || null;
            else body.anno_costruzione = null;

            if (item) {
                await api.put(`/anagrafiche/${aid}/immobili/${item.id}`, body);
                toast.success("Immobile aggiornato");
            } else {
                await api.post(`/anagrafiche/${aid}/immobili`, body);
                toast.success("Immobile aggiunto (geocoding automatico)");
            }
            onSaved();
        } catch (e) {
            toast.error(e.response?.data?.detail || "Errore");
        } finally { setBusy(false); }
    };

    // Calcolo automatico valore ricostruzione da superficie
    const suggerisciRicostruzione = () => {
        const mq = parseFloat(f.superficie_mq) || 0;
        // Coefficiente medio Italia ~1600 €/mq per abitativo, 1400 commerciale, ecc.
        const coeff = { abitativo: 1600, commerciale: 1400, ufficio: 1500, garage: 900, terreno: 100, altro: 1200 }[f.tipo] || 1500;
        if (mq > 0) {
            set("valore_ricostruzione", Math.round(mq * coeff));
            toast.success(`Suggerito: ${mq} mq × ${coeff} €/mq`);
        } else {
            toast.error("Inserisci prima la superficie");
        }
    };

    return (
        <Dialog open onOpenChange={(o) => !o && onClose()}>
            <DialogContent className="max-w-2xl max-h-[85vh] overflow-y-auto" data-testid="patrimonio-dialog">
                <DialogHeader>
                    <DialogTitle>{item ? "Modifica immobile" : "Nuovo immobile"}</DialogTitle>
                </DialogHeader>
                <div className="grid grid-cols-2 gap-3">
                    <div>
                        <Label className="text-xs">Tipo *</Label>
                        <Select value={f.tipo} onValueChange={(v) => set("tipo", v)}>
                            <SelectTrigger data-testid="pat-tipo"><SelectValue /></SelectTrigger>
                            <SelectContent>
                                <SelectItem value="abitativo">Abitativo</SelectItem>
                                <SelectItem value="commerciale">Commerciale</SelectItem>
                                <SelectItem value="ufficio">Ufficio</SelectItem>
                                <SelectItem value="garage">Garage</SelectItem>
                                <SelectItem value="terreno">Terreno</SelectItem>
                                <SelectItem value="altro">Altro</SelectItem>
                            </SelectContent>
                        </Select>
                    </div>
                    <div>
                        <Label className="text-xs">Titolo</Label>
                        <Select value={f.titolo} onValueChange={(v) => set("titolo", v)}>
                            <SelectTrigger data-testid="pat-titolo"><SelectValue /></SelectTrigger>
                            <SelectContent>
                                <SelectItem value="proprieta">Proprietà</SelectItem>
                                <SelectItem value="comproprieta">Comproprietà</SelectItem>
                                <SelectItem value="usufrutto">Usufrutto</SelectItem>
                                <SelectItem value="nuda_proprieta">Nuda proprietà</SelectItem>
                                <SelectItem value="locazione">Locazione</SelectItem>
                            </SelectContent>
                        </Select>
                    </div>
                    <div className="col-span-2">
                        <Label className="text-xs">Indirizzo</Label>
                        <Input value={f.indirizzo} onChange={(e) => set("indirizzo", e.target.value)}
                            placeholder="Via Roma 10" data-testid="pat-indirizzo" />
                    </div>
                    <div>
                        <Label className="text-xs">Comune</Label>
                        <Input value={f.comune} onChange={(e) => set("comune", e.target.value)}
                            placeholder="Milano" data-testid="pat-comune" />
                    </div>
                    <div className="grid grid-cols-2 gap-2">
                        <div>
                            <Label className="text-xs">Prov.</Label>
                            <Input value={f.provincia} onChange={(e) => set("provincia", e.target.value.toUpperCase())} maxLength={2} data-testid="pat-provincia" />
                        </div>
                        <div>
                            <Label className="text-xs">CAP</Label>
                            <Input value={f.cap} onChange={(e) => set("cap", e.target.value)} maxLength={5} data-testid="pat-cap" />
                        </div>
                    </div>
                    <div>
                        <Label className="text-xs">Superficie (mq)</Label>
                        <Input type="number" value={f.superficie_mq} onChange={(e) => set("superficie_mq", e.target.value)} data-testid="pat-superficie" />
                    </div>
                    <div>
                        <Label className="text-xs">Anno costruzione</Label>
                        <Input type="number" value={f.anno_costruzione} onChange={(e) => set("anno_costruzione", e.target.value)} data-testid="pat-anno" />
                    </div>
                    <div className="grid grid-cols-3 gap-1 col-span-2">
                        <div>
                            <Label className="text-xs">Foglio</Label>
                            <Input value={f.foglio} onChange={(e) => set("foglio", e.target.value)} />
                        </div>
                        <div>
                            <Label className="text-xs">Particella</Label>
                            <Input value={f.particella} onChange={(e) => set("particella", e.target.value)} />
                        </div>
                        <div>
                            <Label className="text-xs">Sub</Label>
                            <Input value={f.sub} onChange={(e) => set("sub", e.target.value)} />
                        </div>
                    </div>
                    <div>
                        <Label className="text-xs">Cat. catastale</Label>
                        <Input value={f.categoria_catastale} onChange={(e) => set("categoria_catastale", e.target.value.toUpperCase())} placeholder="A/2, C/6…" />
                    </div>
                    <div>
                        <Label className="text-xs">Rendita catastale (€)</Label>
                        <Input type="number" value={f.rendita_catastale} onChange={(e) => set("rendita_catastale", e.target.value)} />
                    </div>
                    <div>
                        <Label className="text-xs">Valore commerciale (€)</Label>
                        <Input type="number" value={f.valore_commerciale} onChange={(e) => set("valore_commerciale", e.target.value)} data-testid="pat-val-comm" />
                    </div>
                    <div>
                        <Label className="text-xs flex items-center justify-between">
                            Valore ricostruzione (€)
                            <button type="button" onClick={suggerisciRicostruzione} className="text-[10px] text-sky-600 underline">Suggerisci</button>
                        </Label>
                        <Input type="number" value={f.valore_ricostruzione} onChange={(e) => set("valore_ricostruzione", e.target.value)} data-testid="pat-val-ricos" />
                    </div>
                    <div>
                        <Label className="text-xs">Degrado (%)</Label>
                        <Input type="number" value={f.percentuale_degrado} onChange={(e) => set("percentuale_degrado", e.target.value)} min={0} max={100} data-testid="pat-degrado" />
                    </div>
                    <div>
                        <Label className="text-xs">Quota proprietà (%)</Label>
                        <Input type="number" value={f.percentuale_proprieta} onChange={(e) => set("percentuale_proprieta", e.target.value)} min={0} max={100} />
                    </div>
                    <div className="col-span-2">
                        <Label className="text-xs">Note</Label>
                        <Input value={f.note} onChange={(e) => set("note", e.target.value)} placeholder="Es. Ristrutturato nel 2020, mutuo residuo €120k…" />
                    </div>
                </div>
                <DialogFooter>
                    <Button variant="outline" onClick={onClose} disabled={busy}>Annulla</Button>
                    <Button onClick={save} disabled={busy} className="bg-sky-700 hover:bg-sky-800" data-testid="pat-save">
                        {busy ? "Salvataggio…" : (item ? "Aggiorna" : "Aggiungi + Geocodifica")}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}
