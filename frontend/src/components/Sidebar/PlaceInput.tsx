import { useId, useState, type KeyboardEvent } from 'react';
import { usePlaceSuggestions } from '../../hooks/usePlaceSuggestions';
import type { LatLng, PlaceSuggestion } from '../../types';

interface Props {
  id: string;
  value: string;
  location: LatLng | null;
  placeholder?: string;
  invalid?: boolean;
  onChange: (text: string, location: LatLng | null) => void;
}

/**
 * Text input with a suggestions dropdown (ARIA "combobox" pattern).
 * Typing clears the saved location; picking a suggestion stores its exact coordinates,
 * so the backend routes to *that* Springfield instead of guessing.
 * Keyboard: ↑/↓ to move, Enter to pick, Esc to close.
 */
export function PlaceInput({ id, value, location, placeholder, invalid, onChange }: Props) {
  const listId = useId();
  const [open, setOpen] = useState(false);
  const [highlight, setHighlight] = useState(-1);
  const { results, loading } = usePlaceSuggestions(value, open && !location);
  const showList = open && !location && (results.length > 0 || loading);

  const pick = (s: PlaceSuggestion) => {
    onChange(s.label, { lat: s.lat, lng: s.lng });
    setOpen(false);
    setHighlight(-1);
  };

  const onKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (!showList) return;
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setHighlight((h) => Math.min(h + 1, results.length - 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setHighlight((h) => Math.max(h - 1, 0));
    } else if (e.key === 'Enter' && highlight >= 0 && results[highlight]) {
      e.preventDefault(); // pick instead of submitting the form
      pick(results[highlight]);
    } else if (e.key === 'Escape') {
      setOpen(false);
    }
  };

  return (
    <div className="place-input">
      <input
        id={id}
        value={value}
        placeholder={placeholder}
        autoComplete="off"
        role="combobox"
        aria-autocomplete="list"
        aria-expanded={showList}
        aria-controls={listId}
        aria-activedescendant={highlight >= 0 ? `${listId}-${highlight}` : undefined}
        aria-invalid={invalid || undefined}
        onChange={(e) => {
          onChange(e.target.value, null); // edited text no longer matches the picked place
          setOpen(true);
          setHighlight(-1);
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => window.setTimeout(() => setOpen(false), 120)} // let a click on an option land first
        onKeyDown={onKeyDown}
      />
      {location && (
        <span className="place-input__badge" title="Exact place selected from suggestions">
          <svg viewBox="0 0 16 16" width="12" height="12" aria-hidden="true">
            <path d="M3 8.5l3 3 7-7" stroke="currentColor" strokeWidth="2" fill="none" strokeLinecap="round" />
          </svg>
          <span className="visually-hidden">Exact place selected</span>
        </span>
      )}
      {showList && (
        <ul id={listId} role="listbox" className="place-input__list">
          {loading && results.length === 0 && <li className="place-input__status">Searching…</li>}
          {results.map((s, i) => {
            const [name, ...rest] = s.label.split(', ');
            return (
              <li
                key={`${s.label}-${s.lat}`}
                id={`${listId}-${i}`}
                role="option"
                aria-selected={i === highlight}
                className={i === highlight ? 'is-highlighted' : ''}
                onMouseDown={(e) => e.preventDefault()} // keep focus in the input
                onClick={() => pick(s)}
                onMouseEnter={() => setHighlight(i)}
              >
                <span className="place-input__name">{name}</span>
                <span className="place-input__region">{rest.join(', ')}</span>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
