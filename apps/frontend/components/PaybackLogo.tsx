/** The PAYBACK mark — the 2×2 "domino" of four dots (three outlined, top-right filled), matching the
 * official PAYBACK Group logo. ``color`` sets the dots (default PAYBACK blue); on a blue surface pass
 * white. Sized via ``className`` (it's a square viewBox). */
export function PaybackLogo({ className, color = "#0046AA" }: { className?: string; color?: string }) {
  const r = 11; // circle radius
  const sw = 3; // outline stroke width
  // 2×2 grid centres.
  const dots = [
    { cx: 18, cy: 18, fill: false }, // top-left  — outline
    { cx: 46, cy: 18, fill: true }, // top-right — filled
    { cx: 18, cy: 46, fill: false }, // bottom-left  — outline
    { cx: 46, cy: 46, fill: false }, // bottom-right — outline
  ];
  return (
    <svg viewBox="0 0 64 64" xmlns="http://www.w3.org/2000/svg" className={className} role="img" aria-label="PAYBACK">
      {dots.map((d, i) =>
        d.fill ? (
          <circle key={i} cx={d.cx} cy={d.cy} r={r} fill={color} />
        ) : (
          <circle key={i} cx={d.cx} cy={d.cy} r={r - sw / 2} fill="none" stroke={color} strokeWidth={sw} />
        ),
      )}
    </svg>
  );
}
