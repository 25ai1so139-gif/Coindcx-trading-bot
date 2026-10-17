"""Bounded PUBLIC-data paper-worker audit. Never an exchange execution tool.

Run as a module. Raw public responses and account evidence stay in ignored
reports/. An optional, explicitly labeled timeout tests recovery without altering
any market candle. The production PaperLoop and all risk/quality rules are reused.
"""

import argparse
import hashlib
import json
import logging
import platform
import sqlite3
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from threading import Event, Timer

from config import Settings
from data.coindcx import HttpResponse, PublicClient, unsigned_get
from data.schema import utc
from paper_trading import session
from paper_trading.commands import open_account
from paper_trading.continuous import PaperLoop, PublicFeed, ShutdownRequested, status
from paper_trading.persistence import PersistentPaperBroker
from strategies import create_strategy


def stamp():
    return datetime.now(timezone.utc).isoformat()


def save(path, value):
    path.write_text(json.dumps(value, indent=2, default=str) + "\n", encoding="utf-8")


def worker(args):
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    directory = args.output.resolve()
    requests = directory / "requests.jsonl"
    polls = directory / "fetches.jsonl"
    count = 0
    shutdown = Event()
    timer = Timer(args.seconds + 10, shutdown.set)
    timer.daemon = True
    timer.start()  # Child also has a bound if the supervising process disappears.

    def record(path, value):
        with path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(value, default=str) + "\n")

    def transport(url, timeout):
        nonlocal count
        if shutdown.is_set():
            raise ShutdownRequested()
        count += 1
        response = unsigned_get(url, timeout)
        name = f"public-response-{count:04d}.json"
        (directory / name).write_bytes(response.body)
        record(requests, {"at": stamp(), "method": "GET", "url": url,
                          "http": response.status, "file": name,
                          "sha256": hashlib.sha256(response.body).hexdigest()})
        return response

    class RecordedFeed(PublicFeed):
        calls = 0

        def fetch(self, symbol, start, end):
            self.calls += 1
            began = time.monotonic()
            if args.inject_timeout_once and self.calls == 2:
                record(polls, {"at": stamp(), "outcome": "INJECTED_TIMEOUT", "synthetic_fault": True})
                raise TimeoutError("explicit audit fault; no candle modified")
            try:
                first_request = count + 1
                batch = super().fetch(symbol, start, end)
            except Exception:
                record(polls, {"at": stamp(), "outcome": "PUBLIC_FETCH_ERROR", "synthetic_fault": False})
                raise
            name = f"batch-{self.calls:04d}.json"
            captured_at = stamp()
            save(directory / name, {"label": "ACTUAL_PUBLIC_RESPONSE_NORMALIZED_NOT_QUALIFIED",
                                    "as_of": captured_at, "metadata": batch.metadata, "rows": batch.rows})
            record(polls, {"at": captured_at, "outcome": "PUBLIC_FETCH_OK", "file": name,
                           "rows": len(batch.rows), "seconds": time.monotonic() - began,
                           "first_request": first_request, "last_request": count,
                           "sha256": hashlib.sha256((directory / name).read_bytes()).hexdigest(),
                           "synthetic_fault": False})
            return batch

    account = PersistentPaperBroker.create(directory / "paper.sqlite3", Settings(mode="paper"),
                                           symbol=args.pair, data_kind="historical")
    loop = None
    try:
        def wait(seconds):
            if shutdown.wait(seconds):
                raise ShutdownRequested()
        client = PublicClient(transport=transport, sleep=wait, max_retry_delay=5)
        loop = PaperLoop(account, create_strategy(account._settings.strategy),
                         feed=RecordedFeed(client), poll_seconds=10, shutdown=shutdown)
        loop.run()
    finally:
        timer.cancel()
        if loop is not None:
            save(directory / "last-quality.json", loop.last_report)
        if not account._failed:
            save(directory / "worker-final.json", status(account))
        account.close()


