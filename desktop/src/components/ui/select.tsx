import * as React from "react";
import { createPortal } from "react-dom";
import { Check, ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";

type SelectOption = {
    label: string;
    value: string;
};

export interface SelectProps {
    className?: string;
    disabled?: boolean;
    onValueChange: (value: string) => void;
    options: SelectOption[];
    uiSize?: "default" | "sm";
    value: string;
}

type MenuPosition = {
    left: number;
    maxHeight: number;
    top: number;
    width: number;
};

const sizeClasses: Record<NonNullable<SelectProps["uiSize"]>, string> = {
    default: "h-10 rounded-xl px-3 pr-10 text-sm",
    sm: "h-8 rounded-lg px-2.5 pr-8 text-[11px] uppercase tracking-[0.14em]",
};

const menuOffset = 8;
const menuPadding = 12;
const maxMenuHeight = 280;

function clampMenuPosition(triggerRect: DOMRect): MenuPosition {
    const viewportHeight = window.innerHeight;
    const availableBelow = viewportHeight - triggerRect.bottom - menuPadding;
    const availableAbove = triggerRect.top - menuPadding;
    const shouldOpenAbove = availableBelow < 180 && availableAbove > availableBelow;
    const resolvedHeight = Math.min(maxMenuHeight, Math.max(120, shouldOpenAbove ? availableAbove - menuOffset : availableBelow - menuOffset));

    return {
        left: triggerRect.left,
        width: triggerRect.width,
        maxHeight: resolvedHeight,
        top: shouldOpenAbove ? Math.max(menuPadding, triggerRect.top - resolvedHeight - menuOffset) : triggerRect.bottom + menuOffset,
    };
}

const Select = React.forwardRef<HTMLButtonElement, SelectProps>(
    ({ className, disabled = false, onValueChange, options, uiSize = "default", value }, ref) => {
        const [open, setOpen] = React.useState(false);
        const [menuPosition, setMenuPosition] = React.useState<MenuPosition | null>(null);
        const [highlightedIndex, setHighlightedIndex] = React.useState(0);
        const triggerRef = React.useRef<HTMLButtonElement | null>(null);
        const menuRef = React.useRef<HTMLDivElement | null>(null);
        const selectId = React.useId();

        const selectedIndex = Math.max(
            0,
            options.findIndex((option) => option.value === value),
        );
        const selectedOption = options[selectedIndex] ?? options[0];

        React.useImperativeHandle(ref, () => triggerRef.current as HTMLButtonElement, []);

        const updatePosition = React.useCallback(() => {
            if (!triggerRef.current) {
                return;
            }
            setMenuPosition(clampMenuPosition(triggerRef.current.getBoundingClientRect()));
        }, []);

        React.useEffect(() => {
            if (!open) {
                return;
            }

            updatePosition();

            function handlePointerDown(event: MouseEvent) {
                const target = event.target as Node;
                if (triggerRef.current?.contains(target) || menuRef.current?.contains(target)) {
                    return;
                }
                setOpen(false);
            }

            function handleKeyDown(event: KeyboardEvent) {
                if (event.key === "Escape") {
                    setOpen(false);
                    triggerRef.current?.focus();
                    return;
                }

                if (event.key === "ArrowDown") {
                    event.preventDefault();
                    setHighlightedIndex((current) => Math.min(current + 1, options.length - 1));
                    return;
                }

                if (event.key === "ArrowUp") {
                    event.preventDefault();
                    setHighlightedIndex((current) => Math.max(current - 1, 0));
                    return;
                }

                if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    const nextOption = options[highlightedIndex];
                    if (nextOption) {
                        onValueChange(nextOption.value);
                    }
                    setOpen(false);
                    triggerRef.current?.focus();
                }
            }

            function handleLayoutChange() {
                updatePosition();
            }

            document.addEventListener("mousedown", handlePointerDown);
            document.addEventListener("keydown", handleKeyDown);
            window.addEventListener("resize", handleLayoutChange);
            window.addEventListener("scroll", handleLayoutChange, true);

            return () => {
                document.removeEventListener("mousedown", handlePointerDown);
                document.removeEventListener("keydown", handleKeyDown);
                window.removeEventListener("resize", handleLayoutChange);
                window.removeEventListener("scroll", handleLayoutChange, true);
            };
        }, [highlightedIndex, onValueChange, open, options, updatePosition]);

        React.useEffect(() => {
            if (open) {
                setHighlightedIndex(selectedIndex);
            }
        }, [open, selectedIndex]);

        React.useEffect(() => {
            if (!open || !menuRef.current) {
                return;
            }

            const activeOption = menuRef.current.querySelector<HTMLElement>(`[data-option-index="${highlightedIndex}"]`);
            activeOption?.scrollIntoView({ block: "nearest" });
        }, [highlightedIndex, open]);

        function handleTriggerKeyDown(event: React.KeyboardEvent<HTMLButtonElement>) {
            if (disabled) {
                return;
            }

            if (event.key === "ArrowDown" || event.key === "ArrowUp") {
                event.preventDefault();
                setHighlightedIndex(event.key === "ArrowDown" ? selectedIndex : Math.max(selectedIndex - 1, 0));
                setOpen(true);
                return;
            }

            if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                setOpen((current) => !current);
            }
        }

        return (
            <>
                <button
                    ref={triggerRef}
                    type="button"
                    disabled={disabled}
                    aria-controls={`${selectId}-menu`}
                    aria-expanded={open}
                    aria-haspopup="listbox"
                    className={cn(
                        "group cursor-grab inline-flex w-full items-center justify-between border border-stone-700/80 bg-stone-950/70 text-left text-stone-100 shadow-[0_0_0_rgba(0,0,0,0)] outline-none transition-[border-color,background-color,box-shadow,transform,color] duration-450 ease-out x hover:border-stone-600 hover:bg-stone-950/88 hover:shadow-[0_12px_30px_rgba(0,0,0,0.16)] focus-visible:border-amber-300/60 focus-visible:bg-stone-950 focus-visible:shadow-[0_0_0_1px_rgba(252,211,77,0.2),0_18px_38px_rgba(0,0,0,0.24)] active:translate-y-0 disabled:cursor-not-allowed disabled:opacity-50",
                        sizeClasses[uiSize],
                        open && "border-amber-300/60 bg-stone-950 shadow-[0_0_0_1px_rgba(252,211,77,0.18),0_18px_38px_rgba(0,0,0,0.24)]",
                        className,
                    )}
                    onClick={() => {
                        updatePosition();
                        setOpen((current) => !current);
                    }}
                    onKeyDown={handleTriggerKeyDown}
                >
                    <span className="truncate">{selectedOption?.label ?? ""}</span>
                    <ChevronDown
                        className={cn(
                            "shrink-0 text-stone-500 transition-[transform,color] duration-150 ease-out group-hover:text-stone-300 group-focus-visible:text-amber-200",
                            uiSize === "sm" ? "size-3.5" : "size-4",
                            open && "translate-y-0.5 rotate-180 text-amber-200",
                        )}
                    />
                </button>

                {open &&
                    menuPosition &&
                    createPortal(
                        <div
                            id={`${selectId}-menu`}
                            ref={menuRef}
                            role="listbox"
                            aria-activedescendant={`${selectId}-option-${highlightedIndex}`}
                            className="animate-select-pop fixed z-[100] overflow-y-auto rounded-2xl border border-stone-700/90 bg-stone-950/96 p-1.5 shadow-[0_28px_80px_rgba(0,0,0,0.45)] backdrop-blur-xl"
                            style={{
                                left: menuPosition.left,
                                maxHeight: menuPosition.maxHeight,
                                top: menuPosition.top,
                                width: menuPosition.width,
                            }}
                        >
                            {options.map((option, index) => {
                                const selected = option.value === selectedOption?.value;
                                const highlighted = index === highlightedIndex;

                                return (
                                    <button
                                        key={option.value}
                                        id={`${selectId}-option-${index}`}
                                        data-option-index={index}
                                        type="button"
                                        role="option"
                                        aria-selected={selected}
                                        className={cn(
                                            "flex w-full items-center justify-between rounded-xl px-3 py-2 text-sm text-stone-200 transition-[background-color,color,transform] duration-150 ease-out",
                                            highlighted ? "bg-stone-800 text-stone-50" : "hover:bg-stone-900/80 hover:text-stone-50",
                                            uiSize === "sm" && "px-2.5 py-2 text-[11px] uppercase tracking-[0.14em]",
                                        )}
                                        onClick={() => {
                                            onValueChange(option.value);
                                            setOpen(false);
                                            triggerRef.current?.focus();
                                        }}
                                        onMouseEnter={() => setHighlightedIndex(index)}
                                    >
                                        <span className="truncate">{option.label}</span>
                                        <Check className={cn("size-4 transition-opacity duration-150", selected ? "opacity-100 text-amber-200" : "opacity-0")} />
                                    </button>
                                );
                            })}
                        </div>,
                        document.body,
                    )}
            </>
        );
    },
);

Select.displayName = "Select";

export { Select };
export type { SelectOption };
