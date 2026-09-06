import { useEffect, useMemo, useState } from "react"
import { AnimatePresence, motion, useReducedMotion } from "motion/react"

import { getCountry, notificationScenarios, type CountryCode } from "@/app/demo-data"
import {
  loadSignalCalendar,
  type NotificationScenario,
  type SignalCalendarDay,
  type SignalCalendarSource,
} from "@/app/signal-calendar-data"
import { DemoControls } from "@/components/DemoControls"
import { PhoneViewport } from "@/components/PhoneViewport"
import { SignalCalendar } from "@/components/SignalCalendar"
import { CountriesScreen } from "@/screens/CountriesScreen"
import { HomeScreen } from "@/screens/HomeScreen"
import { LockScreen } from "@/screens/LockScreen"
import { TransferScreen } from "@/screens/TransferScreen"

type Screen = "lock" | "home" | "countries" | "transfer"
type TransferOrigin = "push" | "countries"
type NavigationDirection = "forward" | "back"

export function DemoApp() {
  const reducedMotion = useReducedMotion()
  const [screen, setScreen] = useState<Screen>("lock")
  const [notificationVisible, setNotificationVisible] = useState(false)
  const [notificationRevealed, setNotificationRevealed] = useState(false)
  const [notificationScheduled, setNotificationScheduled] = useState(false)
  const [scenario, setScenario] = useState<NotificationScenario>(() => notificationScenarios[0])
  const [scenarioRevision, setScenarioRevision] = useState(0)
  const [calendarDays, setCalendarDays] = useState<SignalCalendarDay[]>([])
  const [calendarSource, setCalendarSource] = useState<SignalCalendarSource>()
  const [calendarError, setCalendarError] = useState<string>()
  const [selectedSignalDate, setSelectedSignalDate] = useState<string>()
  const [signalExpired, setSignalExpired] = useState(false)
  const [signalAgeDays, setSignalAgeDays] = useState(0)
  const [countryCode, setCountryCode] = useState<CountryCode>("TJ")
  const [transferOrigin, setTransferOrigin] = useState<TransferOrigin>("push")
  const [navigationDirection, setNavigationDirection] = useState<NavigationDirection>("forward")

  const country = useMemo(() => getCountry(countryCode), [countryCode])

  useEffect(() => {
    let cancelled = false
    loadSignalCalendar()
      .then((dataset) => {
        if (cancelled) return
        setCalendarDays(dataset.days)
        setCalendarSource(dataset.source)
        let latestSignalDay: SignalCalendarDay | undefined
        for (let index = dataset.days.length - 1; index >= 0; index -= 1) {
          if (dataset.days[index].monthKey === dataset.defaultMonthKey && dataset.days[index].scenario) {
            latestSignalDay = dataset.days[index]
            break
          }
        }
        if (latestSignalDay?.scenario) {
          setScenario(latestSignalDay.scenario)
          setNotificationScheduled(true)
          setSelectedSignalDate(latestSignalDay.isoDate)
          setSignalExpired(latestSignalDay.isExpired)
          setSignalAgeDays(latestSignalDay.ageDays)
        }
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setCalendarError(error instanceof Error ? error.message : "Не удалось загрузить сигналы")
        }
      })
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    if (screen !== "lock" || !notificationScheduled) return
    const timer = window.setTimeout(() => setNotificationVisible(true), reducedMotion ? 80 : 720)
    return () => window.clearTimeout(timer)
  }, [screen, scenarioRevision, notificationScheduled, reducedMotion])

  function openLockScreen() {
    setNotificationVisible(false)
    setNotificationRevealed(false)
    setNotificationScheduled(false)
    setScenarioRevision((current) => current + 1)
    setSelectedSignalDate(undefined)
    setSignalExpired(false)
    setSignalAgeDays(0)
    setScreen("lock")
    setTransferOrigin("push")
  }

  function selectSignalDay(day: SignalCalendarDay) {
    setNotificationVisible(false)
    setNotificationRevealed(false)
    if (day.scenario) setScenario(day.scenario)
    setNotificationScheduled(Boolean(day.scenario))
    setScenarioRevision((current) => current + 1)
    setSelectedSignalDate(day.isoDate)
    setSignalExpired(day.isExpired)
    setSignalAgeDays(day.ageDays)
    setTransferOrigin("push")
    setNavigationDirection("forward")
    setScreen("lock")
  }

  function openNotification() {
    setCountryCode(scenario.countryCode)
    setTransferOrigin("push")
    setNavigationDirection("forward")
    setScreen("transfer")
  }

  function openHome() {
    setTransferOrigin("countries")
    setNavigationDirection("back")
    setScreen("home")
  }

  function openCountries() {
    setNavigationDirection("forward")
    setScreen("countries")
  }

  function selectCountry(code: CountryCode) {
    setCountryCode(code)
    setTransferOrigin("countries")
    setNavigationDirection("forward")
    setScreen("transfer")
  }

  function backFromTransfer() {
    setNavigationDirection("back")
    setScreen(transferOrigin === "push" ? "home" : "countries")
  }

  return (
    <main className="relative min-h-[100dvh] overflow-hidden bg-[#0a0a0b]">
      <div className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2">
        <PhoneViewport>
          <AnimatePresence initial={false} mode="sync" custom={navigationDirection}>
            {screen === "lock" && (
              <motion.div key="lock" className="absolute inset-0" exit={{ opacity: 0, scale: 0.965 }} transition={{ duration: 0.26 }}>
                <LockScreen
                  notificationVisible={notificationVisible}
                  notificationRevealed={notificationRevealed}
                  scenario={scenario}
                  notificationAgeDays={signalAgeDays}
                  onReveal={setNotificationRevealed}
                  onOpen={openNotification}
                />
              </motion.div>
            )}

            {screen === "home" && (
              <ScreenSlide key="home" direction={navigationDirection}>
                <HomeScreen onOpenCountries={openCountries} onHome={openHome} />
              </ScreenSlide>
            )}

            {screen === "countries" && (
              <ScreenSlide key="countries" direction={navigationDirection}>
                <CountriesScreen onBack={openHome} onHome={openHome} onSelect={selectCountry} />
              </ScreenSlide>
            )}

            {screen === "transfer" && transferOrigin === "push" && (
              <AppOpenSlide key={`transfer-${country.code}-push`} reducedMotion={Boolean(reducedMotion)}>
                <TransferScreen
                  country={country}
                  signalText={scenario.body}
                  openedFromPush
                  signalExpired={signalExpired}
                  onBack={backFromTransfer}
                  onHome={openHome}
                />
              </AppOpenSlide>
            )}

            {screen === "transfer" && transferOrigin === "countries" && (
              <ScreenSlide key={`transfer-${country.code}-countries`} direction={navigationDirection}>
                <TransferScreen
                  country={country}
                  signalText={scenario.body}
                  openedFromPush={false}
                  signalExpired={false}
                  onBack={backFromTransfer}
                  onHome={openHome}
                />
              </ScreenSlide>
            )}
          </AnimatePresence>
        </PhoneViewport>
      </div>

      <div className="absolute right-[calc(50%+227px)] top-1/2 hidden -translate-y-1/2 xl:block">
        <SignalCalendar
          days={calendarDays}
          source={calendarSource}
          error={calendarError}
          selectedDate={selectedSignalDate}
          onSelect={selectSignalDay}
        />
      </div>

      <div className="absolute left-[calc(50%+227px)] top-1/2 hidden -translate-y-1/2 xl:block">
        <DemoControls
          onLock={openLockScreen}
          onHome={openHome}
        />
      </div>
    </main>
  )
}

