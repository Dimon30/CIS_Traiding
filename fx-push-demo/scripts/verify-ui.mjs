import { mkdir } from "node:fs/promises"
import path from "node:path"
import { fileURLToPath } from "node:url"

import { chromium } from "playwright-core"

const projectDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..")
const outputDir = path.join(projectDir, "verification")
const executablePath = "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"

await mkdir(outputDir, { recursive: true })

const browser = await chromium.launch({ executablePath, headless: true })
const page = await browser.newPage({ viewport: { width: 1280, height: 920 }, deviceScaleFactor: 1 })
const errors = []

page.on("console", (message) => {
  if (message.type() === "error") errors.push(`console: ${message.text()}`)
})
page.on("pageerror", (error) => errors.push(`page: ${error.message}`))

function assert(condition, message) {
  if (!condition) throw new Error(message)
}

async function capture(name) {
  await page.locator(".phone-viewport").screenshot({ path: path.join(outputDir, `${name}.png`) })
}

async function capturePage(name) {
  await page.screenshot({ path: path.join(outputDir, `${name}.png`), fullPage: true })
}

try {
  await page.goto("http://127.0.0.1:5173", { waitUntil: "networkidle" })
  assert((await page.locator("body").innerText()).trim().length > 0, "Страница пустая")
  assert((await page.locator(".vite-error-overlay").count()) === 0, "Обнаружен Vite error overlay")
  const signalCalendar = page.getByTestId("signal-calendar")
  await signalCalendar.waitFor({ state: "visible" })
  assert((await page.getByRole("button", { name: "Экран блокировки" }).count()) === 1, "Нет кнопки экрана блокировки")
  assert((await page.getByRole("button", { name: "Экран старта" }).count()) === 1, "Нет кнопки стартового экрана")
  assert((await page.getByText("Другой пуш", { exact: false }).count()) === 0, "Старая кнопка другого пуша не удалена")
  const calendarBox = await signalCalendar.boundingBox()
  assert(calendarBox && calendarBox.width >= 390, "Календарь отображается в уменьшенном размере")
  const initialMonth = await page.getByTestId("calendar-month").innerText()
  assert((await signalCalendar.innerText()).includes("3 сигналов в этом месяце"), "В открытом месяце должно быть 3 сигнала")
  const previousMonthButton = page.getByRole("button", { name: "Предыдущий месяц" })
  const nextMonthButton = page.getByRole("button", { name: "Следующий месяц" })
  await previousMonthButton.click()
  const previousMonth = await page.getByTestId("calendar-month").innerText()
  assert(previousMonth !== initialMonth, "Предыдущий месяц не открылся")
  assert((await signalCalendar.innerText()).includes("2 сигналов в этом месяце"), "В предыдущем месяце должно быть 2 сигнала")
  await previousMonthButton.click()
  assert((await signalCalendar.innerText()).includes("2 сигналов в этом месяце"), "В первом месяце должно быть 2 сигнала")
  assert(await previousMonthButton.isDisabled(), "Календарь содержит больше трёх месяцев")
  await nextMonthButton.click()
  await nextMonthButton.click()
  assert((await page.getByTestId("calendar-month").innerText()) === initialMonth, "Текущий месяц не восстановился")
  const phoneBox = await page.locator(".phone-viewport").boundingBox()
  const viewport = page.viewportSize()
  assert(phoneBox && viewport, "Не удалось определить геометрию страницы")
  assert(Math.abs(phoneBox.x + phoneBox.width / 2 - viewport.width / 2) < 1, "Телефон расположен не по центру браузера")

  const notification = page.getByRole("button", { name: "Показать действие Открыть" })
  await notification.waitFor({ state: "visible", timeout: 5000 })
  const expectedSignalText = await notification.locator("span").last().innerText()
  assert(expectedSignalText.length > 0, "У загруженного сигнала нет демонстрационного текста")
  assert((await signalCalendar.getByText("настоящий OOT-сигнал", { exact: false }).count()) === 1, "Календарь не подтвердил загрузку OOT-сигналов")
  assert((await signalCalendar.getByText("20260905_wave0_temporal_v3_baseline", { exact: false }).count()) === 1, "Не показан источник model export")
  await capturePage("00-desktop-layout")
  await capture("01-lock-notification")

  await notification.click()
  await page.getByRole("button", { name: "Скрыть действие" }).waitFor({ state: "visible" })
  await page.waitForTimeout(650)
  await capture("02-notification-action")

  await page.getByRole("button", { name: "Открыть", exact: true }).click()
  await page.getByTestId("transfer-screen").waitFor({ state: "visible", timeout: 5000 })
  await page.getByTestId("active-signal").waitFor({ state: "visible" })
  await page.waitForTimeout(650)
  assert((await page.getByText(expectedSignalText, { exact: true }).count()) === 1, "Текст выгодного момента не совпал с уведомлением")
  await capture("03-push-transfer")

  await page.getByRole("button", { name: "Назад" }).click()
  await page.getByText("Быстрые переводы").waitFor({ state: "visible" })
  await page.waitForTimeout(650)
  await capture("04-home")

  await page.getByRole("button", { name: "За рубеж", exact: true }).click()
  await page.getByTestId("countries-screen").waitFor({ state: "attached" })
  await page.waitForTimeout(20)
  const forwardBox = await page.getByTestId("countries-screen").boundingBox()
  assert(forwardBox && forwardBox.x > phoneBox.x + 20, "Прямой экран не появился справа")
  await page.waitForTimeout(650)
  await capture("05-countries")

  await page.getByRole("button", { name: "Назад" }).click()
  await page.getByTestId("home-screen").waitFor({ state: "attached" })
  await page.waitForTimeout(20)
  const backBox = await page.getByTestId("home-screen").boundingBox()
  const exitingCountriesBox = await page.getByTestId("countries-screen").boundingBox()
  assert(backBox && Math.abs(backBox.x - phoneBox.x) < 5, "Предыдущий экран сместился во время возврата")
  assert(exitingCountriesBox && exitingCountriesBox.x > phoneBox.x + 20, "Текущий экран не ушёл вправо при возврате")
  await page.waitForTimeout(650)
  await page.getByRole("button", { name: "За рубеж", exact: true }).click()
  await page.getByTestId("countries-screen").waitFor({ state: "visible" })
  await page.waitForTimeout(650)

  await page.getByRole("button", { name: "Кыргызстан", exact: true }).click()
  await page.getByRole("heading", { name: "В Кыргызстан" }).waitFor({ state: "visible" })
  await page.waitForTimeout(650)
  await page.getByLabel("Сумма перевода в рублях").fill("12000")
  assert((await page.getByText("12 564", { exact: false }).count()) > 0, "Пересчёт KGS не сработал")
  await capture("06-kyrgyzstan-transfer")

  await page.getByRole("button", { name: "Продолжить" }).click()
  await page.getByRole("dialog", { name: "Перевод подготовлен" }).waitFor({ state: "visible" })
  await page.waitForTimeout(500)
  await capture("07-confirmation")

  await page.getByRole("button", { name: "Готово" }).click()
  await page.getByText("Быстрые переводы").waitFor({ state: "visible" })
  await page.waitForTimeout(650)
  await page.getByRole("button", { name: "За рубеж", exact: true }).click()
  await page.getByRole("heading", { name: "За рубеж" }).waitFor({ state: "visible" })
  await page.waitForTimeout(650)

  const countryFlows = [
    ["Таджикистан", "В Таджикистан"],
    ["Узбекистан", "В Узбекистан"],
    ["Кыргызстан", "В Кыргызстан"],
    ["Казахстан", "В Казахстан"],
    ["Армения", "В Армению"],
    ["Беларусь", "В Беларусь"],
    ["Азербайджан", "В Азербайджан"],
    ["Китай", "В Китай"],
  ]

  for (const [countryName, transferTitle] of countryFlows) {
    await page.getByRole("button", { name: countryName, exact: true }).click()
    await page.getByRole("heading", { name: transferTitle }).waitFor({ state: "visible" })
    await page.waitForTimeout(650)
    await page.getByRole("button", { name: "Назад" }).click()
    await page.getByRole("heading", { name: "За рубеж" }).waitFor({ state: "visible" })
    await page.waitForTimeout(650)
  }

  await previousMonthButton.click()
  const oldSignalDay = page.locator('[data-signal-day="true"]').first()
  const signalLabel = await oldSignalDay.getAttribute("aria-label")
  assert(signalLabel, "У календарного сигнала нет описания")
  const expectedTitle = signalLabel.slice(signalLabel.indexOf(": ") + 2)
  await oldSignalDay.click()
  const oldNotification = page.getByRole("button", { name: "Показать действие Открыть" })
  await oldNotification.waitFor({ state: "visible", timeout: 5000 })
  assert((await page.getByText(expectedTitle, { exact: true }).count()) === 1, "Уведомление не соответствует выбранному дню")
  assert((await oldSignalDay.getAttribute("class"))?.includes("ring-2"), "Выбранный день не подсвечен")
  assert((await page.getByText("дн. назад", { exact: false }).count()) > 0, "У старого пуша не показан возраст")
  await oldNotification.click()
  await page.getByRole("button", { name: "Открыть", exact: true }).click()
  await page.getByTestId("expired-signal").waitFor({ state: "visible" })
  assert((await page.getByText("Курс уже обновился", { exact: true }).count()) === 1, "Просроченный пуш не перепроверен")
  await page.waitForTimeout(650)
  await capturePage("08-expired-notification")

  const ordinaryDay = page.locator('[data-signal-day="false"]:not(:disabled)').first()
  await ordinaryDay.click()
  await page.getByTestId("lock-screen").waitFor({ state: "visible" })
  await page.waitForTimeout(850)
  assert((await page.getByRole("button", { name: "Показать действие Открыть" }).count()) === 0, "В обычный день появилось уведомление")
  assert((await ordinaryDay.getAttribute("class"))?.includes("ring-2"), "Обычный выбранный день не подсвечен")

  assert(errors.length === 0, `Ошибки браузера:\n${errors.join("\n")}`)
  process.stdout.write("UI verification passed: centered phone, interactive signal calendar, navigation motion, calculation, confirmation, and all 8 countries\n")
} finally {
  await browser.close()
}
