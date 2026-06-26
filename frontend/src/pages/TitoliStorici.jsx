/**
 * Pagina dedicata "Titoli storici" — mostra solo titoli INCASSATI.
 *
 * Wrapper sottile attorno a Titoli.jsx: passa il flag `storicoMode`
 * che cambia preset, titoli, colonne (incassato il / pagato con) e
 * default filtering (`stato=incassato`).
 *
 * I titoli "da incassare" e "sospesi" restano in /titoli.
 */
import Titoli from "./Titoli";

export default function TitoliStorici() {
    return <Titoli storicoMode />;
}
