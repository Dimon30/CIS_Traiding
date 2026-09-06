import { getCountry, notificationScenarios, type CountryCode } from "@/app/demo-data"

export type NotificationScenario = {
  countryCode: CountryCode
  title: string
  pushText: string
  bannerText: string
}

export type ModelSignalDecision = {
  date: string
  corridor: string
  countryCode: CountryCode
  rateRubPerUnit: number
  score: number
  threshold: number
  signalType: string
  signalSpeed: string
  candidate: boolean
  send: boolean
  reasonCode: "send" | "cooldown" | "below_threshold"
  priority: number
}

export type SignalCalendarDay = {
  isoDate: string
  label: string
  monthKey: string
  monthLabel: string
  dayOfMonth: number
  isFuture: boolean
  isExpired: boolean
  notificationTimeLabel: string
  decisions: ModelSignalDecision[]
  scenario?: NotificationScenario
}

export type SignalCalendarSource = {
  runId: string
  datasetVersion: string | null
  gitCommit: string | null
  hypothesisId: string
  model: string
  strategy: string
  horizonDays: number
  epsilonBps: number
}

export type SignalCalendarDataset = {
  days: SignalCalendarDay[]
  source: SignalCalendarSource
  defaultMonthKey: string
}

type ModelSignalExport = {
  schemaVersion: 1
  source: SignalCalendarSource
  coverage: {
    from: string
    to: string
    decisionCount: number
    signalCount: number
  }
  signals: ModelSignalDecision[]
}

const dateFormatter = new Intl.DateTimeFormat("ru-RU", {
  day: "numeric",
  month: "long",
  year: "numeric",
})

const monthFormatter = new Intl.DateTimeFormat("ru-RU", { month: "long", year: "numeric" })
const monthNameFormatter = new Intl.DateTimeFormat("ru-RU", { month: "long" })
const preferredDefaultMonthKey = "2025-10"

const demoSchedule: Record<string, string[]> = {
  "2025-09": ["2025-09-02", "2025-09-19"],
  "2025-10": ["2025-10-04", "2025-10-09", "2025-10-22"],
  "2025-11": ["2025-11-06", "2025-11-18"],
}

const demoMeta: Record<string, { notificationTimeLabel: string; isExpired: boolean }> = {
  "2025-09-02": { notificationTimeLabel: "5 ч. назад", isExpired: true },
  "2025-09-19": { notificationTimeLabel: "сейчас", isExpired: false },
  "2025-10-04": { notificationTimeLabel: "6 ч. назад", isExpired: true },
  "2025-10-09": { notificationTimeLabel: "сейчас", isExpired: false },
  "2025-10-22": { notificationTimeLabel: "сейчас", isExpired: false },
  "2025-11-06": { notificationTimeLabel: "5 ч. назад", isExpired: true },
  "2025-11-18": { notificationTimeLabel: "сейчас", isExpired: false },
}

const demoText: Record<string, Omit<NotificationScenario, "countryCode">> = {
  "2025-09-02": { title: "Выгодный курс для перевода", pushText: "Сейчас курс на 2,1% выгоднее среднего за последний месяц.", bannerText: "Сейчас курс на 2,1% выгоднее среднего за последний месяц. За последнюю неделю он стал выгоднее ещё на 0,7%." },
  "2025-09-19": { title: "Курс становится выгоднее", pushText: "Курс становится выгоднее четвёртый день подряд.", bannerText: "Курс улучшается уже четвёртый день подряд. За это время он стал выгоднее на 1,2%." },
  "2025-10-04": { title: "Выгодный курс для перевода", pushText: "Сейчас курс на 2,4% выгоднее среднего за последний месяц.", bannerText: "Сейчас курс на 2,4% выгоднее среднего за последний месяц. За последнюю неделю он стал выгоднее ещё на 0,8%." },
  "2025-10-09": { title: "Курс становится выгоднее", pushText: "Курс становится выгоднее четвёртый день подряд.", bannerText: "Курс улучшается уже четвёртый день подряд. За это время он стал выгоднее на 1,4%." },
  "2025-10-22": { title: "Выгодный курс для перевода", pushText: "Сейчас курс на 1,9% выгоднее среднего за последний месяц.", bannerText: "Сейчас курс на 1,9% выгоднее среднего за последний месяц. За последнюю неделю он стал выгоднее ещё на 0,6%." },
  "2025-11-06": { title: "Курс становится выгоднее", pushText: "Курс становится выгоднее четвёртый день подряд.", bannerText: "Курс улучшается уже четвёртый день подряд. За это время он стал выгоднее на 1,1%." },
  "2025-11-18": { title: "Выгодный курс для перевода", pushText: "Сейчас курс на 2,3% выгоднее среднего за последний месяц.", bannerText: "Сейчас курс на 2,3% выгоднее среднего за последний месяц. За последнюю неделю он стал выгоднее ещё на 0,7%." },
}

