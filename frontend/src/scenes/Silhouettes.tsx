/** Small original accents: dhow, falcon, date palm. */
export function Dhow({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 120 80" aria-hidden="true" fill="currentColor">
      <path d="M4 52 L116 52 Q104 70 86 72 L28 72 Q12 68 4 52 Z" />
      <rect x="58" y="10" width="2.4" height="44" />
      <path d="M61 12 L108 48 L61 48 Z" opacity=".92" />
      <path d="M57 20 L24 48 L57 48 Z" opacity=".75" />
      <path d="M2 54 Q-4 50 0 44 Q6 48 6 52 Z" />
    </svg>
  );
}
export function Falcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 120 60" aria-hidden="true" fill="currentColor">
      <path d="M60 22 C48 8 24 6 4 14 C24 14 38 22 44 34 L52 30 L60 46 L68 30 L76 34 C82 22 96 14 116 14 C96 6 72 8 60 22 Z" />
      <path d="M60 22 L64 16 L60 12 L56 16 Z" />
    </svg>
  );
}
export function DatePalm({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 100 160" aria-hidden="true" fill="currentColor">
      <path d="M48 160 Q52 100 50 60 L54 60 Q56 100 58 160 Z" />
      {[-70, -40, -12, 12, 40, 70].map((a) => (
        <path key={a} d="M52 62 Q 52 34 86 30 Q 62 40 54 62 Z" transform={`rotate(${a} 52 62)`} />
      ))}
      <circle cx="46" cy="66" r="3.4" />
      <circle cx="58" cy="68" r="3.4" />
    </svg>
  );
}
