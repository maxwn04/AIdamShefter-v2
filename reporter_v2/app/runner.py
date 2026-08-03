"""CLI runner for reporter v2."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import text

from datalayer.sleeper_data import SleeperConfig, SleeperLeagueData
from reporter_memory.context_store import ContextStore
from reporter_v2.config import BiasProfile, ReportConfig, TimeRange, ToneControls
from reporter_v2.runner.completion import CompletionSettings, RetryPolicy
from reporter_v2.runner.article_generator import generate_article
from reporter_v2.runner.state import ProcedureHistoryMode, RunnerConfig


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="AI Fantasy Football Reporter V2",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  reporter-v2 "weekly recap" --week 8
  reporter-v2 "snarky recap, roast Team Taco" --week 8 --model deepseek/deepseek-chat
  reporter-v2 "power rankings" --focus standings --length 1400
        """,
    )
    parser.add_argument(
        "prompt",
        nargs="?",
        help="Article request. If omitted, the CLI prompts for one.",
    )
    parser.add_argument("--week", "-w", type=int, help="Single week to cover.")
    parser.add_argument("--week-start", type=int, help="Start week for a range.")
    parser.add_argument("--week-end", type=int, help="End week for a range.")
    parser.add_argument(
        "--week-override",
        type=int,
        default=None,
        help=(
            "Pin the Sleeper effective week during data load. "
            "Overrides SLEEPER_WEEK_OVERRIDE."
        ),
    )
    parser.add_argument(
        "--league",
        "-l",
        default=None,
        help="Sleeper league ID. Defaults to SLEEPER_LEAGUE_ID.",
    )
    parser.add_argument(
        "--model",
        default=None,
        help=(
            "LiteLLM model ID. Defaults to REPORTER_V2_MODEL, REPORTER_MODEL, "
            "then gpt-5-mini."
        ),
    )
    parser.add_argument(
        "--fallback-model",
        action="append",
        default=None,
        dest="fallback_models",
        help=(
            "Fallback LiteLLM model ID if the primary model keeps failing. "
            "Repeat for multiple fallbacks. Defaults to REPORTER_V2_FALLBACK_MODELS "
            "or REPORTER_FALLBACK_MODELS (comma-separated)."
        ),
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=None,
        help=(
            "Retries per model on rate limits / transient errors before falling "
            "back. Defaults to REPORTER_V2_MAX_RETRIES or 3."
        ),
    )
    parser.add_argument("--voice", default="sports columnist")
    parser.add_argument("--snark", type=int, default=1, choices=range(0, 4))
    parser.add_argument("--hype", type=int, default=1, choices=range(0, 4))
    parser.add_argument("--seriousness", type=int, default=1, choices=range(0, 4))
    parser.add_argument("--length", type=int, default=1000, help="Target word count.")
    parser.add_argument(
        "--focus",
        action="append",
        default=[],
        help="Topic to emphasize. Repeat or pass comma-separated values.",
    )
    parser.add_argument(
        "--focus-team",
        action="append",
        default=[],
        help="Team to emphasize. Repeat or pass comma-separated values.",
    )
    parser.add_argument(
        "--avoid",
        action="append",
        default=[],
        help="Topic to skip or minimize. Repeat or pass comma-separated values.",
    )
    parser.add_argument(
        "--favor",
        action="append",
        default=[],
        help="Team to frame positively. Repeat or pass comma-separated values.",
    )
    parser.add_argument(
        "--roast",
        action="append",
        default=[],
        help="Team to frame negatively. Repeat or pass comma-separated values.",
    )
    parser.add_argument(
        "--bias-intensity",
        type=int,
        default=2,
        choices=range(0, 4),
    )
    parser.add_argument(
        "--profanity-policy",
        default="none",
        choices=["none", "mild", "unrestricted"],
    )
    parser.add_argument(
        "--evidence-policy",
        default="standard",
        choices=["strict", "standard", "relaxed"],
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Directory for generated article files. Defaults to REPORTER_OUTPUT_DIR.",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=None,
        help="Directory for persistent context. Defaults to REPORTER_DATA_DIR or .data.",
    )
    parser.add_argument(
        "--no-context",
        action="store_true",
        help="Do not load or write persistent context.",
    )
    parser.add_argument(
        "--eval",
        action="store_true",
        help=(
            "Eval mode: load/search storyline memory for continuity, but do not "
            "write or mutate persistent memory. Useful for fair model comparisons."
        ),
    )
    parser.add_argument(
        "--max-turns",
        type=int,
        default=None,
        help="Maximum model turns before stopping. Defaults to REPORTER_V2_MAX_TURNS or 60.",
    )
    parser.add_argument(
        "--procedure-mode",
        choices=[mode.value for mode in ProcedureHistoryMode],
        default=None,
        help=(
            "How to retain loaded procedure tool results: replace or append. "
            "Defaults to REPORTER_V2_PROCEDURE_MODE or replace."
        ),
    )
    return parser.parse_args()


