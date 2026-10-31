// The same graph as cards: one card per issue, with its fix and who handles it underneath.
import { useLang } from "../../lib/i18n.jsx";
import { NodeBody } from "./ReadinessMap.jsx";

export default function ReadinessCards({ graph, selected, onSelect }) {
  const { t, lang } = useLang();
  const fixesFor = (issue) => graph.fixes.filter((f) => f.step.fixes.includes(issue.code));
  const whoFor = (fix) => graph.who.find((w) => w.fixIds.includes(fix.id));
  const advisor = graph.who.find((w) => w.id === "w:advisor");

  const Part = ({ node, h }) => (
    <button type="button" onClick={() => onSelect(selected === node.id ? null : node.id)}
      className={`block w-full overflow-hidden rounded-lg border text-start transition-colors ${
        selected === node.id ? "border-blue-2 bg-night-3" : "border-transparent hover:border-line-dark hover:bg-white/[.04]"}`}
      style={{ height: h }}>
      <NodeBody node={node} t={t} lang={lang} />
    </button>
  );

  return (
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
      {graph.issues.map((issue) => {
        const fixes = fixesFor(issue);
        return (
          <div key={issue.id} className="rounded-2xl border border-line-dark bg-white/[.04] p-2 transition-transform hover:-translate-y-0.5">
            <Part node={issue} h={64} />
            <div className="mx-3 my-1 border-t border-dashed border-line-dark" />
            {fixes.length ? fixes.map((f) => {
              const w = whoFor(f);
              return (
                <div key={f.id}>
                  <Part node={f} h={72} />
                  {w && <Part node={w} h={56} />}
                </div>
              );
            }) : advisor && <Part node={advisor} h={56} />}
          </div>
        );
      })}
    </div>
  );
}
