import { useMemo, useState } from "react"
import {
  CaretDown,
  CaretLeft,
  CheckCircle,
  ClockCounterClockwise,
  Info,
  Sparkle,
  UserPlus,
  Wallet,
} from "@/components/icons"
import { AnimatePresence, motion } from "motion/react"

import type { Country } from "@/app/demo-data"
import { formatReceived } from "@/app/demo-data"
import { BottomNavigation } from "@/components/BottomNavigation"
import { FlagIcon } from "@/components/FlagIcon"
import { HomeIndicator, StatusBar } from "@/components/StatusBar"

type TransferScreenProps = {
  country: Country
  signalText: string
  openedFromPush: boolean
  signalExpired: boolean
  onBack: () => void
  onHome: () => void
}

export function TransferScreen({ country, signalText, openedFromPush, signalExpired, onBack, onHome }: TransferScreenProps) {
  const [amount, setAmount] = useState(5000)
  const [recipient, setRecipient] = useState(country.lastRecipient)
  const [confirmed, setConfirmed] = useState(false)

  const received = useMemo(() => formatReceived(amount, country.rate), [amount, country.rate])
  const formattedAmount = new Intl.NumberFormat("ru-RU").format(amount)

  return (
    <div data-testid="transfer-screen" className="absolute inset-0 bg-[#101010] text-white">
      <StatusBar time="17:40" />
      <header className="absolute inset-x-0 top-11 z-10 flex h-[50px] items-center justify-center px-4">
        <button type="button" onClick={onBack} aria-label="Назад" className="absolute left-3 grid h-11 w-11 place-items-center rounded-full transition-transform active:scale-[.94]">
          <CaretLeft size={28} />
        </button>
        <h1 className="text-[16px] font-semibold tracking-[-0.02em]">В {country.destination}</h1>
      </header>

      <main className="no-scrollbar absolute inset-x-0 bottom-[76px] top-[96px] overflow-y-auto px-[18px] pb-[28px]">
        <section className="rounded-[23px] bg-[#1c1c1e] px-[16px] py-[14px]">
          <div className="flex items-center gap-3 border-b border-white/[.055] pb-[14px]">
            <div className="grid h-[45px] w-[45px] place-items-center rounded-[14px] bg-[#28282b] text-[#aaaab0]">
              <Wallet size={23} weight="fill" />
            </div>
            <div className="min-w-0 flex-1">
              <p className="text-[15px] font-semibold tabular-nums tracking-[-0.01em]">4 695,37 ₽</p>
              <p className="text-[13px] text-[#a1a1a7]">карта ··9284</p>
            </div>
            <CaretDown size={19} weight="bold" className="text-[#55555a]" />
          </div>

          <label className="mt-[14px] flex items-center gap-3">
            <span className="grid h-[45px] w-[45px] shrink-0 place-items-center rounded-[14px] bg-[#28282b] text-[#a3a3a8]">
              <UserPlus size={24} />
            </span>
            <span className="min-w-0 flex-1">
              <span className="block text-[11px] text-[#85858b]">Получатель</span>
              <input
                value={recipient}
                onChange={(event) => setRecipient(event.target.value)}
                aria-label="Номер получателя"
                className="mt-0.5 w-full bg-transparent text-[14px] text-white outline-none placeholder:text-[#737379]"
                placeholder={`${country.phonePrefix} Номер телефона`}
              />
            </span>
            <CaretDown size={19} weight="bold" className="text-[#55555a]" />
          </label>
        </section>

        <p className="mt-3 px-1 text-[13px] text-[#85858b]">Зачисление происходит моментально</p>

        {openedFromPush && (
          <section
            data-testid={signalExpired ? "expired-signal" : "active-signal"}
            className={`mt-5 rounded-[20px] border px-[15px] py-[13px] shadow-[inset_0_1px_0_rgba(255,255,255,.04)] ${
              signalExpired ? "border-[#f2b84b]/25 bg-[#292319]" : "border-[#ef3124]/25 bg-[#291a1a]"
            }`}
          >
            <div className="flex items-start gap-3">
              <span className={`grid h-9 w-9 shrink-0 place-items-center rounded-full text-white ${signalExpired ? "bg-[#b77a16]" : "bg-[#ef3124]"}`}>
                {signalExpired ? <ClockCounterClockwise size={18} weight="bold" /> : <Sparkle size={18} weight="fill" />}
              </span>
              <div>
                <p className="text-[14px] font-semibold">{signalExpired ? "Курс уже обновился" : "Выгодный момент"}</p>
                <p className={`mt-1 text-[12px] leading-[1.35] ${signalExpired ? "text-[#c9bea9]" : "text-[#c7b9b9]"}`}>
                  {signalExpired
                    ? "Сигнал был актуален в момент отправки. Показываем текущий курс — проверьте сумму перед переводом."
                    : signalText}
                </p>
              </div>
            </div>
          </section>
        )}

        <section className="mt-5 grid grid-cols-2 gap-2.5">
          <label className="rounded-[20px] bg-[#1c1c1e] px-[14px] py-[13px]">
            <span className="block text-[12px] text-[#8e8e94]">Отправите</span>
            <span className="mt-2 flex items-baseline gap-1">
              <input
                value={formattedAmount}
                onChange={(event) => {
                  const next = Number(event.target.value.replace(/\D/g, ""))
                  setAmount(Number.isFinite(next) ? Math.min(next, 250000) : 0)
                }}
                inputMode="numeric"
                aria-label="Сумма перевода в рублях"
                className="min-w-0 flex-1 bg-transparent text-[17px] font-semibold tabular-nums tracking-[-0.01em] outline-none"
              />
              <span className="text-[15px] text-[#a1a1a7]">₽</span>
            </span>
          </label>
          <div className="rounded-[20px] bg-[#1c1c1e] px-[14px] py-[13px]">
            <span className="block text-[12px] text-[#8e8e94]">Получит</span>
            <p className="mt-2 truncate text-[17px] font-semibold tabular-nums tracking-[-0.01em]">
              {received} <span className="text-[15px] text-[#a1a1a7]">{country.currency}</span>
            </p>
          </div>
        </section>

        <section className="mt-2.5 rounded-[20px] bg-[#1c1c1e] px-[14px] py-[12px]">
          <div className="flex items-center gap-2 text-[12px] text-[#99999f]">
            <FlagIcon code={country.code} size="sm" />
            <span>1 ₽ = {country.rate.toLocaleString("ru-RU")} {country.currency}</span>
            <Info size={15} weight="fill" className="ml-auto" />
          </div>
        </section>

        <label className="mt-5 block">
          <span className="sr-only">Сообщение получателю</span>
          <input
            className="h-[51px] w-full rounded-[17px] bg-[#1c1c1e] px-[15px] text-[15px] outline-none placeholder:text-[#85858b]"
            placeholder="Ваше сообщение"
            maxLength={140}
          />
          <span className="mt-2 block px-1 text-[12px] text-[#85858b]">Максимум 140 символов</span>
        </label>

        <button
          type="button"
          disabled={!amount || !recipient.trim()}
          onClick={() => setConfirmed(true)}
          className="mt-6 h-[52px] w-full rounded-[17px] bg-[#ef3124] text-[15px] font-semibold text-white transition-transform active:scale-[.985] disabled:bg-[#2a2a2d] disabled:text-[#626268]"
        >
          Продолжить
        </button>

        <p className="mt-3 flex items-center gap-1.5 px-1 text-[12px] text-[#77777d]">
          Комиссия и лимиты <Info size={14} weight="fill" />
        </p>
      </main>

      <AnimatePresence>
        {confirmed && (
          <motion.div
            className="absolute inset-0 z-40 flex items-end bg-black/55 p-3 backdrop-blur-[3px]"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={() => setConfirmed(false)}
          >
            <motion.section
              role="dialog"
              aria-modal="true"
              aria-label="Перевод подготовлен"
              initial={{ y: "110%" }}
              animate={{ y: 0 }}
              exit={{ y: "110%" }}
              transition={{ type: "spring", stiffness: 260, damping: 28 }}
              onClick={(event) => event.stopPropagation()}
              className="w-full rounded-[28px] bg-[#242426] px-5 pb-7 pt-6 text-center shadow-[inset_0_1px_0_rgba(255,255,255,.08)]"
            >
              <CheckCircle size={48} weight="fill" className="mx-auto text-[#73d465]" />
              <h2 className="mt-3 text-[20px] font-semibold">Перевод подготовлен</h2>
              <p className="mt-2 text-[14px] leading-5 text-[#aaaab0]">
                {formattedAmount} ₽ → {received} {country.currency}
              </p>
              <button type="button" onClick={onHome} className="mt-5 h-[50px] w-full rounded-[16px] bg-white text-[15px] font-semibold text-[#151515] transition-transform active:scale-[.985]">
                Готово
              </button>
            </motion.section>
          </motion.div>
        )}
      </AnimatePresence>

      <BottomNavigation onHome={onHome} />
      <HomeIndicator />
    </div>
  )
}
