// App-wide demo state: the businesses a visitor can pick, which one is selected, and the
// journey started for each (kept in this browser so a judge can switch back and forth).
import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { api } from "./api.js";

const KEY = "ny-journeys";
const load = (k, fallback) => { try { return JSON.parse(localStorage.getItem(k)) ?? fallback; } catch { return fallback; } };
const save = (k, v) => { try { localStorage.setItem(k, JSON.stringify(v)); } catch { /* private mode */ } };

const DemoContext = createContext(null);

export function DemoProvider({ children }) {
  const [businesses, setBusinesses] = useState([]);
  const [apiError, setApiError] = useState(null);
  const [selected, setSelectedState] = useState(() => load("ny-selected", null));
  const [journeys, setJourneys] = useState(() => load(KEY, {}));

  useEffect(() => {
    api.businesses()
      .then((list) => {
        setBusinesses(list);
        setSelectedState((cur) => (list.some((b) => b.business_id === cur) ? cur : list[0]?.business_id ?? null));
      })
      .catch((e) => setApiError(e.message));
  }, []);

  const setSelected = useCallback((id) => { setSelectedState(id); save("ny-selected", id); }, []);
  const setJourney = useCallback((businessId, journeyId) => {
    setJourneys((cur) => {
      const next = { ...cur };
      if (journeyId) next[businessId] = journeyId; else delete next[businessId];
      save(KEY, next);
      return next;
    });
  }, []);

  const business = businesses.find((b) => b.business_id === selected) || null;
  return (
    <DemoContext.Provider value={{ businesses, business, selected, setSelected, journeys, setJourney, apiError }}>
      {children}
    </DemoContext.Provider>
  );
}

export const useDemo = () => useContext(DemoContext);

// One journey: its state, what it waits for, and a way to act on it.
export function useJourney(journeyId) {
  const [data, setData] = useState(null);   // {journey, waiting}
  const [busy, setBusy] = useState(null);   // the action type in flight
  const [error, setError] = useState(null);

  useEffect(() => {
    setData(null); setError(null);
    if (!journeyId) return;
    let live = true;
    api.journey(journeyId).then((d) => live && setData(d)).catch((e) => live && setError(e.message));
    return () => { live = false; };
  }, [journeyId]);

  const act = useCallback(async (action) => {
    setBusy(action.type); setError(null);
    try { const d = await api.act(journeyId, action); setData(d); return d; }
    catch (e) { setError(e.message); return null; }
    finally { setBusy(null); }
  }, [journeyId]);

  return { data, journey: data?.journey, waiting: data?.waiting, busy, error, act, setData };
}
