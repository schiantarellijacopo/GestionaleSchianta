import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "@/lib/api";
import { PageHeader, Loading } from "@/components/Shared";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { MapPin, Navigation, Search } from "lucide-react";
import { toast } from "sonner";

// Carica Leaflet + plugin MarkerCluster via CDN una sola volta.
function useLeafletCluster() {
    const [ready, setReady] = useState(!!(window.L && window.L.markerClusterGroup));
    useEffect(() => {
        if (window.L && window.L.markerClusterGroup) { setReady(true); return; }
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
        addCss("https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.css");
        addCss("https://unpkg.com/leaflet.markercluster@1.5.3/dist/MarkerCluster.Default.css");
        (async () => {
            try {
                await addScript("https://unpkg.com/leaflet@1.9.4/dist/leaflet.js");
                await addScript("https://unpkg.com/leaflet.markercluster@1.5.3/dist/leaflet.markercluster.js");
                setReady(true);
            } catch (e) {
                console.error("Leaflet load error", e);
            }
        })();
    }, []);
    return ready;
}

const TILE_LAYERS = {
    standard: {
        url: "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
        attribution: "&copy; OpenStreetMap",
        max: 19,
    },
    consumatore: {
        // Carto Voyager — sfondo chiaro elegante
        url: "https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png",
        attribution: "&copy; OSM &middot; &copy; CARTO",
        max: 20,
    },
    satellitare: {
        url: "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attribution: "Tiles &copy; Esri",
        max: 19,
    },
};

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
}[c]));

function makeIcon(L, color) {
    // marker pin SVG inline con stelo (stile screenshot Parrocchie)
    const svg = `
        <svg xmlns="http://www.w3.org/2000/svg" width="30" height="42" viewBox="0 0 30 42">
            <path d="M15 0C6.7 0 0 6.7 0 15c0 11 15 27 15 27s15-16 15-27C30 6.7 23.3 0 15 0z"
                  fill="${color}" stroke="#ffffff" stroke-width="2"/>
            <circle cx="15" cy="15" r="5" fill="#0f172a"/>
        </svg>`;
    return L.divIcon({
        className: "anag-pin",
        html: svg,
        iconSize: [30, 42],
        iconAnchor: [15, 42],
        popupAnchor: [0, -36],
    });
}

