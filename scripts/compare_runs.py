#!/usr/bin/env python3
"""
compare_runs.py — Comparaison automatique des runs Locust historisés.

Lit les archives CSV dans locust/results/history/ (format YYYYMMDD_HHMM_perf_stats_stats.csv)
et produit un tableau de comparaison Markdown avec delta P95, RPS et taux d'erreur.

Usage :
    python3 scripts/compare_runs.py                    # 2 derniers runs
    python3 scripts/compare_runs.py --runs 5           # 5 derniers runs
    python3 scripts/compare_runs.py --runs 2 --md      # sortie Markdown brute
    python3 scripts/compare_runs.py --baseline 20260518_1341  # run de référence explicite
"""
import argparse
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
HISTORY_DIR = ROOT / "locust" / "results" / "history"

WARN_P95_MS = 1000
CRIT_P95_MS = 5000


def _load_stats(csv_path: Path) -> dict:
    """Charge un fichier perf_stats_stats.csv → dict {name: row}."""
    rows = {}
    try:
        with csv_path.open(encoding="utf-8") as f:
            for row in csv.DictReader(f):
                name = row.get("Name", "").strip()
                if name:
                    rows[name] = row
    except Exception as e:
        print(f"  ❌ Impossible de lire {csv_path.name}: {e}", file=sys.stderr)
    return rows


def _pct_delta(new_val: float, old_val: float) -> str:
    """Retourne le delta en % avec signe et couleur textuelle."""
    if old_val == 0:
        return "—"
    delta = (new_val - old_val) / old_val * 100
    sign = "+" if delta > 0 else ""
    return f"{sign}{delta:.1f}%"


def _fmt_ms(val: str) -> str:
    try:
        return f"{int(float(val))}ms"
    except (ValueError, TypeError):
        return "—"


def list_runs() -> list[tuple[str, Path]]:
    """Retourne les runs disponibles triés du plus récent au plus ancien."""
    if not HISTORY_DIR.exists():
        return []
    seen: dict[str, Path] = {}
    for f in sorted(HISTORY_DIR.glob("*_perf_stats_stats.csv"), reverse=True):
        # Format : YYYYMMDD_HHMM_perf_stats_stats.csv
        prefix = "_".join(f.name.split("_")[:2])  # YYYYMMDD_HHMM
        if prefix not in seen:
            seen[prefix] = f
    return list(seen.items())