def read_lines(path):
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def audit(args):
    if not 10 <= args.seconds <= 300:
        raise ValueError("audit duration must be 10..300 seconds")
    directory = args.output.resolve()
    directory.mkdir(parents=True, exist_ok=False)  # Never overwrite evidence/accounts.
    markets = PublicClient(max_retry_delay=5).discover()
    choices = [m for m in markets if m.active_confirmed and m.quote_currency == "INR"]
    matching = [m for m in choices if m.pair == args.pair] if args.pair else [m for m in choices if m.asset_currency == "BTC"]
    if not matching:
        raise ValueError("requested/default pair not confirmed active; no substitute invented")
    pair = matching[0].pair
    command = [sys.executable, "-m", "tools.phase8_stability", "--worker", "--output", str(directory),
               "--pair", pair, "--seconds", str(args.seconds)]
    if args.inject_timeout_once:
        command.append("--inject-timeout-once")
    snapshots, stop_error = [], None
    began, began_at = time.monotonic(), stamp()
    with (directory / "worker.stdout").open("w") as out, (directory / "worker.stderr").open("w") as err:
        process = subprocess.Popen(command, stdout=out, stderr=err)
        try:
            deadline = began + args.seconds
            while process.poll() is None and time.monotonic() < deadline:
                if (directory / "fetches.jsonl").exists():
                    account = open_account(directory / "paper.sqlite3")
                    try:
                        snapshots.append({"at": stamp(), "status": status(account)})
                    finally:
                        account.close()
                time.sleep(min(2, max(0, deadline - time.monotonic())))
        finally:
            if process.poll() is None:
                try:
                    account = open_account(directory / "paper.sqlite3")
                    try:
                        session.stop(account)
                    finally:
                        account.close()
                except Exception as exc:
                    stop_error = type(exc).__name__  # No raw exceptions/provider text.
                    process.terminate()
                try:
                    process.wait(timeout=25)
                except subprocess.TimeoutExpired:
                    process.terminate()
                    try:
                        process.wait(timeout=15)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=5)
                    stop_error = "WORKER_EXCEEDED_SHUTDOWN_BUDGET"
    account = open_account(directory / "paper.sqlite3")
    try:
        final = status(account)
    finally:
        account.close()
    fetches, requests = read_lines(directory / "fetches.jsonl"), read_lines(directory / "requests.jsonl")
    report = {"phase": 8, "label": "ACTUAL_PUBLIC_DATA_WITH_EXPLICIT_FAULT_INJECTION" if args.inject_timeout_once else "ACTUAL_PUBLIC_DATA",
              "environment": {"python": platform.python_version(), "platform": platform.platform(), "sqlite": sqlite3.sqlite_version},
              "runner_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "started_at": began_at, "ended_at": stamp(), "actual_seconds_including_shutdown": time.monotonic() - began,
              "requested_seconds": args.seconds, "pair": pair, "confirmed_active_inr_markets": len(choices),
              "worker_exit_code": process.returncode, "shutdown_error": stop_error,
              "completed_public_fetches": sum(f["outcome"] == "PUBLIC_FETCH_OK" for f in fetches),
              "observed_public_fetch_failures": sum(f["outcome"] == "PUBLIC_FETCH_ERROR" for f in fetches),
              "injected_timeouts": sum(f["outcome"] == "INJECTED_TIMEOUT" for f in fetches),
              "public_http_requests": len(requests), "non_200_responses": sum(r["http"] != 200 for r in requests),
              "processed_candles": final["processed_candles"], "simulated_entries": final["risk"]["entries_today"],
              "simulated_closed_trades": final["closed_trades"], "final": final, "fetches": fetches,
              "observations": snapshots, "requests": requests, "private_requests": 0, "orders_submitted": 0,
              "limitations": ["Bounded safe-rejection/recovery evidence, not 24/7 or eligible-fill qualification.",
                              "Injected faults are not observed exchange failures; candles are never synthesized.",
                              "Daily entry count is for this short run's UTC accounting day."]}
    save(directory / "evidence.json", report)
    print(json.dumps({key: value for key, value in report.items() if key not in {"observations", "requests", "final", "fetches"}}, indent=2))
    return 0 if process.returncode == 0 and stop_error is None and final["risk"]["emergency_halted"] else 2


