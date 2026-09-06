import { CaretLeft } from "@/components/icons"

import { countries, type CountryCode } from "@/app/demo-data"
import { BottomNavigation } from "@/components/BottomNavigation"
import { FlagIcon } from "@/components/FlagIcon"
import { HomeIndicator, StatusBar } from "@/components/StatusBar"

type CountriesScreenProps = {
  onBack: () => void
  onHome: () => void
  onSelect: (code: CountryCode) => void
}

export function CountriesScreen({ onBack, onHome, onSelect }: CountriesScreenProps) {
  return (
    <div data-testid="countries-screen" className="absolute inset-0 bg-[#101010] text-white">
      <StatusBar />
      <header className="absolute inset-x-0 top-11 z-10 flex h-[50px] items-center justify-center px-4">
        <button type="button" onClick={onBack} aria-label="Назад" className="absolute left-3 grid h-11 w-11 place-items-center rounded-full transition-transform active:scale-[.94]">
          <CaretLeft size={28} weight="regular" />
        </button>
        <h1 className="text-[16px] font-semibold tracking-[-0.02em]">За рубеж</h1>
      </header>

      <main className="absolute inset-x-[22px] bottom-[92px] top-[100px]">
        <section className="flex h-[468px] flex-col rounded-[25px] bg-[#1c1c1e] px-[15px] py-[10px]">
          <div className="flex-1">
            {countries.map((country) => (
              <button
                key={country.code}
                type="button"
                onClick={() => onSelect(country.code)}
                className="group flex h-[49px] w-full items-center gap-[15px] rounded-[16px] px-[1px] text-left transition-colors active:bg-white/[.045]"
              >
                <FlagIcon code={country.code} size="md" />
                <span className="text-[15px] tracking-[-0.02em]">{country.name}</span>
              </button>
            ))}
          </div>
          <button
            type="button"
            className="mt-2 h-[44px] shrink-0 rounded-[17px] bg-[#29292c] text-[15px] font-semibold transition-transform active:scale-[.985]"
          >
            Все страны
          </button>
        </section>
      </main>

      <BottomNavigation onHome={onHome} />
      <HomeIndicator />
    </div>
  )
}
