import { getCountry, notificationScenarios, type CountryCode } from "@/app/demo-data"

export type NotificationScenario = {
  countryCode: CountryCode
  title: string
  body: string
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
  ageDays: number
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

function scenarioFor(decision: ModelSignalDecision): NotificationScenario {
  const prepared = notificationScenarios.find((scenario) => scenario.countryCode === decision.countryCode)
  if (prepared) return prepared

  const country = getCountry(decision.countryCode)
  return {
    countryCode: decision.countryCode,
    title: "Выгодный момент для перевода",
    body: `Модель отметила подходящий момент для перевода в ${country.destination}`,
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
  let displayEndMonth = monthStart(coverageEnd)
  for (let candidate = monthStart(coverageEnd); candidate >= monthStart(coverageStart); candidate = monthStart(candidate, -1)) {
    const quotasSatisfied = Array.from({ length: monthCount }, (_, index) => {
      const key = monthKey(monthStart(candidate, index - (monthCount - 1)))
      const quota = index === monthCount - 1 ? 3 : 2
      return signalDates.filter((date) => date.startsWith(key)).length >= quota
    }).every(Boolean)
    if (quotasSatisfied) {
      displayEndMonth = candidate
      break
    }
  }

  const signalsByDate = new Map<string, ModelSignalDecision[]>()
  for (let index = 0; index < monthCount; index += 1) {
    const key = monthKey(monthStart(displayEndMonth, index - (monthCount - 1)))
    const quota = index === monthCount - 1 ? 3 : 2
    const selectedDates = selectSpread(signalDates.filter((date) => date.startsWith(key)), quota)
    for (const date of selectedDates) signalsByDate.set(date, allSignalsByDate.get(date) ?? [])
  }

  const startDate = monthStart(displayEndMonth, -(monthCount - 1))
  const endDate = new Date(displayEndMonth.getFullYear(), displayEndMonth.getMonth() + 1, 0, 12)
  const latestSignalDate = parseDate([...signalsByDate.keys()].sort().at(-1) ?? toIsoDate(endDate))

  const days: SignalCalendarDay[] = []
  for (const cursor = new Date(startDate); cursor <= endDate; cursor.setDate(cursor.getDate() + 1)) {
    const isoDate = toIsoDate(cursor)
    const decisions = [...(signalsByDate.get(isoDate) ?? [])].sort(
      (left, right) => right.priority - left.priority || left.corridor.localeCompare(right.corridor),
    )
    const ageDays = Math.max(0, Math.round((latestSignalDate.getTime() - cursor.getTime()) / 86_400_000))
    days.push({
      isoDate,
      label: dateFormatter.format(cursor),
      monthKey: isoDate.slice(0, 7),
      monthLabel: monthFormatter.format(cursor),
      dayOfMonth: cursor.getDate(),
      isFuture: false,
      isExpired: decisions.length > 0 && ageDays > payload.source.horizonDays,
      ageDays,
      decisions,
      scenario: decisions.length > 0 ? scenarioFor(decisions[0]) : undefined,
    })
  }

  return { days, source: payload.source }
}

export async function loadSignalCalendar(): Promise<SignalCalendarDataset> {
  const url = `${import.meta.env.BASE_URL}model-signals.json`
  const response = await fetch(url)
  if (!response.ok) throw new Error(`Не удалось загрузить ${url}: HTTP ${response.status}`)
  return createSignalCalendar(readExport(await response.json()))
}