async def run(args: argparse.Namespace) -> None:
    """Run reporter v2 from parsed CLI args."""
    load_dotenv()
    prompt = args.prompt or _prompt_for_request()
    completion = _resolve_completion_settings(args)
    runner_config = RunnerConfig(
        max_turns=_resolve_max_turns(args.max_turns),
        procedure_history_mode=_resolve_procedure_history_mode(
            getattr(args, "procedure_mode", None)
        ),
    )
    output_dir = args.output_dir or Path(os.getenv("REPORTER_OUTPUT_DIR", ".output"))
    data_dir = args.data_dir or Path(os.getenv("REPORTER_DATA_DIR", ".data"))
    eval_mode = bool(getattr(args, "eval", False))
    if eval_mode and args.no_context:
        raise SystemExit("Cannot combine --eval with --no-context.")
    allow_memory_writes = not eval_mode

    print()
    print("=" * 60)
    print("  Fantasy Football Reporter V2")
    print("=" * 60)
    print()
    print("Loading league data...")

    data = _make_sleeper_data(args.league, getattr(args, "week_override", None))
    data.load()

    time_range = _resolve_time_range(args, data)
    season = _get_season(data)
    context_store = (
        None
        if args.no_context
        else ContextStore(
            db_path=data_dir / "context.db",
            league_id=data.league_id,
            season=season,
        )
    )

    report_config = _build_report_config(args, prompt, time_range)
    output_dir.mkdir(parents=True, exist_ok=True)
    week_slug = _week_slug(time_range)
    log_path = output_dir / f"v2_{week_slug}.stream.log"

    print(f"League: {data.league_id}")
    print(f"Season: {season}")
    print(f"Weeks: {time_range.week_start}-{time_range.week_end}")
    if data.week_override is not None:
        print(f"Sleeper week override: {data.week_override}")
    print(f"Model: {completion.model}")
    if completion.fallback_models:
        print(f"Fallback models: {', '.join(completion.fallback_models)}")
    print(f"Max retries per model: {completion.retry.max_retries}")
    print(f"Max turns: {runner_config.max_turns}")
    print(f"Procedure mode: {runner_config.procedure_history_mode.value}")
    if eval_mode:
        print("Eval mode: memory reads enabled, memory writes disabled")
    if context_store is not None:
        print(f"Context DB: {data_dir / 'context.db'}")
    print(f"Stream log: {log_path}")
    print()
    print("Running v2 single-loop reporter...")
    print()

    output = await generate_article(
        data,
        report_config,
        context_store=context_store,
        completion=completion,
        runner_config=runner_config,
        log_path=log_path,
        allow_memory_writes=allow_memory_writes,
    )

    print("--- Generated Article ---")
    print()
    print(output.article)
    print()
    print("--- Saving Outputs ---")
    print()

    article_path = output_dir / f"v2_article_{week_slug}.md"
    article_path.write_text(output.article, encoding="utf-8")
    print(f"  Article: {article_path}")

    brief_path = output_dir / f"v2_article_{week_slug}.brief.json"
    brief_path.write_text(output.brief.model_dump_json(indent=2), encoding="utf-8")
    print(f"  Brief: {brief_path}")

    summary_path = output_dir / f"v2_article_{week_slug}.run_log_summary.json"
    summary_path.write_text(
        json.dumps(output.run_log_summary, indent=2),
        encoding="utf-8",
    )
    print(f"  Run log summary: {summary_path}")

    run_log_path = output_dir / f"v2_article_{week_slug}.run_log.json"
    run_log_path.write_text(
        json.dumps(output.run_log_entries, indent=2),
        encoding="utf-8",
    )
    print(f"  Run log entries: {run_log_path}")

    print(f"  Stream log: {log_path}")
    print()
    print("Done!")


def main() -> None:
    """Main entry point."""
    try:
        asyncio.run(run(parse_args()))
    except ValueError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        sys.exit(1)


def _prompt_for_request() -> str:
    print()
    print("What kind of article would you like?")
    print()
    prompt = input("> ").strip()
    if not prompt:
        raise ValueError("No prompt provided.")
    return prompt


def _resolve_completion_settings(args: argparse.Namespace) -> CompletionSettings:
    model = _resolve_model(args.model)
    fallback_models = _resolve_fallback_models(
        getattr(args, "fallback_models", None),
        model,
    )
    max_retries = _resolve_max_retries(getattr(args, "max_retries", None))
    return CompletionSettings(
        model=model,
        fallback_models=tuple(fallback_models),
        retry=RetryPolicy(max_retries=max_retries),
    )


def _resolve_model(model_arg: str | None) -> str:
    return (
        model_arg
        or os.getenv("REPORTER_V2_MODEL")
        or os.getenv("REPORTER_MODEL")
        or "gpt-5-mini"
    )


def _resolve_fallback_models(
    fallback_args: list[str] | None,
    primary_model: str,
) -> list[str]:
    if fallback_args:
        candidates = fallback_args
    else:
        raw_value = (
            os.getenv("REPORTER_V2_FALLBACK_MODELS")
            or os.getenv("REPORTER_FALLBACK_MODELS")
            or ""
        )
        candidates = [part.strip() for part in raw_value.split(",") if part.strip()]

    seen = {primary_model}
    models: list[str] = []
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        models.append(candidate)
    return models


