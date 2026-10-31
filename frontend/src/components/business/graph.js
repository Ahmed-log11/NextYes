// Turns a journey into the readiness graph: business -> issues -> fixes -> who handles them.
// Both the map and the cards view draw from this, so they always agree.
import { BLOCKERS, DEPARTMENTS, label } from "../../lib/labels.js";

export function buildGraph(journey, lang) {
  const current = journey.assessment?.blockers ?? [];
  const first = journey.history?.[0]?.blockers ?? current;
  const openCodes = new Set(current.map((b) => b.code));

  // every issue seen in this journey: open ones and the ones already fixed
  const byCode = new Map();
  for (const b of [...first, ...current]) byCode.set(b.code, b);
  const issues = [...byCode.values()].map((b) => ({
    id: `i:${b.code}`, type: "issue", code: b.code, blocker: b,
    title: label(BLOCKERS, b.code, lang),
    severity: b.severity, resolved: !openCodes.has(b.code),
  }));
  // open hard issues first, then soft, resolved last
  const rank = (n) => (n.resolved ? 2 : n.severity === "hard" ? 0 : 1);
  issues.sort((a, b) => rank(a) - rank(b));
  const issueIndex = new Map(issues.map((n, i) => [n.code, i]));

  const fixes = journey.steps.map((s) => ({
    id: `f:${s.step_id}`, type: "fix", step: s, title: s.title[lang] ?? s.title.en,
    status: s.status, executor: s.executor,
  }));
  const firstIssue = (f) => Math.min(...f.step.fixes.map((c) => issueIndex.get(c) ?? 99), 99);
  fixes.sort((a, b) => firstIssue(a) - firstIssue(b));

  // who handles each fix: the assigned person/department, else the usual department
  const who = new Map();
  const whoOf = (f) => {
    const s = f.step;
    if (s.assignee) {
      const key = `w:${(s.assignee.department || s.assignee.name).toLowerCase()}`;
      return { key, title: s.assignee.department || s.assignee.name, person: s.assignee.department ? s.assignee.name : null, suggested: false };
    }
    if (s.executor === "agent") return { key: "w:agent", title: label(DEPARTMENTS, "CHASE_RECEIVABLES", lang), kind: "agent", suggested: false };
    if (s.executor === "wait") return { key: "w:time", title: label(DEPARTMENTS, "WAIT_HISTORY", lang), kind: "time", suggested: false };
    const dep = DEPARTMENTS[s.remedy] ?? DEPARTMENTS.SWITCH_LENDER;
    return { key: `w:${dep.en.toLowerCase()}`, title: dep[lang] ?? dep.en, suggested: true };
  };
  const edges = [];
  for (const f of fixes) {
    const w = whoOf(f);
    if (!who.has(w.key)) who.set(w.key, { id: w.key, type: "who", title: w.title, people: new Set(), kind: w.kind ?? "team", suggested: w.suggested, fixIds: [] });
    const node = who.get(w.key);
    if (w.person) node.people.add(w.person);
    if (!w.suggested) node.suggested = false;
    node.fixIds.push(f.id);
    edges.push({ from: f.id, to: w.key, tone: f.status === "done" ? "done" : f.status === "in_progress" ? "live" : f.status === "declined" ? "off" : "plain" });
    for (const code of f.step.fixes) {
      if (byCode.has(code)) edges.push({ from: `i:${code}`, to: f.id, tone: f.status === "done" ? "done" : f.status === "declined" ? "off" : f.status === "in_progress" ? "live" : "fix" });
    }
  }
  // issues no step covers go to a human advisor
  const covered = new Set(fixes.flatMap((f) => f.step.fixes));
  const orphans = issues.filter((i) => !covered.has(i.code) && !i.resolved);
  if (orphans.length) {
    who.set("w:advisor", { id: "w:advisor", type: "who", title: label(DEPARTMENTS, "ADVISOR", lang), people: new Set(), kind: "advisor", suggested: false, fixIds: [] });
    for (const o of orphans) { o.unfixable = true; edges.push({ from: o.id, to: "w:advisor", tone: "off" }); }
  }

  const business = {
    id: "b", type: "business", title: journey.business_name[lang] ?? journey.business_name.en,
    score: journey.assessment?.score ?? 0, threshold: journey.assessment?.threshold ?? 75,
  };
  for (const i of issues) edges.unshift({ from: "b", to: i.id, tone: i.resolved ? "done" : i.severity === "hard" ? "hard" : "soft" });

  const whoNodes = [...who.values()].map((w) => ({ ...w, people: [...w.people] }));
  return { business, issues, fixes, who: whoNodes, edges };
}

// Everything connected to a node along the chain (used to highlight a path on hover).
export function connected(graph, id) {
  if (!id) return null;
  const out = new Set([id]);
  const fwd = (n) => graph.edges.filter((e) => e.from === n).forEach((e) => { if (!out.has(e.to)) { out.add(e.to); fwd(e.to); } });
  const back = (n) => graph.edges.filter((e) => e.to === n).forEach((e) => { if (!out.has(e.from)) { out.add(e.from); back(e.from); } });
  fwd(id); back(id);
  return out;
}

export function findNode(graph, id) {
  if (id === "b") return graph.business;
  return [...graph.issues, ...graph.fixes, ...graph.who].find((n) => n.id === id) || null;
}
