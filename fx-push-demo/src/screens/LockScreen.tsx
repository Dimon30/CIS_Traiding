import { Camera, Flashlight, LockSimple } from "@/components/icons"
import { AnimatePresence } from "motion/react"

import { HomeIndicator, IOSStatusIcons } from "@/components/StatusBar"
import { PushNotification } from "@/components/PushNotification"
import type { CountryCode } from "@/app/demo-data"

type LockScreenProps = {
  notificationVisible: boolean
  notificationRevealed: boolean
  scenario: {
    countryCode: CountryCode
    title: string
    body: string
  }
  notificationTimeLabel: string
  onReveal: (revealed: boolean) => void
  onOpen: () => void
}

export function LockScreen({
  notificationVisible,
  notificationRevealed,
  scenario,
  notificationTimeLabel,
  onReveal,
  onOpen,
}: LockScreenProps) {
  return (
    <div data-testid="lock-screen" className="lock-wallpaper absolute inset-0 overflow-hidden text-white">
      <div className="absolute left-[34px] top-[20px] text-[14px] font-semibold tracking-[-0.025em]">beeline</div>
      <div className="absolute left-1/2 top-[10px] grid h-[34px] w-[151px] -translate-x-1/2 place-items-center rounded-full bg-[#080808]">
        <LockSimple size={14} weight="fill" />
      </div>
      <div className="absolute right-[25px] top-[20px]">
        <IOSStatusIcons />
      </div>

      <div className="absolute inset-x-0 top-[72px] text-center">
        <p className="text-[17px] font-medium tracking-[-0.025em]">Thursday, 3 September</p>
        <p className="mt-[-2px] text-[70px] font-semibold leading-none tracking-[-0.055em]">17:42</p>
      </div>

      <AnimatePresence>
        {notificationVisible && (
          <PushNotification
            scenario={scenario}
            timeLabel={notificationTimeLabel}
            revealed={notificationRevealed}
            onReveal={onReveal}
            onOpen={onOpen}
          />
        )}
      </AnimatePresence>

      <div className="absolute bottom-[50px] left-[48px] grid h-[48px] w-[48px] place-items-center rounded-full bg-black/25 backdrop-blur-xl">
        <Flashlight size={22} weight="fill" />
      </div>
      <div className="absolute bottom-[50px] right-[48px] grid h-[48px] w-[48px] place-items-center rounded-full bg-black/25 backdrop-blur-xl">
        <Camera size={23} weight="fill" />
      </div>
      <HomeIndicator />
    </div>
  )
}
