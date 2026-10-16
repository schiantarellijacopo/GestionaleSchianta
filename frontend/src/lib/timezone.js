// Forza l'ora di Roma (Europe/Rome) su TUTTE le formattazioni di data/ora del
// frontend, indipendentemente dal fuso del dispositivo. Intl gestisce in automatico
// il cambio ora legale/solare (CET/CEST). Chi passa un `timeZone` esplicito lo mantiene.
const ROME = "Europe/Rome";
const IT = "it-IT";

function patch(method) {
  const orig = Date.prototype[method];
  Date.prototype[method] = function (locales, options) {
    return orig.call(this, locales || IT, { timeZone: ROME, ...(options || {}) });
  };
}

["toLocaleString", "toLocaleDateString", "toLocaleTimeString"].forEach(patch);

// Helper esplicito per ottenere "adesso" come stringa leggibile in ora di Roma.
export function nowRome(options) {
  return new Date().toLocaleString(IT, options);
}
