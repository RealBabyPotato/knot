import * as React from "react";
import { cn } from "@/lib/utils";

export interface InputProps extends React.ComponentProps<"input"> {}

const Input = React.forwardRef<HTMLInputElement, InputProps>(({ className, ...props }, ref) => (
  <input
    ref={ref}
    className={cn(
      "flex h-10 w-full rounded-xl border border-stone-700/80 bg-stone-950/70 px-3 text-sm text-stone-100 transition-colors duration-150 outline-none placeholder:text-stone-500 focus:border-amber-300/60 focus:ring-2 focus:ring-amber-300/20 disabled:cursor-not-allowed disabled:opacity-50",
      className,
    )}
    {...props}
  />
));
Input.displayName = "Input";

export { Input };
