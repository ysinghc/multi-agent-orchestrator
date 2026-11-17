"""Command-line entry point: run a task against the sample knowledge base and print the trace."""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict
from pathlib import Path

from orchestrator.config import GraphConfig
from orchestrator.llm import ChatModel, GeminiChat
from orchestrator.offline import OfflineModel
from orchestrator.runner import RunResult, run_task
from orchestrator.tools import KnowledgeBase, calculator_tool, knowledge_tool

DEFAULT_CORPUS = Path(__file__).resolve().parent / "corpus"  # ships inside the package


def _model(provider: str) -> ChatModel:
    if provider == "gemini":
        try:
            return GeminiChat(
                model=os.environ.get("GEMINI_MODEL", "gemini-2.5-flash"),
                project=os.environ.get("GCP_PROJECT"),
                location=os.environ.get("GCP_LOCATION", "us-central1"),
            )
        except Exception as exc:  # e.g. missing Google credentials
            raise SystemExit(
                f"Could not create the Gemini client: {exc}\n"
                "Gemini needs the optional extra: pip install 'multi-agent-orchestrator[gcp]'\n"
                "and credentials: set GCP_PROJECT and run gcloud auth application-default login.\n"
                "Or run without --provider gemini to use the offline model."
            ) from exc
    return OfflineModel()


def _load_corpus(path: Path) -> KnowledgeBase:
    try:
        kb = KnowledgeBase.from_dir(path)
    except FileNotFoundError as exc:
        raise SystemExit(f"{exc}\nPass --corpus with a folder of .md documents.") from exc
    if len(kb) == 0:
        raise SystemExit(f"no .md documents found in {path}. Pass --corpus with a folder of them.")
    return kb


def _print_trace(result: RunResult) -> None:
    print(f"status: {result.status}   revisions: {result.revisions}")
    print(f"answer:\n{result.final_answer}\n")
    print(f"{'step':<18}{'role':<12}{'ms':>9}  {'tokens in/out':<14}{'tok/s':>9}  cost (USD)")
    for e in result.events:
        tps = "-" if e["tokens_per_second"] is None else f"{e['tokens_per_second']:.1f}"
        print(
            f"{e['node']:<18}{e['role']:<12}{e['duration_s'] * 1000:>9.2f}  "
            f"{e['prompt_tokens']}/{e['completion_tokens']:<12}{tps:>9}  {e['cost_usd']:.8f}"
        )
    t = result.trace
    print(
        f"\nllm_calls={t['llm_calls']} tokens_out={t['completion_tokens']} "
        f"tokens_per_second={t['tokens_per_second']} cost_usd={t['cost_usd']:.8f}"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="orchestrate")
    parser.add_argument("task", help="the task for the agent team")
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--provider", choices=["offline", "gemini"], default="offline")
    parser.add_argument("--max-llm-calls", type=int, default=20)
    parser.add_argument("--json", action="store_true", help="print the full result as JSON")
    args = parser.parse_args(argv)

    kb = _load_corpus(args.corpus)
    config = GraphConfig(max_llm_calls=args.max_llm_calls)
    result = run_task(
        args.task, _model(args.provider), [calculator_tool(), knowledge_tool(kb)], config
    )
    if args.json:
        print(json.dumps(asdict(result), indent=2, default=str))
    else:
        _print_trace(result)
    return 0
