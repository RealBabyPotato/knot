import * as React from "react"

export interface InputProps extends React.ComponentProps<"input"> {}

const Input = React.forwardRef<HTMLInputElement, InputProps>(
  ({ style, ...props }, ref) => {
    const inputStyles: React.CSSProperties = {
      display: "flex",
      height: "36px",
      width: "100%",
      borderRadius: "6px",
      border: "1px solid var(--color-border)",
      background: "transparent",
      padding: "0 12px",
      fontSize: "13px",
      color: "var(--color-foreground)",
      outline: "none",
      transition: "border-color 150ms",
      ...style,
    }
    
    return (
      <input
        style={inputStyles}
        ref={ref}
        {...props}
      />
    )
  }
)
Input.displayName = "Input"

export { Input }