function scenarioFor(decision: ModelSignalDecision, date: string): NotificationScenario {
  const prepared = notificationScenarios.find((scenario) => scenario.countryCode === decision.countryCode)
  if (prepared && !demoText[date]) return withMonthName(prepared, date)

  const country = getCountry(decision.countryCode)
  const fallback: NotificationScenario = {
    countryCode: decision.countryCode,
    title: "Выгодный момент для перевода",
    pushText: `Сейчас условия для перевода в ${country.destination} выглядят выгодно.`,
    bannerText: `Сейчас условия для перевода в ${country.destination} выглядят выгодно.`,
  }
  return withMonthName(demoText[date] ? { ...fallback, ...demoText[date] } : fallback, date)
}

function withMonthName(scenario: NotificationScenario, date: string): NotificationScenario {
  const monthName = monthNameFormatter.format(parseDate(date))
  const monthlyReference = `среднего за ${monthName}`

  return {
    ...scenario,
    pushText: scenario.pushText.replace("среднего за последний месяц", monthlyReference),
    bannerText: scenario.bannerText.replace("среднего за последний месяц", monthlyReference),
  }
}

function toIsoDate(date: Date) {
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, "0")
  const day = String(date.getDate()).padStart(2, "0")
  return `${year}-${month}-${day}`
}

function parseDate(value: string) {
  const parsed = new Date(`${value}T12:00:00`)
  if (Number.isNaN(parsed.getTime())) throw new Error(`Некорректная дата в model-signals.json: ${value}`)
  return parsed
}

function monthStart(date: Date, offset = 0) {
  return new Date(date.getFullYear(), date.getMonth() + offset, 1, 12)
}

function monthKey(date: Date) {
  return toIsoDate(date).slice(0, 7)
}

function selectSpread<T>(items: T[], count: number) {
  if (items.length <= count) return items
  if (count === 1) return [items[Math.floor(items.length / 2)]]

  const indexes = Array.from({ length: count }, (_, index) =>
    Math.round(index * (items.length - 1) / (count - 1)),
  )
  return indexes.map((index) => items[index])
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null
}

function readExport(value: unknown): ModelSignalExport {
  if (!isRecord(value) || value.schemaVersion !== 1) {
    throw new Error("Неподдерживаемая версия model-signals.json")
  }
  if (!isRecord(value.source) || !isRecord(value.coverage) || !Array.isArray(value.signals)) {
    throw new Error("Неполный контракт model-signals.json")
  }

  for (const decision of value.signals) {
    if (
      !isRecord(decision)
      || typeof decision.date !== "string"
      || typeof decision.corridor !== "string"
      || typeof decision.countryCode !== "string"
      || typeof decision.score !== "number"
      || typeof decision.threshold !== "number"
      || typeof decision.send !== "boolean"
      || typeof decision.candidate !== "boolean"
    ) {
      throw new Error("Некорректная строка решения в model-signals.json")
    }
  }

  return value as ModelSignalExport
}

