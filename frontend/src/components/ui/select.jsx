import * as React from "react"
import { Check, ChevronDown } from "lucide-react"

import { cn } from "@/lib/utils"
import { Popover, PopoverTrigger, PopoverContent } from "@/components/ui/popover"
import {
  Command,
  CommandInput,
  CommandList,
  CommandEmpty,
  CommandItem,
  CommandGroup,
  CommandSeparator,
} from "@/components/ui/command"

// --- helpers -----------------------------------------------------------
function nodeText(node) {
  if (node == null || node === false) return ""
  if (typeof node === "string" || typeof node === "number") return String(node)
  if (Array.isArray(node)) return node.map(nodeText).join(" ")
  if (React.isValidElement(node)) return nodeText(node.props?.children)
  return ""
}

function countSelectItems(children) {
  let n = 0
  React.Children.forEach(children, (c) => {
    if (!React.isValidElement(c)) return
    if (c.type === SelectItem) n += 1
    else if (c.props && c.props.children) n += countSelectItems(c.props.children)
  })
  return n
}

const SelectCtx = React.createContext(null)

// --- Root --------------------------------------------------------------
const Select = ({ value, defaultValue, onValueChange, disabled, open, onOpenChange, children }) => {
  const [uncValue, setUncValue] = React.useState(defaultValue)
  const val = value !== undefined ? value : uncValue
  const [uncOpen, setUncOpen] = React.useState(false)
  const isOpen = open !== undefined ? open : uncOpen

  const setOpen = React.useCallback((o) => {
    if (open === undefined) setUncOpen(o)
    onOpenChange?.(o)
  }, [open, onOpenChange])

  const setValue = React.useCallback((v) => {
    if (value === undefined) setUncValue(v)
    onValueChange?.(v)
    if (open === undefined) setUncOpen(false)
    onOpenChange?.(false)
  }, [value, onValueChange, open, onOpenChange])

  const labelMap = React.useMemo(() => {
    const m = {}
    const walk = (nodes) => React.Children.forEach(nodes, (c) => {
      if (!React.isValidElement(c)) return
      if (c.type === SelectItem) m[String(c.props.value)] = c.props.children
      else if (c.props?.children) walk(c.props.children)
    })
    walk(children)
    return m
  }, [children])

  const ctx = React.useMemo(() => ({ val, setValue, disabled, labelMap }), [val, setValue, disabled, labelMap])

  return (
    <SelectCtx.Provider value={ctx}>
      <Popover open={!!isOpen && !disabled} onOpenChange={(o) => !disabled && setOpen(o)}>
        {children}
      </Popover>
    </SelectCtx.Provider>
  )
}

const SelectGroup = ({ children }) => <CommandGroup>{children}</CommandGroup>

const SelectValue = ({ placeholder, children }) => {
  const { val, labelMap } = React.useContext(SelectCtx)
  const label = val != null && val !== "" ? labelMap[String(val)] : undefined
  if (label !== undefined && label !== null && label !== "") {
    return <span className="truncate">{label}</span>
  }
  return <span className="truncate text-muted-foreground">{placeholder ?? children ?? ""}</span>
}

const SelectTrigger = React.forwardRef(({ className, children, ...props }, ref) => {
  const { disabled } = React.useContext(SelectCtx)
  return (
    <PopoverTrigger asChild>
      <button
        ref={ref}
        type="button"
        disabled={disabled}
        className={cn(
          "flex h-9 w-full items-center justify-between whitespace-nowrap rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-sm ring-offset-background focus:outline-none focus:ring-1 focus:ring-ring disabled:cursor-not-allowed disabled:opacity-50 [&>span]:line-clamp-1 text-left",
          className
        )}
        {...props}>
        {children}
        <ChevronDown className="h-4 w-4 opacity-50 shrink-0" />
      </button>
    </PopoverTrigger>
  )
})
SelectTrigger.displayName = "SelectTrigger"

const SelectContent = React.forwardRef(({ className, children, position, searchable, searchPlaceholder = "Cerca...", ...props }, ref) => {
  const total = React.useMemo(() => countSelectItems(children), [children])
  const showSearch = searchable ?? total > 7
  return (
    <PopoverContent
      ref={ref}
      align="start"
      className={cn("p-0 w-[var(--radix-popover-trigger-width)] min-w-[8rem] max-w-[92vw]", className)}
      {...props}>
      <Command
        filter={(value, search) =>
          value.toLowerCase().includes(search.trim().toLowerCase()) ? 1 : 0
        }>
        {showSearch && <CommandInput placeholder={searchPlaceholder} className="h-9" />}
        <CommandList className="max-h-[300px]">
          {showSearch && <CommandEmpty>Nessun risultato</CommandEmpty>}
          {children}
        </CommandList>
      </Command>
    </PopoverContent>
  )
})
SelectContent.displayName = "SelectContent"

const SelectLabel = React.forwardRef(({ className, ...props }, ref) => (
  <div ref={ref} className={cn("px-2 py-1.5 text-xs font-semibold text-muted-foreground", className)} {...props} />
))
SelectLabel.displayName = "SelectLabel"

const SelectItem = React.forwardRef(({ className, children, value, disabled, ...props }, ref) => {
  const { val, setValue } = React.useContext(SelectCtx)
  const selected = String(val) === String(value)
  return (
    <CommandItem
      ref={ref}
      value={`${nodeText(children)}\u0000${String(value)}`}
      disabled={disabled}
      onSelect={() => setValue(value)}
      className={cn("relative cursor-pointer pr-8", className)}
      {...props}>
      <span className="truncate">{children}</span>
      {selected && (
        <span className="absolute right-2 flex h-3.5 w-3.5 items-center justify-center">
          <Check className="h-4 w-4" />
        </span>
      )}
    </CommandItem>
  )
})
SelectItem.displayName = "SelectItem"

const SelectSeparator = React.forwardRef(({ className, ...props }, ref) => (
  <CommandSeparator className={cn("my-1", className)} {...props} />
))
SelectSeparator.displayName = "SelectSeparator"

const SelectScrollUpButton = () => null
const SelectScrollDownButton = () => null

export {
  Select,
  SelectGroup,
  SelectValue,
  SelectTrigger,
  SelectContent,
  SelectLabel,
  SelectItem,
  SelectSeparator,
  SelectScrollUpButton,
  SelectScrollDownButton,
}