def compare(runs: list[tuple[str, Path]], output_md: bool = False) -> None:
    """Affiche la comparaison entre N runs (du plus récent au plus ancien)."""
    if len(runs) < 1:
        print("❌ Aucun run disponible dans locust/results/history/")
        print("   Lancez d'abord : python3 scripts/local_up.py --perf --no-pull")
        return

    # Charger tous les runs
    loaded: list[tuple[str, dict]] = []
    for ts, path in runs:
        stats = _load_stats(path)
        if stats:
            loaded.append((ts, stats))

    if len(loaded) < 2:
        print(f"⚠️  Seulement {len(loaded)} run(s) disponible(s) — comparaison impossible.")
        print("   Lancez au moins 2 runs pour obtenir un diff.")
        if loaded:
            ts, stats = loaded[0]
            agg = stats.get("Aggregated", {})
            print(f"\n  Run {ts}: RPS={agg.get('Requests/s', '?')}  "
                  f"P95={_fmt_ms(agg.get('95%'))}  "
                  f"Fail%={agg.get('Failure %', '?')}%")
        return

    # Header
    header_run = [f"Run {ts}" for ts, _ in loaded]
    sep = "---|" * (len(loaded) + 1)

    print("\n" + "=" * 72)
    print("📊  COMPARAISON DES RUNS LOCUST")
    print("=" * 72)

    # Vue d'ensemble (Aggregated)
    print("\n### Vue d'ensemble (Aggregated)\n")
    print(f"| Métrique | {' | '.join(header_run)} | Δ (dernier vs précédent) |")
    print(f"|---{sep}---|")

    metrics = [
        ("Req/s", "Requests/s", False),
        ("P50 (ms)", "50%", False),
        ("P95 (ms)", "95%", True),     # True = higher is worse
        ("P99 (ms)", "99%", True),
        ("Erreurs %", "Failure %", True),
    ]

    for label, key, higher_is_worse in metrics:
        vals = []
        raw_vals = []
        for ts, stats in loaded:
            agg = stats.get("Aggregated", {})
            raw = agg.get(key, "0") or "0"
            try:
                raw_vals.append(float(raw))
                vals.append(_fmt_ms(raw) if "%" not in label else f"{float(raw):.1f}%")
            except (ValueError, TypeError):
                raw_vals.append(0.0)
                vals.append("—")
        # Delta entre le run le plus récent et le précédent
        delta = "—"
        if len(raw_vals) >= 2:
            delta = _pct_delta(raw_vals[0], raw_vals[1])
            try:
                d = float(raw_vals[0] - raw_vals[1])
                emoji = ""
                if abs(d) > 0.01:
                    improved = d < 0 if higher_is_worse else d > 0
                    emoji = " ✅" if improved else " ⚠️"
                delta = f"{delta}{emoji}"
            except Exception:
                pass
        print(f"| **{label}** | {' | '.join(vals)} | {delta} |")

    # Endpoints — comparaison enrichie (P50, P95, P99, Req/s, Erreurs%)
    print("\n### Endpoints — évolution détaillée (dernier run vs précédent)\n")
    latest_ts, latest_stats = loaded[0]
    prev_ts, prev_stats = loaded[1]

    rows = []
    for name, row in latest_stats.items():
        if name == "Aggregated":
            continue
        prev_row = prev_stats.get(name) or {}
        try:
            p50_new = float(row.get("50%") or 0)
            p95_new = float(row.get("95%") or 0)
            p99_new = float(row.get("99%") or 0)
            rps_new = float(row.get("Requests/s") or 0)
            req_new = int(float(row.get("Request Count") or 0))
            fail_new = int(float(row.get("Failure Count") or 0))
            fail_pct_new = (fail_new / req_new * 100) if req_new > 0 else 0.0

            p95_old = float(prev_row.get("95%") or 0)
            p99_old = float(prev_row.get("99%") or 0)
        except (ValueError, TypeError):
            continue

        delta_p95 = ((p95_new - p95_old) / p95_old * 100) if p95_old > 0 else 0.0
        delta_p99 = ((p99_new - p99_old) / p99_old * 100) if p99_old > 0 else 0.0
        rows.append((name, p50_new, p95_new, p99_new, rps_new, fail_pct_new, delta_p95, delta_p99))

    # Trier par P95 décroissant (bottlenecks en premier)
    rows.sort(key=lambda r: r[2], reverse=True)

    print(
        f"| Endpoint | P50 {latest_ts} | P95 {latest_ts} | P99 {latest_ts} "
        f"| Req/s | Fail% | ΔP95 | ΔP99 |"
    )
    print("|---|---|---|---|---|---|---|---|")
    for name, p50_new, p95_new, p99_new, rps_new, fail_pct_new, delta_p95, delta_p99 in rows[:25]:
        status = "✅" if p95_new < WARN_P95_MS else ("⚠️" if p95_new < CRIT_P95_MS else "❌")
        trend_p95 = f"+{delta_p95:.0f}% 📈" if delta_p95 > 10 else (
            f"{delta_p95:.0f}% 📉" if delta_p95 < -10 else f"{delta_p95:.0f}%"
        )
        trend_p99 = f"+{delta_p99:.0f}% 📈" if delta_p99 > 10 else (
            f"{delta_p99:.0f}% 📉" if delta_p99 < -10 else f"{delta_p99:.0f}%"
        )
        fail_str = f"**{fail_pct_new:.1f}%** ❌" if fail_pct_new > 5 else f"{fail_pct_new:.1f}%"
        short = name[:50] + "…" if len(name) > 50 else name
        print(
            f"| {status} {short} "
            f"| {_fmt_ms(str(p50_new))} "
            f"| {_fmt_ms(str(p95_new))} "
            f"| {_fmt_ms(str(p99_new))} "
            f"| {rps_new:.1f} "
            f"| {fail_str} "
            f"| {trend_p95} "
            f"| {trend_p99} |"
        )

    # Nouvelles erreurs
    print(f"\n### Nouvelles erreurs ({latest_ts} vs {prev_ts})\n")
    # Charger les failures
    fail_path = HISTORY_DIR / f"{latest_ts}_perf_stats_failures.csv"
    prev_fail_path = HISTORY_DIR / f"{prev_ts}_perf_stats_failures.csv"
    new_errors = []
    if fail_path.exists():
        with fail_path.open(encoding="utf-8") as f:
            latest_fails = {r.get("Name"): r for r in csv.DictReader(f)}
        prev_fails: dict = {}
        if prev_fail_path.exists():
            with prev_fail_path.open(encoding="utf-8") as f:
                prev_fails = {r.get("Name"): r for r in csv.DictReader(f)}
        for name, row in latest_fails.items():
            if name not in prev_fails:
                new_errors.append(f"  🆕 **{name}** — {row.get('Error', '')[:80]}")
            else:
                prev_occ = int(prev_fails[name].get("Occurrences") or 0)
                curr_occ = int(row.get("Occurrences") or 0)
                if curr_occ > prev_occ * 1.2:
                    new_errors.append(
                        f"  📈 **{name}** — {curr_occ} occurrences (+{curr_occ - prev_occ})"
                    )
    if new_errors:
        for e in new_errors:
            print(e)
    else:
        print("  ✅ Aucune nouvelle erreur par rapport au run précédent.")

    print(f"\n📁 Historique complet : {HISTORY_DIR}")
    print(f"   {len(loaded)} run(s) chargé(s) sur {len(runs)} disponible(s)\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Comparaison automatique des runs Locust historisés."
    )
    parser.add_argument(
        "--runs", type=int, default=2,
        help="Nombre de runs à comparer (défaut: 2 = dernier vs précédent).",
    )
    parser.add_argument(
        "--md", action="store_true",
        help="Sortie Markdown brute (pour copier-coller).",
    )
    parser.add_argument(
        "--list", action="store_true",
        help="Liste les runs disponibles et quitte.",
    )
    args = parser.parse_args()

    available = list_runs()

    if args.list or not available:
        print(f"📁 Runs disponibles dans {HISTORY_DIR}:")
        for ts, path in available:
            size = path.stat().st_size if path.exists() else 0
            print(f"  {ts}  ({size} bytes)")
        if not available:
            print("  (aucun run)")
        return

    selected = available[:args.runs]
    compare(selected, output_md=args.md)


if __name__ == "__main__":
    main()
