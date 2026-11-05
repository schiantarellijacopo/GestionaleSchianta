import * as React from "react";
import { Check, ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";
import { Popover, PopoverTrigger, PopoverContent } from "@/components/ui/popover";
import {
  Command,
  CommandInput,
  CommandList,
  CommandEmpty,
  CommandItem,
} from "@/components/ui/command";

function labelToString(label) {
  if (label == null || label === false) return "";
  if (typeof label === "string" || typeof label === "number") return String(label);
  if (Array.isArray(label)) return label.map(labelToString).join(" ");
  if (React.isValidElement(label)) return labelToString(label.props?.children);
  return "";
}

// Flatten React children (handles arrays & fragments) collecting native <option> elements.
function flattenOptions(children) {
  const out = [];
  React.Children.forEach(children, (child) => {
    if (!child || typeof child !== "object") return;
    if (child.type === React.Fragment) {
      out.push(...flattenOptions(child.props.children));
      return;
    }
    if (child.type === "option") {
      out.push({
        value: child.props.value ?? "",
        label: child.props.children,
        disabled: !!child.props.disabled,
      });
    }
  });
  return out;
}

/**
 * Drop-in replacement for a native <select> that adds type-to-search.
 * Keeps the native contract: `value`, `onChange(e-like {target:{value}})`, <option> children.
 */
export const SearchableSelect = React.forwardRef(function SearchableSelect(
  {
    value,
    onChange,
    children,
    className,
    disabled,
    placeholder,
    searchPlaceholder = "Cerca...",
    emptyText = "Nessun risultato",
    id,
    title,
    "data-testid": testId,
    ...rest
  },
  ref
) {
  const [open, setOpen] = React.useState(false);
  const options = React.useMemo(() => flattenOptions(children), [children]);
  const showSearch = options.length > 7;
  const current = String(value ?? "");
  const selected = options.find((o) => String(o.value) === current);
  const triggerNode = selected
    ? selected.label
    : placeholder ?? (options[0] ? options[0].label : "");
  const hasValue = !!selected && labelToString(selected.label).trim() !== "";

  return (
    <Popover open={open} onOpenChange={(o) => !disabled && setOpen(o)}>
      <PopoverTrigger asChild>
        <button
          type="button"
          ref={ref}
          id={id}
          title={title}
          disabled={disabled}
          data-testid={testId}
          aria-haspopup="listbox"
          className={cn(
            "flex items-center justify-between gap-1 bg-white text-left disabled:opacity-50 disabled:cursor-not-allowed focus:outline-none",
            className
          )}
          {...rest}
        >
          <span className={cn("truncate", !hasValue && "text-slate-400")}>
            {triggerNode || "—"}
          </span>
          <ChevronDown className="h-3.5 w-3.5 shrink-0 opacity-50" />
        </button>
      </PopoverTrigger>
      <PopoverContent
        align="start"
        className="p-0 w-[var(--radix-popover-trigger-width)] min-w-[200px] max-w-[92vw]"
      >
        <Command
          filter={(val, search) =>
            val.toLowerCase().includes(search.trim().toLowerCase()) ? 1 : 0
          }
        >
          {showSearch && <CommandInput placeholder={searchPlaceholder} className="h-9" />}
          <CommandList>
            {showSearch && <CommandEmpty>{emptyText}</CommandEmpty>}
            {options.map((o, i) => (
              <CommandItem
                key={`${o.value}-${i}`}
                value={`${labelToString(o.label)}\u0000${i}`}
                disabled={o.disabled}
                onSelect={() => {
                  onChange?.({ target: { value: o.value } });
                  setOpen(false);
                }}
                className="cursor-pointer"
              >
                <Check
                  className={cn(
                    "mr-2 h-3.5 w-3.5 shrink-0",
                    String(o.value) === current ? "opacity-100" : "opacity-0"
                  )}
                />
                <span className="truncate">{o.label}</span>
              </CommandItem>
            ))}
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  );
});

export default SearchableSelect;