def replay(directory):
    """Replay exact archived public HTTP bytes, offline; require ZERO_VOLUME."""
    directory = directory.resolve()
    evidence = json.loads((directory / "evidence.json").read_text(encoding="utf-8"))
    capture = next(f for f in evidence["fetches"] if f["outcome"] == "PUBLIC_FETCH_OK")
    batch_bytes = (directory / capture["file"]).read_bytes()
    if hashlib.sha256(batch_bytes).hexdigest() != capture["sha256"]:
        raise ValueError("recorded normalized batch checksum mismatch")
    original = json.loads(batch_bytes)
    requests = evidence["requests"][capture["first_request"] - 1:capture["last_request"]]
    index = 0

    def transport(url, timeout):
        nonlocal index
        record = requests[index]
        index += 1
        if record["url"] != url or record["method"] != "GET":
            raise ValueError("recorded public route does not match replay")
        raw = (directory / record["file"]).read_bytes()
        if hashlib.sha256(raw).hexdigest() != record["sha256"]:
            raise ValueError("recorded public response checksum mismatch")
        return HttpResponse(record["http"], raw, {})

    at = utc(original["as_of"])
    client = PublicClient(transport=transport, now=lambda: at, request_interval=0)
    with tempfile.TemporaryDirectory(prefix="phase8-offline-replay-") as temp:
        settings = Settings(mode="paper")
        account = PersistentPaperBroker.create(Path(temp) / "paper.sqlite3", settings,
                         symbol=evidence["pair"], data_kind="historical")
        try:
            loop = PaperLoop(account, create_strategy(settings.strategy), feed=PublicFeed(client),
                             now=lambda: at, poll_seconds=10)
            loop.start()
            before = account.snapshot().state_json
            health = loop.poll()
            snapshot = account.snapshot()
            result = {"label": "OFFLINE_REPLAY_OF_ACTUAL_PUBLIC_HTTP_BYTES_NOT_SYNTHETIC_CANDLES",
                      "capture_as_of": original["as_of"], "private_requests": 0, "network_requests": 0,
                      "replayed_responses": index, "health": health, "quality": loop.last_report,
                      "equity": snapshot.state["equity"], "processed_candles": snapshot.processed_candles,
                      "financial_state_unchanged": snapshot.state_json == before, "orders_submitted": 0}
            passed = (index == len(requests) and health == "DATA_BLOCKED"
                      and snapshot.runtime["reason"] == "ZERO_VOLUME" and snapshot.state_json == before
                      and snapshot.state["equity"] == "2000" and snapshot.processed_candles == 0)
            result["zero_volume_preservation_status"] = "PASS" if passed else "FAIL"
            save(directory / "replay-evidence.json", result)
            print(json.dumps(result, indent=2, default=str))
            return 0 if passed else 2
        finally:
            account.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    destination = parser.add_mutually_exclusive_group(required=True)
    destination.add_argument("--output", type=Path, help="NEW directory, normally under ignored reports/")
    destination.add_argument("--replay", type=Path, help="offline replay of a recorded audit; never fetches")
    parser.add_argument("--seconds", type=int, default=60)
    parser.add_argument("--pair", help="exact public-discovered INR native pair (default: discovered BTC/INR)")
    parser.add_argument("--inject-timeout-once", action="store_true", help="label and inject one fetch timeout; never modify candles")
    parser.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if not 10 <= args.seconds <= 300:
        parser.error("audit duration must be 10..300 seconds")
    if args.replay:
        return replay(args.replay)
    if args.worker:
        worker(args)
        return 0
    return audit(args)


if __name__ == "__main__":
    raise SystemExit(main())
