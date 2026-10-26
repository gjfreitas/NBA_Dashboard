import type { Market } from "@/lib/props";
import { InfoTip } from "../InfoTip";
import { SMALL_SAMPLE, type SplitGroup } from "@/lib/splits";

const pct = (v: number | null) => (v == null ? "–" : `${Math.round(v * 100)}%`);

/** The same stat under different conditions. The row with the highest average in each group is marked, small samples are flagged. */
export function SplitsPanel({ groups, market, line, seasonLabel }: { groups: SplitGroup[]; market: Market; line: number; seasonLabel: string }) {
  if (!groups.length) return null;
  return (
    <section aria-label="Splits" className="rounded-lg border border-line bg-surface p-3">
      <h2 className="mb-2 text-sm font-semibold">Splits · {market.label}
        <InfoTip label="About these splits">{seasonLabel}, before the other filters. {market.binary ? "Share of games achieved." : `Hit rate is over ${line}.`} Columns: games, average, hit rate. * means fewer than {SMALL_SAMPLE} games, so treat it as noise.</InfoTip>
      </h2>
      <div className="grid gap-x-6 gap-y-3 md:grid-cols-2">
        {groups.map((g) => {
          const best = Math.max(...g.rows.filter((r) => r.n >= SMALL_SAMPLE && r.avg != null).map((r) => r.avg as number), -Infinity);
          return (
            <table key={g.key} className="num w-full border-collapse text-sm">
              <caption className="pb-1 text-left text-xs font-medium text-muted">{g.label}</caption>
              <thead className="sr-only"><tr><th scope="col">Split</th><th scope="col">Games</th><th scope="col">Average</th><th scope="col">Hit rate</th></tr></thead>
              <tbody>
                {g.rows.map((r) => (
                  <tr key={r.key} className="border-t border-line">
                    <th scope="row" className="py-1.5 pr-2 text-left font-normal">{r.label}</th>
                    <td className="w-12 py-1.5 text-right text-xs text-muted">{r.n}<span className="sr-only"> games</span></td>
                    <td className={`w-14 py-1.5 text-right ${r.n >= SMALL_SAMPLE && r.avg === best ? "font-bold" : ""}`}>
                      {r.avg == null ? "–" : r.avg.toFixed(1)}
                      {r.n >= SMALL_SAMPLE && r.avg === best && g.rows.filter((x) => x.n > 0).length > 1 && <span className="sr-only"> (highest)</span>}
                    </td>
                    <td className="w-12 py-1.5 text-right text-muted">{pct(r.hit)}{r.n > 0 && r.n < SMALL_SAMPLE && <span title="Small sample"> *</span>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          );
        })}
      </div>
    </section>
  );
}
