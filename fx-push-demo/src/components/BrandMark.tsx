type BrandMarkProps = {
  compact?: boolean
  inverse?: boolean
}

export function BrandMark({ compact = false, inverse = false }: BrandMarkProps) {
  return (
    <span
      aria-label="Альфа-Банк"
      className={`inline-flex items-center ${compact ? "gap-1.5" : "gap-2.5"}`}
    >
      <span
        className={`${compact ? "h-8 w-8 rounded-[9px]" : "h-14 w-14 rounded-[15px]"} grid place-items-center bg-[#ef3124] text-white shadow-[inset_0_1px_0_rgba(255,255,255,.16)]`}
      >
        <span className={`${compact ? "text-lg" : "text-3xl"} relative -top-px font-black leading-none`}>
          A
          <span className="absolute -bottom-1 left-0 h-[2px] w-full rounded-full bg-current" />
        </span>
      </span>
      {!compact && (
        <span className={`text-[24px] font-bold tracking-[-0.04em] ${inverse ? "text-[#111]" : "text-white"}`}>
          Альфа-Банк
        </span>
      )}
    </span>
  )
}
