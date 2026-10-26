from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from . import __version__
from .api import create_server
from .auditor import Auditor
from .config import Settings
from .enums import ClaimLabel
from .evaluation import run_all_evaluations
from .mocks.registry import MockRegistry
from .probes.models import validate_payload
from .utils import truncate


def _settings(args: argparse.Namespace) -> Settings:
    settings = Settings.from_env()
    settings.live = bool(getattr(args, "live", False))
    if getattr(args, "output_dir", None):
        settings.outputs_dir = Path(args.output_dir)
    if getattr(args, "cache_dir", None):
        settings.cache_dir = Path(args.cache_dir)
    if getattr(args, "drift_mode", None):
        settings.drift_mode = args.drift_mode
    return settings.prepare()


def _auditor(args: argparse.Namespace, persist: bool | None = None) -> Auditor:
    should_persist = not bool(getattr(args, "no_persist", False)) if persist is None else persist
    return Auditor(settings=_settings(args), persist=should_persist)


def _alert_message(alert: Any) -> str:
    message = alert.details.get("message")
    if message:
        return str(message)
    if alert.detector.value == "embedding":
        threshold = alert.details.get("threshold")
        return f"schema distance {alert.distance:.4f} exceeds threshold {threshold}"
    return ""


def _print_verify(result: Any) -> None:
    counts: dict[str, int] = {label.value: 0 for label in ClaimLabel}
    for assessment in result.assessments:
        counts[assessment.label.value] += 1
    summary = ", ".join(f"{name}={count}" for name, count in counts.items() if count)
    print(f"Tool: {result.tool_id}")
    print(f"Probe: {result.probe_source or '-'} HTTP {result.probe_status_code if result.probe_status_code is not None else '-'} valid={result.probe_valid}")
    print(f"Coverage: {result.coverage.coverage_percent:.2f}% overall, {result.coverage.probeable_coverage_percent:.2f}% of probeable claims")
    print(f"Labels: {summary or 'none'}")
    print(f"Drift alerts: {len(result.drift_alerts)}")
    for alert in result.drift_alerts:
        print(f"  [{alert.severity.value}] {alert.detector.value} {alert.field_path or 'transport'}: {_alert_message(alert)}")
    print("")
    print(f"{'Label':<13} {'Docs':<10} {'Probe':<13} Claim")
    print(f"{'-' * 13} {'-' * 10} {'-' * 13} {'-' * 60}")
    for assessment in result.assessments:
        claim_text = truncate(assessment.claim.text, 88)
        print(f"{assessment.label.value:<13} {assessment.doc_stance.value:<10} {assessment.probe_outcome.value:<13} {claim_text}")
    if result.notes:
        print("")
        for note in result.notes:
            print(f"Note: {note}")


def _print_probe(auditor: Auditor, tool_id: str, probe: Any) -> None:
    validation = validate_payload(auditor.get_definition(tool_id), probe.payload) if probe.payload is not None else None
    print(f"Tool: {tool_id}")
    print(f"Source: {probe.source.value}")
    print(f"Status: {probe.status_code} ok={probe.ok} latency_ms={probe.latency_ms:.2f} cached={probe.cached}")
    print(f"URL: {probe.url}")
    if probe.error:
        print(f"Error: {probe.error}")
    if validation is not None:
        print(f"Validation: ok={validation.ok} checked_fields={validation.checked_fields} issues={len(validation.issues)}")
        for issue in validation.issues:
            print(f"  {issue.path}: {issue.message}")
    print("Payload:")
    print(truncate(json.dumps(probe.payload, indent=2, ensure_ascii=False), 2000))


def command_catalog(args: argparse.Namespace) -> int:
    auditor = _auditor(args, persist=False)
    if args.json:
        print(json.dumps([tool.to_dict() for tool in auditor.catalog.values()], indent=2, ensure_ascii=False))
        return 0
    print(f"{'Tool':<20} {'Category':<14} {'Claims':>6} {'Probeable':>9}  Name")
    for tool in auditor.catalog.values():
        print(f"{tool.tool_id:<20} {tool.category:<14} {len(tool.claims):>6} {str(tool.tool_id in auditor.definitions):>9}  {tool.name}")
    return 0


def command_verify(args: argparse.Namespace) -> int:
    auditor = _auditor(args)
    result = auditor.verify(
        args.tool_id,
        force_live=args.live,
        establish_baseline=not args.no_baseline,
    )
    if args.json:
        print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
    else:
        _print_verify(result)
    return 0