def _resolve_max_retries(max_retries_arg: int | None) -> int:
    if max_retries_arg is not None:
        if max_retries_arg < 0:
            raise ValueError("--max-retries must be at least 0.")
        return max_retries_arg

    raw_value = os.getenv("REPORTER_V2_MAX_RETRIES")
    if raw_value is None or raw_value == "":
        return RetryPolicy().max_retries

    try:
        max_retries = int(raw_value)
    except ValueError as exc:
        raise ValueError("REPORTER_V2_MAX_RETRIES must be an integer.") from exc
    if max_retries < 0:
        raise ValueError("REPORTER_V2_MAX_RETRIES must be at least 0.")
    return max_retries


def _resolve_max_turns(max_turns_arg: int | None) -> int:
    if max_turns_arg is not None:
        if max_turns_arg < 1:
            raise ValueError("--max-turns must be at least 1.")
        return max_turns_arg

    raw_value = os.getenv("REPORTER_V2_MAX_TURNS")
    if raw_value is None or raw_value == "":
        return 60

    try:
        max_turns = int(raw_value)
    except ValueError as exc:
        raise ValueError("REPORTER_V2_MAX_TURNS must be an integer.") from exc
    if max_turns < 1:
        raise ValueError("REPORTER_V2_MAX_TURNS must be at least 1.")
    return max_turns


def _make_sleeper_data(
    league_arg: str | None,
    week_override_arg: int | None,
) -> SleeperLeagueData:
    if week_override_arg is None:
        return SleeperLeagueData(league_id=league_arg)

    league_id = league_arg or os.getenv("SLEEPER_LEAGUE_ID")
    if not league_id:
        raise ValueError(
            "SLEEPER_LEAGUE_ID must be set or --league must be provided "
            "when using --week-override."
        )

    return SleeperLeagueData(
        config=SleeperConfig(
            league_id=str(league_id),
            week_override=week_override_arg,
        )
    )


def _resolve_procedure_history_mode(
    procedure_mode_arg: str | None,
) -> ProcedureHistoryMode:
    raw_value = procedure_mode_arg or os.getenv("REPORTER_V2_PROCEDURE_MODE")
    if raw_value is None or raw_value == "":
        return ProcedureHistoryMode.REPLACE

    try:
        return ProcedureHistoryMode(raw_value)
    except ValueError as exc:
        allowed = ", ".join(mode.value for mode in ProcedureHistoryMode)
        name = (
            "--procedure-mode"
            if procedure_mode_arg is not None
            else "REPORTER_V2_PROCEDURE_MODE"
        )
        raise ValueError(f"{name} must be one of: {allowed}.") from exc


def _resolve_time_range(
    args: argparse.Namespace,
    data: SleeperLeagueData,
) -> TimeRange:
    if args.week is not None and (args.week_start is not None or args.week_end is not None):
        raise ValueError("Use either --week or --week-start/--week-end, not both.")

    if args.week is not None:
        return TimeRange.single_week(args.week)

    if args.week_start is not None or args.week_end is not None:
        if args.week_start is None or args.week_end is None:
            raise ValueError("--week-start and --week-end must be provided together.")
        if args.week_end < args.week_start:
            raise ValueError("--week-end must be greater than or equal to --week-start.")
        return TimeRange.range(args.week_start, args.week_end)

    if data.effective_week is None:
        raise ValueError("Week is required because no effective week was loaded.")
    return TimeRange.single_week(int(data.effective_week))


def _build_report_config(
    args: argparse.Namespace,
    prompt: str,
    time_range: TimeRange,
) -> ReportConfig:
    favored_teams = _flatten(args.favor)
    disfavored_teams = _flatten(args.roast)
    bias_profile = None
    if favored_teams or disfavored_teams:
        bias_profile = BiasProfile(
            favored_teams=favored_teams,
            disfavored_teams=disfavored_teams,
            intensity=args.bias_intensity,
        )

    return ReportConfig(
        time_range=time_range,
        focus_hints=_flatten(args.focus),
        avoid_topics=_flatten(args.avoid),
        focus_teams=_flatten(args.focus_team),
        voice=args.voice,
        tone=ToneControls(
            snark_level=args.snark,
            hype_level=args.hype,
            seriousness=args.seriousness,
        ),
        profanity_policy=args.profanity_policy,
        bias_profile=bias_profile,
        length_target=args.length,
        evidence_policy=args.evidence_policy,
        custom_instructions=prompt,
    )


def _flatten(values: list[str]) -> list[str]:
    results: list[str] = []
    for value in values:
        results.extend(part.strip() for part in value.split(",") if part.strip())
    return results


def _get_season(data: SleeperLeagueData) -> str:
    if not data._query_conn:
        return ""
    row = data._query_conn.execute(text("SELECT season FROM leagues LIMIT 1")).first()
    return str(row[0]) if row else ""


def _week_slug(time_range: TimeRange) -> str:
    if time_range.week_start == time_range.week_end:
        return f"week{time_range.week_start}"
    return f"weeks{time_range.week_start}-{time_range.week_end}"


if __name__ == "__main__":
    main()
