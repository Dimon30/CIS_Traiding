import {
  ArrowsLeftRight,
  ChatCircleDots,
  ClockCounterClockwise,
  Heart,
  HouseSimple,
} from "@/components/icons"

type BottomNavigationProps = {
  onHome: () => void
}

const items = [
  { label: "Главный", icon: HouseSimple },
  { label: "Платежи", icon: ArrowsLeftRight },
  { label: "Выгода", icon: Heart, badge: "21" },
  { label: "История", icon: ClockCounterClockwise },
  { label: "Чаты", icon: ChatCircleDots },
]

export function BottomNavigation({ onHome }: BottomNavigationProps) {
  return (
    <nav className="absolute inset-x-0 bottom-0 z-20 h-[76px] border-t border-white/[.035] bg-[#101010]/95 px-2 pb-[14px] backdrop-blur-xl">
      <div className="grid h-full grid-cols-5 items-center">
        {items.map(({ label, icon: Icon, badge }, index) => (
          <button
            key={label}
            type="button"
            onClick={index === 0 ? onHome : undefined}
            aria-disabled={index !== 0}
            className={`relative flex h-full flex-col items-center justify-center gap-1.5 rounded-xl transition-transform active:scale-[.96] ${index === 0 ? "text-white" : "text-[#98989e]"}`}
          >
            <span className="relative">
              <Icon size={22} weight="fill" />
              {badge && (
                <span className="absolute -right-3 -top-2 grid h-[20px] min-w-[20px] place-items-center rounded-full bg-[#ff2d25] px-1 text-[9px] font-bold text-white">
                  {badge}
                </span>
              )}
            </span>
            <span className="text-[9px] leading-none">{label}</span>
          </button>
        ))}
      </div>
    </nav>
  )
}
