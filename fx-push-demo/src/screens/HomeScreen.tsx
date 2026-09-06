import {
  ArrowsLeftRight,
  CaretDown,
  CaretRight,
  ContactlessPayment,
  MagnifyingGlass,
  Plus,
  QrCode,
  User,
  X,
} from "@/components/icons"

import { BottomNavigation } from "@/components/BottomNavigation"
import { HomeIndicator, StatusBar } from "@/components/StatusBar"

type HomeScreenProps = {
  onOpenCountries: () => void
  onHome: () => void
}

export function HomeScreen({ onOpenCountries, onHome }: HomeScreenProps) {
  return (
    <div data-testid="home-screen" className="absolute inset-0 bg-[#101010] text-white">
      <StatusBar time="17:39" />
      <div className="no-scrollbar absolute inset-x-0 bottom-[76px] top-11 overflow-y-auto overflow-x-hidden px-[18px]">
        <header className="flex items-center justify-between py-[20px]">
          <div className="flex items-center gap-3">
            <div className="grid h-[44px] w-[44px] place-items-center rounded-full bg-[#2a2a2d] text-[#96969b]">
              <User size={23} weight="fill" />
            </div>
            <span className="flex items-center gap-1 text-[19px] font-semibold">
              Илья <CaretRight size={17} weight="bold" className="text-[#8f8f95]" />
            </span>
          </div>
          <button type="button" className="rounded-full bg-[#9bea28] px-3 py-2 text-[13px] font-bold text-[#142008] transition-transform active:scale-[.97]">
            + 5 000 ₽
          </button>
        </header>

        <section className="flex h-[72px] items-center justify-between rounded-[22px] bg-[#27272a] px-[15px]">
          <div>
            <p className="text-[13px] text-[#98989d]">карта</p>
            <p className="mt-1 text-[17px] font-semibold tabular-nums tracking-[-0.015em]">4 695,37 ₽</p>
          </div>
          <div className="relative h-[41px] w-[62px] rounded-[10px] bg-[#f33329] p-2 text-[9px] font-bold">
            <span className="absolute left-2 top-1.5 border-b border-black text-black">A</span>
            <span className="absolute bottom-1.5 left-2">5775</span>
            <span className="absolute bottom-1.5 right-2 text-[8px] italic text-black">VISA</span>
          </div>
        </section>

        <section className="mt-2.5 h-[107px] overflow-hidden rounded-[22px] bg-[#27272a]">
          <div className="relative h-[70px] px-[15px] py-[13px]">
            <button type="button" aria-label="Закрыть предложение" className="absolute right-4 top-[14px] text-[#99999f]">
              <X size={19} weight="bold" />
            </button>
            <p className="text-[13px] text-[#9b9ba1]">Рекордно низкая ставка</p>
            <p className="mt-1 text-[18px]">До 7 500 000 ₽</p>
          </div>
          <div className="flex h-[37px] items-center bg-[#293148] px-[15px] text-[13px]">Возьмите кредит до 15.09</div>
        </section>

        <div className="flex h-[42px] items-center justify-center text-[#29292c]">
          <CaretDown size={38} weight="bold" />
        </div>

        <div className="-mx-[18px] mt-[-9px] rounded-t-[30px] bg-[#1b1b1d] px-[18px] pb-8 pt-[9px]">
          <section className="flex items-center gap-2">
            <div className="flex h-[50px] min-w-0 flex-1 items-center gap-3 rounded-full bg-[#29292c] px-4 text-[#85858b]">
              <MagnifyingGlass size={24} weight="bold" className="text-white" />
              <span className="text-[15px]">Поиск</span>
            </div>
            <button type="button" className="grid h-[50px] w-[50px] shrink-0 place-items-center rounded-full bg-[#29292c] transition-transform active:scale-[.96]">
              <QrCode size={25} weight="bold" />
            </button>
            <button type="button" className="grid h-[50px] w-[50px] shrink-0 place-items-center rounded-full bg-[#29292c] transition-transform active:scale-[.96]">
              <ContactlessPayment size={27} weight="bold" />
            </button>
          </section>

          <div className="no-scrollbar -mx-[18px] mt-2.5 flex gap-2 overflow-x-auto px-[18px] pb-1">
            <button type="button" className="flex shrink-0 items-center gap-2 rounded-full bg-[#26304a] px-4 py-[10px] text-[13px] transition-transform active:scale-[.97]">
              <Plus size={18} weight="bold" /> Новый продукт
            </button>
            <button type="button" className="shrink-0 rounded-full bg-[#29292c] px-4 py-[10px] text-[13px]">Платёжный стикер</button>
            <button type="button" className="shrink-0 rounded-full bg-[#29292c] px-4 py-[10px] text-[13px]">Кредитная карта</button>
          </div>

          <section className="mt-5">
            <h2 className="flex items-center text-[16px] font-semibold">Быстрые переводы <CaretRight size={17} weight="bold" className="text-[#8d8d93]" /></h2>
            <div className="no-scrollbar -mx-[18px] mt-3.5 flex gap-[18px] overflow-x-auto px-[18px] pb-2">
              <QuickItem icon={<div className="phone-transfer-mark"><span /></div>} label={<>По номеру<br />телефона</>} />
              <QuickItem icon={<ArrowsLeftRight size={30} weight="bold" />} label={<>Между<br />счетами</>} />
              <button type="button" onClick={onOpenCountries} className="w-[70px] shrink-0 text-center transition-transform active:scale-[.96]">
                <div className="relative mx-auto grid h-[58px] w-[58px] place-items-center rounded-full bg-[#2a2a2e]">
                  <InternationalTransferIcon />
                </div>
                <span className="mt-2 block text-[10px] leading-4">За рубеж</span>
              </button>
              <QuickItem icon={<User size={29} weight="fill" className="text-[#9a9aa0]" />} label="Себе" />
              <QuickItem icon={<span className="text-[16px] font-semibold text-[#ff6058]">ОВ</span>} label={<>Ольга<br />Викторовна</>} tone="warm" />
            </div>
          </section>

          <section className="mt-6">
            <h2 className="flex items-center text-[16px] font-semibold">Зарплата <CaretRight size={17} weight="bold" className="text-[#8d8d93]" /></h2>
            <div className="mt-3.5 grid grid-cols-[1.05fr_.95fr] gap-3">
              <div className="h-[132px] rounded-[23px] bg-[#83d8ff] p-4 text-[#101010]">
                <p className="text-[16px] font-semibold">Получайте<br />ещё больше</p>
                <p className="mt-2 text-[13px] text-[#48596a]">Привилегии<br />и предложения</p>
              </div>
              <div className="h-[132px] rounded-[23px] bg-[#27272a] p-4">
                <p className="text-[16px] font-semibold">Кэшбэк 5%</p>
                <p className="mt-2 text-[13px] leading-5 text-[#9b9ba1]">В топ-категории<br />каждый месяц</p>
              </div>
            </div>
          </section>
        </div>
      </div>
      <BottomNavigation onHome={onHome} />
      <HomeIndicator />
    </div>
  )
}

