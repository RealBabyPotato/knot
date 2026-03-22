import { useEffect, useId, useRef, useState } from "react";
import { Check, ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";

type SelectOption<T extends string> = {
  value: T;
  label: string;
  description?: string;
};

type SelectProps<T extends string> = {
  value: T;
  options: SelectOption<T>[];
  onChange: (value: T) => void;
  placeholder?: string;
  className?: string;
  menuClassName?: string;
  buttonClassName?: string;
  disabled?: boolean;
  align?: "left" | "right";
};

export function Select<T extends string>({
  value,
  options,
  onChange,
  placeholder,
  className,
  menuClassName,
  buttonClassName,
  disabled = false,
  align = "left",
}: SelectProps<T>) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement | null>(null);
  const buttonRef = useRef<HTMLButtonElement | null>(null);
  const listboxId = useId();
  const selected = options.find((option) => option.value === value);

  useEffect(() => {
    if (!open) {
      return;
    }

    function handlePointerDown(event: PointerEvent) {
      if (!rootRef.current?.contains(event.target as Node)) {
        setOpen(false);
      }
    }

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setOpen(false);
        buttonRef.current?.focus();
      }
    }

    window.addEventListener("pointerdown", handlePointerDown);
    window.addEventListener("keydown", handleKeyDown);
    return () => {
      window.removeEventListener("pointerdown", handlePointerDown);
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [open]);

  return (
    <div ref={rootRef} className={cn("relative", className)}>
      <button
        ref={buttonRef}
        type="button"
        disabled={disabled}
        aria-expanded={open}
        aria-haspopup="listbox"
        aria-controls={listboxId}
        onClick={() => setOpen((current) => !current)}
        className={cn(
          "group inline-flex h-10 w-full items-center justify-between gap-3 rounded-xl border border-stone-700/80 bg-stone-950/70 px-3 text-left text-sm text-stone-100 outline-none transition-all duration-200 ease-out hover:border-stone-600 hover:bg-stone-900 focus-visible:border-amber-300/60 focus-visible:ring-2 focus-visible:ring-amber-300/20 disabled:cursor-not-allowed disabled:opacity-50",
          open && "border-amber-300/45 bg-stone-900 shadow-[0_16px_40px_rgba(0,0,0,0.28)]",
          buttonClassName,
        )}
      >
        <span className="min-w-0 truncate text-sm text-stone-100">
          {selected?.label ?? placeholder ?? "Select"}
        </span>
        <ChevronDown
          className={cn(
            "size-4 shrink-0 text-stone-500 transition-all duration-200 ease-out group-hover:text-stone-300",
            open && "translate-y-[1px] rotate-180 text-amber-300",
          )}
        />
      </button>

      <div
        className={cn(
          "pointer-events-none absolute top-[calc(100%+0.5rem)] z-30 w-full origin-top rounded-2xl border border-stone-800/90 bg-stone-950/95 p-1.5 opacity-0 shadow-[0_24px_80px_rgba(0,0,0,0.42)] backdrop-blur-xl transition-all duration-200 ease-out",
          open && "pointer-events-auto translate-y-0 scale-100 opacity-100",
          !open && "-translate-y-1 scale-[0.98]",
          align === "right" && "right-0",
          align === "left" && "left-0",
          menuClassName,
        )}
      >
        <div
          id={listboxId}
          role="listbox"
          aria-activedescendant={selected?.value}
          className="max-h-72 overflow-y-auto"
        >
          {options.map((option) => {
            const active = option.value === value;

            return (
              <button
                key={option.value}
                id={option.value}
                type="button"
                role="option"
                aria-selected={active}
                onClick={() => {
                  onChange(option.value);
                  setOpen(false);
                }}
                className={cn(
                  "flex w-full items-center justify-between gap-3 rounded-xl px-3 py-2.5 text-left transition-all duration-150 ease-out",
                  active
                    ? "bg-stone-900 text-stone-50 shadow-[inset_0_0_0_1px_rgba(245,158,11,0.16)]"
                    : "text-stone-300 hover:bg-stone-900/80 hover:text-stone-100",
                )}
              >
                <span className="min-w-0">
                  <span className="block truncate text-sm">{option.label}</span>
                  {option.description && (
                    <span className="mt-0.5 block truncate text-xs text-stone-500">
                      {option.description}
                    </span>
                  )}
                </span>
                <Check
                  className={cn(
                    "size-4 shrink-0 transition-all duration-150",
                    active ? "scale-100 text-amber-300 opacity-100" : "scale-90 opacity-0",
                  )}
                />
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}
