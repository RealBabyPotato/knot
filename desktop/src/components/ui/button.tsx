import * as React from "react"
import { Slot } from "@radix-ui/react-slot"

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  asChild?: boolean
  variant?: "default" | "destructive" | "outline" | "secondary" | "ghost" | "link"
  size?: "default" | "sm" | "lg" | "icon"
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className = "", variant = "default", size = "default", asChild = false, style, ...props }, ref) => {
    const Comp = asChild ? Slot : "button"
    
    const baseStyles: React.CSSProperties = {
      display: "inline-flex",
      alignItems: "center",
      justifyContent: "center",
      gap: "8px",
      whiteSpace: "nowrap",
      borderRadius: "6px",
      fontSize: "13px",
      fontWeight: 500,
      transition: "background 150ms, opacity 150ms",
      cursor: "pointer",
      border: "none",
    }
    
    const variantStyles: Record<string, React.CSSProperties> = {
      default: {
        background: "var(--color-primary)",
        color: "var(--color-primary-foreground)",
      },
      destructive: {
        background: "var(--color-destructive)",
        color: "var(--color-destructive-foreground)",
      },
      outline: {
        background: "transparent",
        border: "1px solid var(--color-border)",
        color: "var(--color-foreground)",
      },
      secondary: {
        background: "var(--color-secondary)",
        color: "var(--color-secondary-foreground)",
      },
      ghost: {
        background: "transparent",
        color: "var(--color-foreground)",
      },
      link: {
        background: "transparent",
        color: "var(--color-primary)",
        textDecoration: "underline",
      },
    }
    
    const sizeStyles: Record<string, React.CSSProperties> = {
      default: { height: "36px", padding: "0 16px" },
      sm: { height: "32px", padding: "0 12px", fontSize: "12px" },
      lg: { height: "40px", padding: "0 24px" },
      icon: { height: "36px", width: "36px", padding: 0 },
    }
    
    const combinedStyle: React.CSSProperties = {
      ...baseStyles,
      ...variantStyles[variant],
      ...sizeStyles[size],
      ...style,
    }
    
    return (
      <Comp
        style={combinedStyle}
        ref={ref}
        {...props}
      />
    )
  }
)
Button.displayName = "Button"

export { Button }