def command_probe(args: argparse.Namespace) -> int:
    auditor = _auditor(args, persist=False)
    probe = auditor.probe(args.tool_id, force_live=args.live)
    if args.json:
        print(json.dumps(probe.to_dict(), indent=2, ensure_ascii=False))
    else:
        _print_probe(auditor, args.tool_id, probe)
    return 0 if probe.ok else 1


def command_extract(args: argparse.Namespace) -> int:
    auditor = _auditor(args, persist=False)
    claims = auditor.extract_claims(args.tool_id)
    if args.json:
        print(json.dumps([claim.to_dict() for claim in claims], indent=2, ensure_ascii=False))
        return 0
    print(f"Extracted {len(claims)} claims from {args.tool_id}")
    for claim in claims:
        field = f" field={claim.field_path}" if claim.field_path else ""
        print(f"- {claim.text} [{claim.claim_type.value}]{field}")
    return 0


def command_monitor(args: argparse.Namespace) -> int:
    auditor = _auditor(args)
    baseline = auditor.verify(args.tool_id, force_live=args.live, establish_baseline=True)
    print(f"Established baseline for {args.tool_id}: alerts={len(baseline.drift_alerts)}")
    for probe_round in range(1, args.rounds + 1):
        result = auditor.monitor_tool(
            args.tool_id,
            probe_round=probe_round,
            force_live=args.live,
            establish_baseline=False,
        )
        print(f"Round {probe_round}: source={result.probe_source or '-'} alerts={len(result.drift_alerts)} labels={ {item.label.value for item in result.assessments} }")
        for alert in result.drift_alerts:
            print(f"  [{alert.severity.value}] {alert.detector.value} {alert.field_path or 'transport'}: {_alert_message(alert)}")
        if probe_round < args.rounds and args.interval > 0:
            time.sleep(args.interval)
    return 0


def command_evaluate(args: argparse.Namespace) -> int:
    result = run_all_evaluations(output_dir=args.output_dir, threshold=args.threshold)
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    claims = result["claim_verification"]["metrics"]
    drift = result["drift_detection"]
    trust = result["trust_experiment"]
    print("Evaluation complete")
    print(f"Claims: accuracy={claims['accuracy']:.3f} macro_f1={claims['macro_f1']:.3f} n={claims['total']}")
    print(
        f"Drift: rule_only={drift['runs']['rule_only']['detected']}/{drift['scenario_count']} "
        f"full={drift['runs']['full']['detected']}/{drift['scenario_count']} "
        f"false_alarms={drift['false_alarms']['full']['false_alarms']}/{drift['false_alarms']['full']['total_variations']}"
    )
    print(f"Trust: bad_demoted={trust['bad_demoted']}/{trust['bad_providers']} honest_demoted={trust['honest_demoted']}/{trust['honest_providers']}")
    print(f"Summary: {result['artifacts']['markdown']}")
    return 0


def command_demo(args: argparse.Namespace) -> int:
    del args
    with tempfile.TemporaryDirectory(prefix="agent-bazaar-demo-") as temporary:
        base = Path(temporary)
        settings = Settings(
            outputs_dir=base / "outputs",
            cache_dir=base / "cache",
            live=False,
            drift_mode="full",
        ).prepare()
        auditor = Auditor(settings=settings, persist=False)
        registry = MockRegistry(auditor.harness, catalog=auditor.catalog, definitions=auditor.definitions)
        print("Agent Bazaar Auditor demo")
        print(f"Version {__version__}; offline fixtures; {len(auditor.catalog)} tools and {len(auditor.definitions)} probe definitions.")
        print("")
        print("1. Healthy provider: Frankfurter")
        healthy = auditor.verify("frankfurter")
        _print_verify(healthy)
        print("")
        print("2. Dishonest provider: Open-Meteo silently switches Celsius to Fahrenheit")
        baseline = auditor.verify("open-meteo", establish_baseline=True)
        print(f"Healthy baseline labels: {sorted({item.label.value for item in baseline.assessments})}")
        registry.control("open-meteo", "dishonest")
        result = auditor.monitor_tool("open-meteo", probe_round=1, establish_baseline=False)
        print(f"After injection: labels={sorted({item.label.value for item in result.assessments})} alerts={len(result.drift_alerts)}")
        for alert in result.drift_alerts:
            print(f"  [{alert.severity.value}] {alert.detector.value} {alert.field_path}: {_alert_message(alert)}")
        print("")
        print("3. Outage: IPify returns HTTP 503")
        auditor.verify("ipify", establish_baseline=True)
        registry.control("ipify", "outage")
        outage = auditor.monitor_tool("ipify", probe_round=1, establish_baseline=False)
        print(f"Labels={sorted({item.label.value for item in outage.assessments})} alerts={len(outage.drift_alerts)}")
        print("")
        print("4. Garbage 200: Nominatim returns polluted schema")
        auditor.verify("nominatim", establish_baseline=True)
        registry.control("nominatim", "garbage_200")
        garbage = auditor.monitor_tool("nominatim", probe_round=1, establish_baseline=False)
        print(f"Detectors={sorted({alert.detector.value for alert in garbage.drift_alerts})} alerts={len(garbage.drift_alerts)}")
        for alert in garbage.drift_alerts:
            print(f"  [{alert.severity.value}] {alert.detector.value} distance={alert.distance}: {_alert_message(alert)}")
        print("")
        print("5. Trust leaderboard after observations")
        for row in auditor.trust_snapshot():
            print(f"  {row['tool_id']:<20} score={row['score']:.3f} observations={row['observations']} failures={row['failures']}")
        print("")
        print("Demo finished. Run `agent-bazaar-auditor evaluate` for the full seeded evaluation.")
    return 0


