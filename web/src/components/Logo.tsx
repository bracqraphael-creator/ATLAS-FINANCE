/** Emblème ATLAS : un globe réduit à son équateur et à un méridien incliné. */
export function Logo({ className = "h-7 w-7" }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" className={className} aria-hidden="true">
      <circle cx="16" cy="16" r="13" fill="none" stroke="var(--brass)" strokeWidth="1.6" />
      <ellipse cx="16" cy="16" rx="5.5" ry="13" fill="none" stroke="var(--brass)" strokeWidth="1.2" transform="rotate(18 16 16)" />
      <path d="M3 16h26" stroke="var(--brass)" strokeWidth="1.2" />
    </svg>
  );
}
