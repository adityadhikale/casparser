import { useEffect, useState, type ReactNode } from 'react'
import { animate, motion, useReducedMotion } from 'motion/react'

export const ease = [0.22, 1, 0.36, 1] as const

/** Fade + rise on mount, with optional stagger delay (seconds). */
export function Reveal({ children, delay = 0, className, y = 14 }: { children: ReactNode; delay?: number; className?: string; y?: number }) {
  const reduce = useReducedMotion()
  return (
    <motion.div
      className={className}
      initial={reduce ? false : { opacity: 0, y }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, ease, delay }}
    >
      {children}
    </motion.div>
  )
}

/** Counts up to `value`, rendering through `format`. */
export function CountUp({ value, format }: { value: number; format: (n: number) => string }) {
  const reduce = useReducedMotion()
  const [n, setN] = useState(reduce ? value : 0)
  useEffect(() => {
    if (reduce) { setN(value); return }
    const c = animate(0, value, { duration: 1.1, ease, onUpdate: setN })
    return () => c.stop()
  }, [value, reduce])
  return <>{format(n)}</>
}
