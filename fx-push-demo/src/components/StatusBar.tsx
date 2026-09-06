type StatusBarProps = {
  time?: string
}

export function StatusBar({ time = "18:15" }: StatusBarProps) {
  return (
    <div className="pointer-events-none absolute inset-x-0 top-0 z-20 flex h-11 items-center justify-between pl-[52px] pr-[28px] text-white">
      <span className="text-[15px] font-semibold tracking-[-0.02em]">{time}</span>
      <IOSStatusIcons />
    </div>
  )
}

export function IOSStatusIcons() {
  return (
    <svg
      aria-hidden="true"
      className="h-[14px] w-[78px] shrink-0 overflow-visible"
      viewBox="0 0 74 14"
      fill="none"
    >
      <g fill="currentColor">
        <rect x="0" y="9" width="3" height="5" rx="1" />
        <rect x="5" y="6.5" width="3" height="7.5" rx="1" />
        <rect x="10" y="3.5" width="3" height="10.5" rx="1" />
        <rect x="15" y="0" width="3" height="14" rx="1" opacity=".28" />
      </g>
      <g stroke="currentColor" strokeWidth="1.8" strokeLinecap="round">
        <path d="M25 4.25c5.15-4 11.65-4 16.8 0" />
        <path d="M28.2 7.35c3.2-2.5 7.2-2.5 10.4 0" />
        <path d="M31.45 10.35c1.2-.9 2.7-.9 3.9 0" />
      </g>
      <g transform="translate(49 1)">
        <rect width="21" height="12" rx="3.5" stroke="currentColor" strokeOpacity=".45" />
        <rect x="2" y="2" width="4" height="8" rx="2" fill="#ff453a" />
        <path d="M22.4 4.25v3.5" stroke="currentColor" strokeOpacity=".45" strokeWidth="1.5" strokeLinecap="round" />
      </g>
    </svg>
  )
}

export function HomeIndicator() {
  return <div className="pointer-events-none absolute bottom-[6px] left-1/2 z-30 h-[4px] w-[138px] -translate-x-1/2 rounded-full bg-white" />
}
