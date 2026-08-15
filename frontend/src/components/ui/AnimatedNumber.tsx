import { useEffect, useRef } from 'react'
import { animate, useMotionValue, useTransform, motion } from 'framer-motion'

export function AnimatedNumber({ value }: { value: number }) {
  const motionValue = useMotionValue(0)
  const rounded = useTransform(motionValue, (v) => Math.round(v).toLocaleString())
  const hasMounted = useRef(false)

  useEffect(() => {
    const controls = animate(motionValue, value, {
      duration: hasMounted.current ? 0.6 : 0.8,
      ease: 'easeOut',
    })
    hasMounted.current = true
    return () => controls.stop()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value])

  return <motion.span>{rounded}</motion.span>
}
