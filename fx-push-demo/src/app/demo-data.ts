export type CountryCode = "TJ" | "UZ" | "KG" | "KZ" | "AM" | "BY" | "AZ" | "CN"

export type Country = {
  code: CountryCode
  name: string
  destination: string
  currency: string
  currencyName: string
  rate: number
  phonePrefix: string
  lastRecipient: string
}

export const countries: Country[] = [
  { code: "TJ", name: "Таджикистан", destination: "Таджикистан", currency: "TJS", currencyName: "сомони", rate: 0.119, phonePrefix: "+992", lastRecipient: "+992 93 512 48 06" },
  { code: "UZ", name: "Узбекистан", destination: "Узбекистан", currency: "UZS", currencyName: "сумов", rate: 146.83, phonePrefix: "+998", lastRecipient: "+998 90 742 16 35" },
  { code: "KG", name: "Кыргызстан", destination: "Кыргызстан", currency: "KGS", currencyName: "сомов", rate: 1.047, phonePrefix: "+996", lastRecipient: "+996 555 48 27 19" },
  { code: "KZ", name: "Казахстан", destination: "Казахстан", currency: "KZT", currencyName: "тенге", rate: 5.71, phonePrefix: "+7", lastRecipient: "+7 707 312 58 46" },
  { code: "AM", name: "Армения", destination: "Армению", currency: "AMD", currencyName: "драмов", rate: 4.62, phonePrefix: "+374", lastRecipient: "+374 93 642 187" },
  { code: "BY", name: "Беларусь", destination: "Беларусь", currency: "BYN", currencyName: "белорусских рублей", rate: 0.037, phonePrefix: "+375", lastRecipient: "+375 29 681 42 07" },
  { code: "AZ", name: "Азербайджан", destination: "Азербайджан", currency: "AZN", currencyName: "манатов", rate: 0.021, phonePrefix: "+994", lastRecipient: "+994 50 728 31 64" },
  { code: "CN", name: "Китай", destination: "Китай", currency: "CNY", currencyName: "юаней", rate: 0.087, phonePrefix: "+86", lastRecipient: "+86 138 6241 9073" },
]

export const notificationScenarios = [
  {
    countryCode: "TJ" as const,
    title: "Выгодный момент для перевода",
    body: "Курс сомони выгоднее, чем в 85% дней за последние три месяца",
  },
  {
    countryCode: "UZ" as const,
    title: "Рубль укрепился к суму",
    body: "За неделю получатель в Узбекистане получит примерно на 2,1% больше",
  },
  {
    countryCode: "KZ" as const,
    title: "Курс стал выгоднее",
    body: "Сегодня за ту же сумму можно получить больше тенге, чем неделю назад",
  },
] as const

export function getCountry(code: CountryCode) {
  return countries.find((country) => country.code === code) ?? countries[0]
}

export function formatReceived(amount: number, rate: number) {
  const value = amount * rate
  const digits = value >= 1000 ? 0 : value >= 10 ? 1 : 2
  return new Intl.NumberFormat("ru-RU", { maximumFractionDigits: digits }).format(value)
}
