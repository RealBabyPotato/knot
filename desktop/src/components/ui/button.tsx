import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cn } from "@/lib/utils";

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  asChild?: boolean;
  variant?: "default" | "destructive" | "outline" | "secondary" | "ghost" | "link";
  size?: "default" | "sm" | "lg" | "icon";
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant = "default", size = "default", asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : "button";

    const variantClasses: Record<NonNullable<ButtonProps["variant"]>, string> = {
      default: "border-transparent bg-amber-300 text-stone-950 shadow-sm hover:bg-amber-200",
      destructive: "border-transparent bg-rose-500 text-white shadow-sm hover:bg-rose-400",
      outline: "border-stone-700/80 bg-stone-950/70 text-stone-100 hover:bg-stone-900",
      secondary: "border-transparent bg-stone-800 text-stone-100 hover:bg-stone-700",
      ghost: "border-transparent bg-transparent text-stone-300 hover:bg-stone-900 hover:text-stone-100",
      link: "border-transparent bg-transparent px-0 text-amber-300 underline-offset-4 hover:underline",
    };

    const sizeClasses: Record<NonNullable<ButtonProps["size"]>, string> = {
      default: "h-10 px-4",
      sm: "h-9 rounded-lg px-3 text-xs",
      lg: "h-11 px-6 text-sm",
      icon: "size-10",
    };

    return (
      <Comp
        ref={ref}
        className={cn(
          "inline-flex shrink-0 items-center justify-center gap-2 whitespace-nowrap rounded-xl border text-sm font-medium transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-300/60 focus-visible:ring-offset-2 focus-visible:ring-offset-stone-950 disabled:pointer-events-none disabled:opacity-50",
          variantClasses[variant],
          sizeClasses[size],
          className,
        )}
        {...props}
      />
    );
  },
);
Button.displayName = "Button";

export { Button };
