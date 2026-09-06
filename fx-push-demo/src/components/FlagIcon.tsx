import type { CountryCode } from "@/app/demo-data"

type FlagIconProps = {
  code: CountryCode
  size?: "sm" | "md" | "lg"
}

export function FlagIcon({ code, size = "md" }: FlagIconProps) {
  const sizeClass = size === "sm" ? "h-5 w-5 rounded-[6px]" : size === "lg" ? "h-11 w-11 rounded-[13px]" : "h-[30px] w-[30px] rounded-[9px]"

  return (
    <span
      aria-hidden="true"
      className={`flag flag-${code.toLowerCase()} ${sizeClass} relative inline-block shrink-0 overflow-hidden shadow-[0_1px_5px_rgba(0,0,0,.24)]`}
    >
      <span className="flag-detail" />
    </span>
  )
}
