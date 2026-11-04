import type { Correction } from './api'
import { segment } from './segment'

/** A learner's message with flagged spans underlined; tapping one calls `onSelect`. */
export default function FlaggedText({
  content,
  corrections,
  onSelect,
}: {
  content: string
  corrections: Correction[]
  onSelect: (correction: Correction) => void
}) {
  return (
    <>
      {segment(content, corrections).map((part, i) =>
        part.correction ? (
          <button
            key={i}
            type="button"
            className="flag"
            onClick={() => onSelect(part.correction!)}
            aria-label={`Mistake: ${part.text}. Show correction`}
          >
            {part.text}
          </button>
        ) : (
          <span key={i}>{part.text}</span>
        ),
      )}
    </>
  )
}
