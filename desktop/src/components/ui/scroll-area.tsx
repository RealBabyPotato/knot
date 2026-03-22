import * as React from "react"
import * as ScrollAreaPrimitive from "@radix-ui/react-scroll-area"

const ScrollArea = React.forwardRef<
  React.ElementRef<typeof ScrollAreaPrimitive.Root>,
  React.ComponentPropsWithoutRef<typeof ScrollAreaPrimitive.Root>
>(({ style, children, ...props }, ref) => (
  <ScrollAreaPrimitive.Root
    ref={ref}
    style={{ position: "relative", overflow: "hidden", ...style }}
    {...props}
  >
    <ScrollAreaPrimitive.Viewport style={{ height: "100%", width: "100%", borderRadius: "inherit" }}>
      {children}
    </ScrollAreaPrimitive.Viewport>
    <ScrollBar />
    <ScrollAreaPrimitive.Corner />
  </ScrollAreaPrimitive.Root>
))
ScrollArea.displayName = ScrollAreaPrimitive.Root.displayName

const ScrollBar = React.forwardRef<
  React.ElementRef<typeof ScrollAreaPrimitive.ScrollAreaScrollbar>,
  React.ComponentPropsWithoutRef<typeof ScrollAreaPrimitive.ScrollAreaScrollbar>
>(({ style, orientation = "vertical", ...props }, ref) => (
  <ScrollAreaPrimitive.ScrollAreaScrollbar
    ref={ref}
    orientation={orientation}
    style={{
      display: "flex",
      touchAction: "none",
      userSelect: "none",
      transition: "background 150ms",
      ...(orientation === "vertical" && {
        height: "100%",
        width: "10px",
        borderLeft: "1px solid transparent",
        padding: "1px",
      }),
      ...(orientation === "horizontal" && {
        height: "10px",
        flexDirection: "column",
        borderTop: "1px solid transparent",
        padding: "1px",
      }),
      ...style,
    }}
    {...props}
  >
    <ScrollAreaPrimitive.ScrollAreaThumb 
      style={{ 
        position: "relative", 
        flex: 1, 
        borderRadius: "9999px", 
        background: "var(--color-border)" 
      }} 
    />
  </ScrollAreaPrimitive.ScrollAreaScrollbar>
))
ScrollBar.displayName = ScrollAreaPrimitive.ScrollAreaScrollbar.displayName

export { ScrollArea, ScrollBar }
