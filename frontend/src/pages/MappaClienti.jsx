import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "@/lib/api";
import { PageHeader, Loading, Empty } from "@/components/Shared";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { MapPin, Navigation } from "lucide-react";
import { toast } from "sonner";

// Leaflet via CDN dinamico per evitare bundle bloat
function useLeaflet() {
    const [loaded, setLoaded] = useState(false);
    useEffect(() => {
        if (window.L) { setLoaded(true); return; }
        const css = document.createElement("link");
        css.rel = "stylesheet";
        css.href = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.css";
        document.head.appendChild(css);
        const s = document.createElement("script");
        s.src = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.js";
        s.onload = () => setLoaded(true);
        document.body.appendChild(s);
    }, []);
    return loaded;
}

export default function MappaClienti() {
    const [items, setItems] = useState(null);
    const [busy, setBusy] = useState(false);
    const leafletReady = useLeaflet();
    const nav = useNavigate();

    const load = () => api.get("/geo/anagrafiche").then((r) => setItems(r.data));
    useEffect(() => { load(); }, []);

    useEffect(() => {
        if (!leafletReady || !items) return;
        const L = window.L;
        const el = document.getElementById("map");
        if (!el) return;
        // reset map istance se gia presente
        if (el._leaflet_id) { el.innerHTML = ""; delete el._leaflet_id; }
        const map = L.map("map").setView([42.5, 12.5], 6);
        L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
            attribution: "&copy; OpenStreetMap",
        }).addTo(map);
        const markers = items.map((a) => {
            const m = L.marker([a.lat, a.lng]).addTo(map);
            m.bindPopup(`<b>${a.ragione_sociale}</b><br>${a.indirizzo || ""}<br>${a.comune || ""} (${a.provincia || ""})<br><a href="/anagrafiche/${a.id}">Apri scheda</a>`);
            return m;
        });
        if (markers.length) {
            const group = L.featureGroup(markers);
            map.fitBounds(group.getBounds().pad(0.2));
        }
    }, [leafletReady, items, nav]);

    const geocodeAll = async () => {
        setBusy(true);
        try {
            const all = await api.get("/anagrafiche");
            const senza = all.data.filter((a) => !a.lat && (a.comune || a.indirizzo));
            toast.message(`Geocoding di ${senza.length} clienti...`);
            let ok = 0;
            for (const a of senza.slice(0, 50)) {  // limite per evitare rate-limit Nominatim
                try {
                    const r = await api.post(`/geo/anagrafiche/${a.id}/geocode`);
                    if (r.data.found) ok++;
                    await new Promise((res) => setTimeout(res, 1100));  // 1 req/sec
                } catch { /* skip */ }
            }
            toast.success(`Geocoding completato: ${ok}/${senza.length} clienti localizzati`);
            load();
        } finally { setBusy(false); }
    };

    return (
        <div data-testid="mappa-page">
            <PageHeader
                title="Mappa clienti"
                subtitle="Geolocalizzazione delle anagrafiche con coordinate"
                actions={
                    <Button variant="outline" onClick={geocodeAll} disabled={busy} data-testid="geocode-all-button">
                        <Navigation size={14} className="mr-1" /> {busy ? "Geocoding..." : "Geocodifica clienti"}
                    </Button>
                }
            />
            <Card className="p-4 border-slate-200">
                {items === null ? <Loading /> : items.length === 0 ? (
                    <div className="text-center py-12">
                        <MapPin size={32} className="text-slate-300 mx-auto mb-3" />
                        <div className="text-sm text-slate-600 mb-1">Nessun cliente geolocalizzato.</div>
                        <div className="text-xs text-slate-500">Premi &quot;Geocodifica clienti&quot; per cercare le coordinate dei clienti che hanno un indirizzo.</div>
                    </div>
                ) : (
                    <>
                        <div className="text-xs text-slate-500 mb-2 num">{items.length} clienti sulla mappa</div>
                        <div id="map" style={{ height: 600, borderRadius: 6, border: "1px solid #E2E8F0" }} />
                    </>
                )}
            </Card>
        </div>
    );
}
