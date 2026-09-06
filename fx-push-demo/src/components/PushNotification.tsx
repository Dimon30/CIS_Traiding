import { useRef } from "react"
import { motion, useReducedMotion } from "motion/react"

import type { CountryCode } from "@/app/demo-data"
import { BrandMark } from "@/components/BrandMark"

type NotificationScenario = {
  countryCode: CountryCode
  title: string
  pushText: string
  bannerText: string
}

type PushNotificationProps = {
  scenario: NotificationScenario
  timeLabel: string
  revealed: boolean
  onReveal: (revealed: boolean) => void
  onOpen: () => void
}

export function PushNotification({ scenario, timeLabel, revealed, onReveal, onOpen }: PushNotificationProps) {
  const reducedMotion = useReducedMotion()
  const dragged = useRef(false)

  return (
    <motion.div
      className="absolute left-3 right-3 top-[332px] z-20 h-[116px]"
      initial={reducedMotion ? { opacity: 0 } : { opacity: 0, y: 28, scale: 0.97 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, y: 18, scale: 0.98 }}
      transition={{ type: "spring", stiffness: 220, damping: 24 }}
    >
      <button
        type="button"
        onClick={onOpen}
        disabled={!revealed}
        tabIndex={revealed ? 0 : -1}
        aria-hidden={!revealed}
        className="absolute left-0 top-0 grid h-full w-[78px] place-items-center rounded-[24px] border border-white/20 bg-[rgba(236,231,239,.77)] px-2 text-[12px] font-semibold text-[#17151b] shadow-[inset_0_1px_0_rgba(255,255,255,.6),0_8px_30px_rgba(50,25,72,.18)] backdrop-blur-[22px] transition-transform active:scale-[.96]"
      >
        Открыть
      </button>

      <motion.button
        type="button"
        drag="x"
        dragConstraints={{ left: 0, right: 78 }}
        dragElastic={0.08}
        onDragStart={() => {
          dragged.current = true
        }}
        onDragEnd={(_, info) => {
          onReveal(info.offset.x > 34 || info.velocity.x > 250)
          window.setTimeout(() => {
            dragged.current = false
          }, 0)
        }}
        onClick={() => {
          if (!dragged.current) onReveal(!revealed)
        }}
        animate={{ x: revealed ? 82 : 0 }}
        transition={reducedMotion ? { duration: 0.01 } : { duration: 0.56, ease: [0.22, 1, 0.36, 1] }}
        aria-label={revealed ? "Скрыть действие" : "Показать действие Открыть"}
        className="absolute inset-0 flex cursor-grab flex-col rounded-[24px] border border-white/20 bg-[rgba(236,231,239,.77)] p-[13px] text-left text-[#17151b] shadow-[inset_0_1px_0_rgba(255,255,255,.6),0_8px_30px_rgba(50,25,72,.18)] backdrop-blur-[22px] active:cursor-grabbing"
      >
        <div className="flex items-center gap-2">
          <BrandMark compact />
          <span className="text-[12px] font-semibold">Альфа-Банк</span>
          <span className="ml-auto text-[11px] text-black/45">{timeLabel}</span>
        </div>
        <strong className="mt-1.5 block text-[14px] font-semibold leading-tight tracking-[-0.015em]">
          {scenario.title}
        </strong>
        <span className="mt-0.5 line-clamp-2 text-[12px] leading-[1.25] text-black/75">
          {scenario.pushText}
        </span>
      </motion.button>
    </motion.div>
  )
}