function QuickItem({ icon, label, tone = "neutral" }: { icon: React.ReactNode; label: React.ReactNode; tone?: "neutral" | "warm" }) {
  return (
    <button type="button" aria-disabled="true" className="w-[70px] shrink-0 text-center">
      <span className={`mx-auto grid h-[58px] w-[58px] place-items-center rounded-full ${tone === "warm" ? "bg-[#4a2927]" : "bg-[#2a2a2e]"}`}>{icon}</span>
      <span className="mt-2 block text-[10px] leading-4">{label}</span>
    </button>
  )
}

function InternationalTransferIcon() {
  return (
    <span aria-hidden="true" className="relative block h-[34px] w-[38px]">
      <span className="flag flag-kg absolute bottom-[1px] left-[1px] h-[18px] w-[28px] -rotate-[8deg] overflow-hidden rounded-[6px] shadow-[0_2px_5px_rgba(0,0,0,.35)]">
        <span className="flag-detail" />
      </span>
      <span className="flag flag-uz absolute right-0 top-0 h-[18px] w-[28px] rotate-[8deg] overflow-hidden rounded-[6px] shadow-[0_2px_5px_rgba(0,0,0,.35)]">
        <span className="flag-detail" />
      </span>
      <span className="flag flag-tj absolute left-[5px] top-[8px] h-[18px] w-[28px] overflow-hidden rounded-[6px] shadow-[0_2px_5px_rgba(0,0,0,.4)]">
        <span className="flag-detail" />
      </span>
    </span>
  )
}
