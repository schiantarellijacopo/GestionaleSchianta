import { API_BASE } from "@/lib/api";

// Consuma l'endpoint SSE /copilot/chat/stream e invoca i callback per ogni evento
export async function streamCopilot({ message, sessionId, onMeta, onDelta, onError }) {
    const token = localStorage.getItem("token");
    const res = await fetch(`${API_BASE}/copilot/chat/stream`, {
        method: "POST",
        credentials: "include",
        headers: {
            "Content-Type": "application/json",
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ message, session_id: sessionId }),
    });
    if (!res.ok || !res.body) throw new Error(`HTTP ${res.status}`);
    const reader = res.body.getReader();
    const dec = new TextDecoder();
    let buf = "";
    for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += dec.decode(value, { stream: true });
        let idx;
        while ((idx = buf.indexOf("\n\n")) !== -1) {
            const raw = buf.slice(0, idx);
            buf = buf.slice(idx + 2);
            let event = "delta";
            let data = "";
            for (const line of raw.split("\n")) {
                if (line.startsWith("event:")) event = line.slice(6).trim();
                else if (line.startsWith("data:")) data += line.slice(5).trim();
            }
            if (!data) continue;
            let obj;
            try { obj = JSON.parse(data); } catch { continue; }
            if (event === "meta") onMeta?.(obj);
            else if (event === "error") onError?.(obj);
            else if (event === "delta") onDelta?.(obj.t || "");
        }
    }
}