function AppOpenSlide({ children, reducedMotion }: { children: React.ReactNode; reducedMotion: boolean }) {
  return (
    <motion.div
      className="absolute inset-0 z-[1] overflow-hidden bg-[#101010]"
      initial={reducedMotion ? { opacity: 0 } : { y: "100%", borderRadius: 42 }}
      animate={reducedMotion ? { opacity: 1 } : { y: 0, borderRadius: 0 }}
      exit="exit"
      variants={{
        exit: (direction: NavigationDirection) =>
          reducedMotion
            ? { opacity: 0 }
            : direction === "back"
              ? {
                  x: "100%",
                  opacity: 1,
                  zIndex: 2,
                  borderRadius: 30,
                  boxShadow: "-18px 0 36px rgba(0,0,0,.32)",
                }
              : { opacity: 0 },
      }}
      transition={reducedMotion ? { duration: 0.12 } : { type: "spring", stiffness: 175, damping: 24, mass: 0.82 }}
    >
      {children}
    </motion.div>
  )
}

const screenSlideVariants = {
  enter: (direction: NavigationDirection) =>
    direction === "forward"
      ? { opacity: 1, x: "100%", zIndex: 2, boxShadow: "-18px 0 36px rgba(0,0,0,.32)" }
      : { opacity: 1, x: 0, zIndex: 1, boxShadow: "none" },
  center: (direction: NavigationDirection) => ({
    opacity: 1,
    x: 0,
    zIndex: direction === "forward" ? 2 : 1,
    boxShadow: direction === "forward" ? "-18px 0 36px rgba(0,0,0,.32)" : "none",
  }),
  exit: (direction: NavigationDirection) =>
    direction === "back"
      ? { opacity: 1, x: "100%", zIndex: 2, boxShadow: "-18px 0 36px rgba(0,0,0,.32)" }
      : { opacity: 1, x: "-14%", zIndex: 1, boxShadow: "none" },
}

function ScreenSlide({ children, direction }: { children: React.ReactNode; direction: NavigationDirection }) {
  return (
    <motion.div
      className="absolute inset-0 will-change-transform"
      custom={direction}
      variants={screenSlideVariants}
      initial="enter"
      animate="center"
      exit="exit"
      transition={{ type: "spring", stiffness: 260, damping: 30, mass: 0.9 }}
    >
      {children}
    </motion.div>
  )
}
