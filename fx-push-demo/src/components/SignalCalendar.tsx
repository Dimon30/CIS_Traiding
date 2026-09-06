import { useMemo, useState } from "react"

import type { SignalCalendarDay, SignalCalendarSource } from "@/app/signal-calendar-data"
import { CaretLeft, CaretRight } from "@/components/icons"

type SignalCalendarProps = {
  days: SignalCalendarDay[]
  source?: SignalCalendarSource
  error?: string
  selectedDate?: string
  onSelect: (day: SignalCalendarDay) => void
}

const weekdays = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]

export function SignalCalendar({ days, source, error, selectedDate, onSelect }: SignalCalendarProps) {
  const months = useMemo(() => {
    const uniqueMonths = new Map<string, string>()

    for (const day of days) {
      if (!uniqueMonths.has(day.monthKey)) uniqueMonths.set(day.monthKey, day.monthLabel)
    }

    return [...uniqueMonths].map(([key, label]) => ({ key, label }))
  }, [days])

  const [activeMonthKey, setActiveMonthKey] = useState<string>()
  const requestedMonthIndex = months.findIndex((month) => month.key === activeMonthKey)
  const activeMonthIndex = requestedMonthIndex >= 0 ? requestedMonthIndex : Math.floor(months.length / 2)
  const activeMonth = months[activeMonthIndex]
  const monthDays = days.filter((day) => day.monthKey === activeMonth?.key)
  const firstWeekday = monthDays[0] ? (new Date(`${monthDays[0].isoDate}T12:00:00`).getDay() + 6) % 7 : 0
  const totalCellCount = Math.max(35, Math.ceil((firstWeekday + monthDays.length) / 7) * 7)
  const calendarCells: Array<SignalCalendarDay | null> = [
    ...Array.from<null>({ length: firstWeekday }).fill(null),
    ...monthDays,
  ]

  while (calendarCells.length < totalCellCount) calendarCells.push(null)

  const signalCount = monthDays.filter((day) => day.scenario).length
  const canGoBack = activeMonthIndex > 0
  const canGoForward = activeMonthIndex < months.length - 1

  return (
    <aside
      data-testid="signal-calendar"
      className="w-[390px] rounded-[26px] border border-white/[.08] bg-[#19191b] p-5 text-white shadow-[0_24px_70px_rgba(0,0,0,.28)]"
    >
      <p className="text-[11px] font-semibold uppercase tracking-[.12em] text-[#85858b]">Календарь сигналов</p>

      <div className="mt-3 flex items-center justify-between">
        <h2 data-testid="calendar-month" className="capitalize text-[20px] font-semibold tracking-[-0.025em]">
          {activeMonth?.label ?? "Месяц"}
        </h2>
        <div className="flex gap-1.5">
          <MonthButton
            label="Предыдущий месяц"
            disabled={!canGoBack}
            onClick={() => setActiveMonthKey(months[Math.max(0, activeMonthIndex - 1)]?.key)}
          >
            <CaretLeft size={18} weight="bold" />
          </MonthButton>
          <MonthButton
            label="Следующий месяц"
            disabled={!canGoForward}
            onClick={() => setActiveMonthKey(months[Math.min(months.length - 1, activeMonthIndex + 1)]?.key)}
          >
            <CaretRight size={18} weight="bold" />
          </MonthButton>
        </div>
      </div>

      <p className="mt-2 text-[12px] leading-[1.45] text-[#96969c]">
        {error
          ? "Данные модели не загружены. Пересоберите экспорт и обновите страницу."
          : days.length === 0
            ? "Загружаем расписание сигналов модели…"
            : "Зелёный день — настоящий OOT-сигнал модели; текст пуша пока демонстрационный."}
      </p>

      <div className="mt-5 grid grid-cols-7 gap-1.5" aria-hidden="true">
        {weekdays.map((weekday) => (
          <span key={weekday} className="text-center text-[10px] font-medium text-[#74747a]">
            {weekday}
          </span>
        ))}
      </div>

      <div className="mt-2 grid grid-cols-7 gap-1.5">
        {calendarCells.map((day, index) => {
          if (!day) return <span key={`empty-${index}`} aria-hidden="true" className="h-[44px]" />

          const isSignal = Boolean(day.scenario)
          const isSelected = day.isoDate === selectedDate

          return (
            <button
              key={day.isoDate}
              type="button"
              disabled={day.isFuture}
              data-signal-day={isSignal ? "true" : "false"}
              aria-label={isSignal ? `${day.label}: ${day.scenario?.title}` : `${day.label}: сигнала нет`}
              title={isSignal ? `${day.label} — ${day.scenario?.title}` : day.label}
              onClick={() => onSelect(day)}
              className={`grid h-[44px] min-w-0 place-items-center rounded-[9px] border text-[11px] font-semibold tabular-nums transition-[transform,background-color,border-color] duration-200 ${
                isSignal
                  ? "border-[#56d364]/45 bg-[#39d353] text-[#071b0a] hover:border-[#8bea94] hover:bg-[#56d364] active:scale-[.9]"
                  : day.isFuture
                    ? "cursor-default border-white/[.025] bg-[#222225] text-[#515157]"
                    : "border-white/[.04] bg-[#2b2b2f] text-[#8b8b91] hover:border-white/[.09] hover:bg-[#343438] active:scale-[.9]"
              } ${isSelected ? "ring-2 ring-white/85 ring-offset-2 ring-offset-[#19191b]" : ""}`}
            >
              {day.dayOfMonth}
            </button>
          )
        })}
      </div>

      <div className="mt-5 flex items-center justify-between border-t border-white/[.065] pt-4 text-[10px] text-[#77777d]">
        <span>{signalCount} сигналов в этом месяце</span>
        <span className="flex items-center gap-2">
          <span>Нет</span>
          <span className="h-3.5 w-3.5 rounded-[4px] border border-white/[.04] bg-[#2b2b2f]" />
          <span className="h-3.5 w-3.5 rounded-[4px] border border-[#56d364]/45 bg-[#39d353]" />
          <span>Выгодно</span>
        </span>
      </div>
      {source ? (
        <p className="mt-3 truncate text-[9px] text-[#5f5f65]" title={`${source.runId} · ${source.model} · ${source.strategy}`}>
          {source.runId} · {source.model}
        </p>
      ) : null}
    </aside>
  )
}

function MonthButton({
  children,
  disabled,
  label,
  onClick,
}: {
  children: React.ReactNode
  disabled: boolean
  label: string
  onClick: () => void
}) {
  return (
    <button
      type="button"
      aria-label={label}
      disabled={disabled}
      onClick={onClick}
      className="grid h-9 w-9 place-items-center rounded-[11px] border border-white/[.06] bg-[#29292c] text-[#d2d2d6] transition-[transform,background-color] hover:bg-[#333337] active:scale-[.92] disabled:cursor-default disabled:opacity-30"
    >
      {children}
    </button>
  )
}
