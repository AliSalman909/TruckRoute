import { MapContainer } from './components/Map/MapContainer';
import { InputForm } from './components/Sidebar/InputForm';
import { ResultsPanel } from './components/Sidebar/ResultsPanel';
import { TimelineSlider } from './components/TimelineSlider';
import { useWeatherGrid } from './hooks/useWeatherGrid';

export default function App() {
  useWeatherGrid();
  return (
    <div className="app">
      <aside className="sidebar">
        <header className="brand">
          <span className="brand__mark" aria-hidden="true">
            <svg viewBox="0 0 32 32" width="28" height="28">
              <rect width="32" height="32" rx="8" fill="currentColor" />
              <path d="M6 20h14v-8H6zM20 15h4l3 3v2h-7z" fill="#fff" />
              <circle cx="10" cy="22" r="2.4" fill="#fff" />
              <circle cx="23" cy="22" r="2.4" fill="#fff" />
            </svg>
          </span>
          <div>
            <h1 className="brand__name">SafeHaul</h1>
            <p className="brand__tag">Weather-aware routing for heavy loads</p>
          </div>
        </header>
        <InputForm />
        <ResultsPanel />
        <footer className="sidebar__footer">
          Routing &amp; geocoding: FreeRoute · Forecasts: Open-Meteo · Map: OpenFreeMap, © OpenStreetMap contributors.
          Advisory only; always follow local road closures.
        </footer>
      </aside>
      <main className="map-area">
        <MapContainer />
        <TimelineSlider />
      </main>
    </div>
  );
}
