import { Input } from "@/components/ui/input";
import { forwardRef } from "react";

/** Input che forza l'uppercase automatico durante la digitazione.
 * Si comporta come <Input> ma trasforma value e onChange in MAIUSCOLO.
 */
const UpperInput = forwardRef(function UpperInput({ onChange, value, ...rest }, ref) {
    const handle = (e) => {
        const v = (e.target.value || "").toUpperCase();
        if (onChange) {
            // crea evento sintetico con valore uppercase
            const ev = { ...e, target: { ...e.target, value: v } };
            onChange(ev);
        }
    };
    return (
        <Input
            ref={ref}
            value={(value ?? "").toString().toUpperCase()}
            onChange={handle}
            className="uc"
            {...rest}
        />
    );
});

export default UpperInput;
