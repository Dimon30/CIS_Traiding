import type { ReactNode } from "react"

type PhoneViewportProps = {
  children: ReactNode
}

export function PhoneViewport({ children }: PhoneViewportProps) {
  return (
    <div className="phone-viewport relative isolate aspect-[390/844] w-[min(390px,calc((100dvh-32px)*.4621),calc(100vw-24px))] overflow-hidden bg-[#101010] shadow-[0_32px_100px_rgba(0,0,0,.5)] md:rounded-[38px] md:ring-1 md:ring-white/10">
      {children}
    </div>
  )
}
