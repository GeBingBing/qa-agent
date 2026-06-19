// 通用 Badge (shadcn/ui 风格)

import { type ReactNode } from 'react'
import { cn } from '@/lib/utils'

type BadgeVariant = 'default' | 'secondary' | 'outline' | 'destructive' | 'success' | 'warning'

const variants: Record<BadgeVariant, string> = {
  default: 'bg-primary text-primary-foreground',
  secondary: 'bg-secondary text-secondary-foreground',
  outline: 'border border-input bg-background',
  destructive: 'bg-destructive text-destructive-foreground',
  success: 'bg-emerald-600/20 text-emerald-400 border border-emerald-600/30',
  warning: 'bg-amber-600/20 text-amber-400 border border-amber-600/30',
}

interface BadgeProps {
  variant?: BadgeVariant
  children: ReactNode
  className?: string
}

export function Badge({ variant = 'default', children, className }: BadgeProps) {
  return (
    <span className={cn(
      'inline-flex items-center rounded-md px-2 py-0.5 text-xs font-medium',
      variants[variant],
      className,
    )}>
      {children}
    </span>
  )
}
