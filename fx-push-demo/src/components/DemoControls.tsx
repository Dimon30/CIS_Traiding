import { HouseSimple, LockSimple } from "@/components/icons"

type DemoControlsProps = {
  onLock: () => void
  onHome: () => void
}

export function DemoControls({
  onLock,
  onHome,
}: DemoControlsProps) {
  return (
    <aside className="hidden w-[230px] rounded-[24px] border border-white/10 bg-[#19191b] p-4 text-white shadow-[0_24px_70px_rgba(0,0,0,.28)] lg:block">
      <p className="text-[11px] font-semibold uppercase tracking-[.12em] text-[#85858b]">Управление демо</p>
      <h1 className="mt-2 text-[18px] font-semibold tracking-[-0.025em]">Валютный сигнал</h1>
      <p className="mt-2 text-[13px] leading-5 text-[#a4a4aa]">
        Перейдите на экран блокировки или сразу откройте стартовый экран приложения.
      </p>
      <div className="mt-5 space-y-2">
        <ControlButton icon={<LockSimple size={17} weight="fill" />} label="Экран блокировки" onClick={onLock} />
        <ControlButton icon={<HouseSimple size={17} weight="fill" />} label="Экран старта" onClick={onHome} />
      </div>
      <p className="mt-5 border-t border-white/[.07] pt-4 text-[11px] leading-4 text-[#6f6f75]">
        Курсы и суммы в прототипе демонстрационные.
      </p>
    </aside>
  )
}

function ControlButton({ icon, label, onClick }: { icon: React.ReactNode; label: string; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="flex h-11 w-full items-center gap-2.5 rounded-[14px] bg-white/[.055] px-3 text-left text-[13px] transition-colors hover:bg-white/[.09] active:scale-[.985]"
    >
      <span className="text-[#c3c3c8]">{icon}</span>
      {label}
    </button>
  )
}