def command_serve(args: argparse.Namespace) -> int:
    auditor = _auditor(args)
    mock_registry = MockRegistry(auditor.harness, catalog=auditor.catalog, definitions=auditor.definitions) if args.mock else None
    server = create_server(auditor, host=args.host, port=args.port, mock_registry=mock_registry)
    print(f"Auditor API listening on http://{args.host}:{args.port} (mock_control={args.mock})")
    print("GET /health /tools /probes /trust; POST /verify /probe /monitor /mock")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Shutting down.")
    finally:
        server.server_close()
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="agent-bazaar-auditor",
        description="Trust and drift auditor for third-party agent tools.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--live", action="store_true", help="Use live HTTP probes instead of offline fixtures.")
    common.add_argument("--output-dir", help="Directory for artifacts and reports.")
    common.add_argument("--cache-dir", help="Directory for probe cache.")
    common.add_argument("--drift-mode", choices=["full", "rule_only", "embedding_only"], help="Drift detection mode.")
    common.add_argument("--no-persist", action="store_true", help="Do not write artifacts.")
    common.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    catalog = subparsers.add_parser("catalog", parents=[common], help="List catalog tools and claims.")
    catalog.set_defaults(func=command_catalog)

    verify = subparsers.add_parser("verify", parents=[common], help="Verify all claims for a tool.")
    verify.add_argument("tool_id")
    verify.add_argument("--no-baseline", action="store_true", help="Do not establish a drift baseline.")
    verify.set_defaults(func=command_verify)

    probe = subparsers.add_parser("probe", parents=[common], help="Probe one tool and validate its payload.")
    probe.add_argument("tool_id")
    probe.set_defaults(func=command_probe)

    extract = subparsers.add_parser("extract", parents=[common], help="Extract claims from a tool description.")
    extract.add_argument("tool_id")
    extract.set_defaults(func=command_extract)

    monitor = subparsers.add_parser("monitor", parents=[common], help="Re-probe a tool and report drift alerts.")
    monitor.add_argument("tool_id")
    monitor.add_argument("--rounds", type=int, default=3)
    monitor.add_argument("--interval", type=float, default=0.0, help="Seconds between rounds.")
    monitor.set_defaults(func=command_monitor)

    evaluate = subparsers.add_parser("evaluate", parents=[common], help="Run claim, drift and trust evaluations.")
    evaluate.add_argument("--threshold", type=float, default=None, help="Override the tuned drift threshold.")
    evaluate.set_defaults(func=command_evaluate)

    demo = subparsers.add_parser("demo", help="Run an end-to-end offline demonstration.")
    demo.set_defaults(func=command_demo)

    serve = subparsers.add_parser("serve", parents=[common], help="Start the HTTP API.")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8765)
    serve.add_argument("--mock", action="store_true", help="Enable POST /mock provider controls.")
    serve.set_defaults(func=command_serve)
    return parser


def _configure_output() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8")
        except (ValueError, OSError):
            pass


def main(argv: list[str] | None = None) -> int:
    _configure_output()
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except KeyError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    except ValueError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        return 130
