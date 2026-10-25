import * as React from "react"
import { cn } from "cn"

function Textarea({ className, ...props }: React.ComponentProps<"textarea">) {
  return (
    <textarea
      data-slot="textarea"
      className={cn(
        "flex field-sizing-content min-h-16 w-full rounded-md border border-input bg-background px-3 py-2 text-sm text-foreground transition-colors outline-none placeholder:text-tertiary focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-ring disabled:cursor-not-allowed disabled:bg-muted disabled:text-tertiary aria-invalid:border-critical",
        className
      )}
      {...props}
    />
  )
}

export { Textarea }