export default function MappaClienti() {
    const [items, setItems] = useState(null);
    const [busy, setBusy] = useState(false);
    const [layer, setLayer] = useState("consumatore");
    const [showClienti, setShowClienti] = useState(true);
    const [showProspect, setShowProspect] = useState(true);
    const [query, setQuery] = useState("");
    const [tagFilter, setTagFilter] = useState("all");
    const ready = useLeafletCluster();
    const nav = useNavigate();
    const mapRef = useRef(null);
    const tileRef = useRef(null);
    const clusterRef = useRef(null);
    const iconsRef = useRef({});

    const load = () => api.get("/geo/anagrafiche").then((r) => setItems(r.data));
    useEffect(() => { load(); }, []);

    // tags unici per il filtro
    const allTags = useMemo(() => {
        if (!items) return [];
        const s = new Set();
        items.forEach((a) => (a.tags || []).forEach((t) => s.add(t)));
        return Array.from(s).sort();
    }, [items]);

    // filtro applicato
    const filtered = useMemo(() => {
        if (!items) return [];
        const q = query.trim().toLowerCase();
        return items.filter((a) => {
            if (a.is_cliente && !showClienti) return false;
            if (!a.is_cliente && !showProspect) return false;
            if (tagFilter !== "all" && !(a.tags || []).includes(tagFilter)) return false;
            if (q) {
                const hay = `${a.ragione_sociale || ""} ${a.indirizzo || ""} ${a.comune || ""} ${a.provincia || ""}`.toLowerCase();
                if (!hay.includes(q)) return false;
            }
            return true;
        });
    }, [items, showClienti, showProspect, query, tagFilter]);

    // INIT mappa una sola volta
    useEffect(() => {
        if (!ready || mapRef.current) return;
        const L = window.L;
        const el = document.getElementById("anag-map");
        if (!el) return;
        const map = L.map(el, { zoomControl: true, preferCanvas: true }).setView([42.5, 12.5], 6);
        mapRef.current = map;
        const cfg = TILE_LAYERS[layer];
        tileRef.current = L.tileLayer(cfg.url, { attribution: cfg.attribution, maxZoom: cfg.max }).addTo(map);
        clusterRef.current = L.markerClusterGroup({
            showCoverageOnHover: false,
            maxClusterRadius: 60,
            iconCreateFunction: (cluster) => {
                const markers = cluster.getAllChildMarkers();
                const anyProspect = markers.some((m) => m.options.dataIsProspect);
                const allProspect = markers.every((m) => m.options.dataIsProspect);
                const color = allProspect ? "#dc2626" : anyProspect ? "#a855f7" : "#0ea5e9";
                return L.divIcon({
                    html: `<div style="background:${color};opacity:.85;border:3px solid #fff;border-radius:50%;width:42px;height:42px;display:flex;align-items:center;justify-content:center;color:#fff;font-weight:600;box-shadow:0 2px 6px rgba(0,0,0,.25);">${cluster.getChildCount()}</div>`,
                    className: "cluster-icon",
                    iconSize: [42, 42],
                });
            },
        });
        map.addLayer(clusterRef.current);
        iconsRef.current.cliente = makeIcon(L, "#0ea5e9");
        iconsRef.current.prospect = makeIcon(L, "#dc2626");
    }, [ready, layer]);

    // cambio layer di sfondo
    useEffect(() => {
        if (!mapRef.current || !tileRef.current) return;
        const L = window.L;
        mapRef.current.removeLayer(tileRef.current);
        const cfg = TILE_LAYERS[layer];
        tileRef.current = L.tileLayer(cfg.url, { attribution: cfg.attribution, maxZoom: cfg.max }).addTo(mapRef.current);
    }, [layer]);

    // ridisegna marker quando cambia filtered
    useEffect(() => {
        if (!ready || !clusterRef.current || !mapRef.current) return;
        const L = window.L;
        const cluster = clusterRef.current;
        cluster.clearLayers();
        const markers = [];
        filtered.forEach((a) => {
            const isProspect = !a.is_cliente;
            const icon = isProspect ? iconsRef.current.prospect : iconsRef.current.cliente;
            const m = L.marker([a.lat, a.lng], { icon, dataIsProspect: isProspect });
            const badgeCls = isProspect
                ? "background:#fee2e2;color:#b91c1c;border:1px solid #fecaca"
                : "background:#e0f2fe;color:#0369a1;border:1px solid #bae6fd";
            const badge = isProspect ? "PROSPECT" : "CLIENTE";
            m.bindPopup(
                `<div style="font-family:inherit;min-width:200px">
                    <div style="font-weight:700;font-size:14px;margin-bottom:6px;color:#0f172a">${esc(a.ragione_sociale)}</div>
                    <div style="font-size:12px;color:#475569;margin-bottom:2px">${esc(a.indirizzo || "")}</div>
                    <div style="font-size:12px;color:#475569;margin-bottom:8px">${esc(a.comune || "")} ${a.provincia ? "(" + esc(a.provincia) + ")" : ""}</div>
                    <div style="display:inline-block;padding:2px 8px;border-radius:10px;font-size:10px;font-weight:600;letter-spacing:.4px;${badgeCls};margin-bottom:8px">${badge}</div>
                    ${(a.tags || []).length ? `<div style="font-size:10px;color:#64748b;margin-bottom:8px">${(a.tags || []).map(t => `<span style="background:#f1f5f9;padding:1px 6px;border-radius:8px;margin-right:4px">${esc(t)}</span>`).join("")}</div>` : ""}
                    <a href="/anagrafiche/${esc(a.id)}" style="display:inline-flex;align-items:center;gap:4px;color:#0369a1;font-weight:500;font-size:12px;text-decoration:none;border-bottom:1px solid #bae6fd">Apri scheda →</a>
                </div>`
            );
            markers.push(m);
        });
        if (markers.length) {
            cluster.addLayers(markers);
            try {
                const group = L.featureGroup(markers);
                mapRef.current.fitBounds(group.getBounds().pad(0.15));
            } catch { /* ignore */ }
        }
    }, [filtered, ready]);

    const geocodeAll = async () => {
        setBusy(true);
        try {
            const all = await api.get("/anagrafiche");
            const senza = all.data.filter((a) => !a.lat && (a.comune || a.indirizzo));
            toast.message(`Geocoding di ${senza.length} clienti...`);
            let ok = 0;
            for (const a of senza.slice(0, 50)) {
                try {
                    const r = await api.post(`/geo/anagrafiche/${a.id}/geocode`);
                    if (r.data.found) ok++;
                    await new Promise((res) => setTimeout(res, 1100));
                } catch (err) {
                    console.warn(`Geocoding fallito per ${a.id}:`, err?.message || err);
                }
            }
            toast.success(`Geocoding completato: ${ok}/${senza.length} localizzati`);
            load();
        } finally { setBusy(false); }
    };

    const totalClienti = (items || []).filter((a) => a.is_cliente).length;
    const totalProspect = (items || []).filter((a) => !a.is_cliente).length;

    return (
        <div data-testid="mappa-page">
            <PageHeader
                title="Mappa clienti"
                subtitle={
                    <>
                        <span className="inline-flex items-center gap-1 mr-3"><span className="inline-block w-3 h-3 rounded-full bg-sky-500" /> Clienti attivi {items ? `(${totalClienti})` : ""}</span>
                        <span className="inline-flex items-center gap-1"><span className="inline-block w-3 h-3 rounded-full bg-red-600" /> Prospect / non clienti {items ? `(${totalProspect})` : ""}</span>
                    </>
                }
                actions={
                    <Button variant="outline" onClick={geocodeAll} disabled={busy} data-testid="geocode-all-button">
                        <Navigation size={14} className="mr-1" /> {busy ? "Geocoding..." : "Geocodifica clienti"}
                    </Button>
                }
            />

            <Card className="p-3 border-slate-200 mb-3 flex flex-wrap items-end gap-3" data-testid="mappa-toolbar">
                <div>
                    <Label className="text-xs">Sfondo</Label>
                    <div className="flex gap-1 mt-1">
                        {Object.keys(TILE_LAYERS).map((k) => (
                            <Button
                                key={k}
                                size="sm"
                                variant={layer === k ? "default" : "outline"}
                                onClick={() => setLayer(k)}
                                data-testid={`mappa-layer-${k}`}
                                className="capitalize"
                            >
                                {k}
                            </Button>
                        ))}
                    </div>
                </div>
                <div className="flex items-center gap-2 pl-3 border-l border-slate-200">
                    <Checkbox checked={showClienti} onCheckedChange={(v) => setShowClienti(!!v)} id="t-clienti" data-testid="toggle-clienti" />
                    <label htmlFor="t-clienti" className="text-sm flex items-center gap-1 cursor-pointer">
                        <span className="inline-block w-2.5 h-2.5 rounded-full bg-sky-500" /> Clienti
                    </label>
                    <Checkbox checked={showProspect} onCheckedChange={(v) => setShowProspect(!!v)} id="t-prosp" data-testid="toggle-prospect" />
                    <label htmlFor="t-prosp" className="text-sm flex items-center gap-1 cursor-pointer">
                        <span className="inline-block w-2.5 h-2.5 rounded-full bg-red-600" /> Prospect
                    </label>
                </div>
                <div className="flex-1 min-w-[200px] relative">
                    <Label className="text-xs">Cerca nome / indirizzo</Label>
                    <div className="relative">
                        <Input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Es. Mario Rossi, Como…" className="pl-8" data-testid="mappa-search" />
                        <Search size={14} className="absolute left-2 top-1/2 -translate-y-1/2 text-slate-400" />
                    </div>
                </div>
                {allTags.length > 0 && (
                    <div className="min-w-[180px]">
                        <Label className="text-xs">Filtra per tag</Label>
                        <Select value={tagFilter} onValueChange={setTagFilter}>
                            <SelectTrigger data-testid="mappa-tag-filter"><SelectValue /></SelectTrigger>
                            <SelectContent>
                                <SelectItem value="all">— tutti i tag —</SelectItem>
                                {allTags.map((t) => <SelectItem key={t} value={t}>{t}</SelectItem>)}
                            </SelectContent>
                        </Select>
                    </div>
                )}
            </Card>

            <Card className="p-3 border-slate-200">
                {items === null ? <Loading /> : items.length === 0 ? (
                    <div className="text-center py-12">
                        <MapPin size={32} className="text-slate-300 mx-auto mb-3" />
                        <div className="text-sm text-slate-600 mb-1">Nessun cliente geolocalizzato.</div>
                        <div className="text-xs text-slate-500">Premi &quot;Geocodifica clienti&quot; per cercare le coordinate di chi ha un indirizzo.</div>
                    </div>
                ) : (
                    <>
                        <div className="text-xs text-slate-500 mb-2 num" data-testid="mappa-count">
                            {filtered.length} anagrafiche visibili sulla mappa (su {items.length} totali con coordinate)
                        </div>
                        <div id="anag-map" style={{ height: 640, borderRadius: 6, border: "1px solid #E2E8F0" }} data-testid="anag-map-container" />
                    </>
                )}
            </Card>
        </div>
    );
}
