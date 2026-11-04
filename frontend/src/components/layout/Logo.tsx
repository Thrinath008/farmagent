/** Furrows running to a horizon, with a shoot breaking through. */
export function Logo({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" fill="none" className={className} aria-hidden="true">
      <path d="M2 28 13 14M12 28l3.5-14M20 28l-3.5-14M30 28 19 14" stroke="#8fce7e" strokeWidth="2" strokeLinecap="round" />
      <path d="M16 11V4" stroke="#fff" strokeWidth="2" strokeLinecap="round" />
      <path d="M16 7.5C16 5 18 3.5 21 3.5 21 6 19 7.5 16 7.5Z" fill="#fff" />
    </svg>
  );
}
