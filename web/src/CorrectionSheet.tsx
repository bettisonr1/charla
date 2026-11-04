import { CATEGORY_LABELS, type Correction } from './api'

/** Bottom sheet with the fix, its category and the explanation. Reachable by thumb. */
export default function CorrectionSheet({
  correction,
  onClose,
}: {
  correction: Correction
  onClose: () => void
}) {
  return (
    <div className="sheet-backdrop" onClick={onClose}>
      <div
        className="sheet"
        role="dialog"
        aria-label="Correction"
        onClick={(e) => e.stopPropagation()}
      >
        <p className="sheet-category">{CATEGORY_LABELS[correction.category]}</p>
        <p className="sheet-diff">
          <del>{correction.original}</del> → <strong>{correction.corrected}</strong>
        </p>
        <p className="sheet-explanation" lang="es">
          {correction.explanation}
        </p>
        <button type="button" className="sheet-close" onClick={onClose} autoFocus>
          Got it
        </button>
      </div>
    </div>
  )
}