export function createSignalCalendar(payload: ModelSignalExport, monthCount = 3): SignalCalendarDataset {
  const coverageStart = parseDate(payload.coverage.from)
  const coverageEnd = parseDate(payload.coverage.to)
  const allSignalsByDate = new Map<string, ModelSignalDecision[]>()

  for (const decision of payload.signals) {
    if (!decision.send) continue
    const signals = allSignalsByDate.get(decision.date) ?? []
    signals.push(decision)
    allSignalsByDate.set(decision.date, signals)
  }

  const signalDates = [...allSignalsByDate.keys()].sort()
  const centerIndex = Math.floor(monthCount / 2)
  const windowSatisfiesQuotas = (endMonth: Date) => Array.from({ length: monthCount }, (_, index) => {
    const key = monthKey(monthStart(endMonth, index - (monthCount - 1)))
    const quota = index === centerIndex ? 3 : 2
    return signalDates.filter((date) => date.startsWith(key)).length >= quota
  }).every(Boolean)

  const preferredDefaultMonth = parseDate(`${preferredDefaultMonthKey}-01`)
  let displayEndMonth = monthStart(preferredDefaultMonth, monthCount - centerIndex - 1)
  if (!windowSatisfiesQuotas(displayEndMonth)) {
    displayEndMonth = monthStart(coverageEnd)
  }
  for (let candidate = displayEndMonth; !windowSatisfiesQuotas(displayEndMonth) && candidate >= monthStart(coverageStart); candidate = monthStart(candidate, -1)) {
    if (windowSatisfiesQuotas(candidate)) {
      displayEndMonth = candidate
      break
    }
  }

  const signalsByDate = new Map<string, ModelSignalDecision[]>()
  for (let index = 0; index < monthCount; index += 1) {
    const key = monthKey(monthStart(displayEndMonth, index - (monthCount - 1)))
    const quota = index === centerIndex ? 3 : 2
    const sourceDates = selectSpread(signalDates.filter((date) => date.startsWith(key)), quota)
    const displayDates = demoSchedule[key] ?? sourceDates
    displayDates.forEach((displayDate, displayIndex) => {
      const sourceDate = sourceDates[displayIndex % Math.max(1, sourceDates.length)]
      const decisions = (allSignalsByDate.get(sourceDate) ?? []).map((decision) => ({ ...decision, date: displayDate }))
      signalsByDate.set(displayDate, decisions)
    })
  }

  const startDate = monthStart(displayEndMonth, -(monthCount - 1))
  const endDate = new Date(displayEndMonth.getFullYear(), displayEndMonth.getMonth() + 1, 0, 12)
  const days: SignalCalendarDay[] = []
  for (const cursor = new Date(startDate); cursor <= endDate; cursor.setDate(cursor.getDate() + 1)) {
    const isoDate = toIsoDate(cursor)
    const decisions = [...(signalsByDate.get(isoDate) ?? [])].sort(
      (left, right) => right.priority - left.priority || left.corridor.localeCompare(right.corridor),
    )
    const meta = demoMeta[isoDate]
    days.push({
      isoDate,
      label: dateFormatter.format(cursor),
      monthKey: isoDate.slice(0, 7),
      monthLabel: monthFormatter.format(cursor),
      dayOfMonth: cursor.getDate(),
      isFuture: false,
      isExpired: meta?.isExpired ?? false,
      notificationTimeLabel: meta?.notificationTimeLabel ?? "сейчас",
      decisions,
      scenario: decisions.length > 0 ? scenarioFor(decisions[0], isoDate) : undefined,
    })
  }

  return {
    days,
    source: payload.source,
    defaultMonthKey: monthKey(monthStart(displayEndMonth, centerIndex - (monthCount - 1))),
  }
}

export async function loadSignalCalendar(): Promise<SignalCalendarDataset> {
  const url = `${import.meta.env.BASE_URL}model-signals.json`
  const response = await fetch(url)
  if (!response.ok) throw new Error(`Не удалось загрузить ${url}: HTTP ${response.status}`)
  return createSignalCalendar(readExport(await response.json()))
}
