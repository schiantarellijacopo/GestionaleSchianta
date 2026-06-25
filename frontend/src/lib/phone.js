/**
 * Formatta un numero di telefono italiano per visualizzazione.
 * Converte il prefisso "0039" in "+39" e raggruppa le cifre.
 * Es: "00393470009438" -> "+39 347 000 9438"
 *     "3470009438"     -> "347 000 9438"
 *     "+39 347 000 9438" (già OK) -> inalterato
 */
export function formatPhone(raw) {
    if (!raw) return "";
    let s = String(raw).trim();
    // normalizza: rimuovi spazi, trattini, parentesi
    const clean = s.replace(/[\s\-().]/g, "");
    // sostituisci 00xx con +xx (qualunque prefisso internazionale)
    let normalized = clean;
    if (normalized.startsWith("00")) {
        normalized = "+" + normalized.slice(2);
    }
    // se inizia con +39 + 10 cifre → raggruppa "+39 XXX XXX XXXX"
    const m = normalized.match(/^(\+39)(\d{3})(\d{3})(\d{3,4})$/);
    if (m) return `${m[1]} ${m[2]} ${m[3]} ${m[4]}`;
    // se inizia con +XX + 10 cifre IT-style
    const mIntl = normalized.match(/^(\+\d{1,3})(\d{3})(\d{3})(\d{3,4})$/);
    if (mIntl) return `${mIntl[1]} ${mIntl[2]} ${mIntl[3]} ${mIntl[4]}`;
    // numero IT senza prefisso (10 cifre)
    const mIt = normalized.match(/^(\d{3})(\d{3})(\d{3,4})$/);
    if (mIt) return `${mIt[1]} ${mIt[2]} ${mIt[3]}`;
    // fallback: ritorna normalizzato (con + se 00 era presente)
    return normalized;
}

/**
 * Restituisce il valore da usare nell'href="tel:..." (senza spazi, con +).
 */
export function telHref(raw) {
    if (!raw) return "";
    const clean = String(raw).replace(/[\s\-().]/g, "");
    if (clean.startsWith("00")) return "+" + clean.slice(2);
    return clean;
}
