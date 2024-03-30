#!/usr/bin/env python3
"""List Bittensor subnets whose owner incentive allocation is below a limit."""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from dataclasses import asdict, dataclass
from typing import Any, Iterable, Sequence

ALPHA_EMISSION_PER_DAY = 7200.0
MINER_EMISSION_SHARE = 0.41
BLOCKS_PER_DAY = 7200


@dataclass(frozen=True)
class SubnetBurn:
    netuid: int
    name: str
    incentive_burn_percent: float
    alpha_price_tao: float
    miner_tao_per_day: float
    registrations_24h: int
    registration_cost_tao: float


def as_float_list(values: Iterable[object]) -> list[float]:
    """Convert SDK list, NumPy array, or Torch tensor values to plain floats."""
    if hasattr(values, "detach"):
        values = values.detach()
    if hasattr(values, "cpu"):
        values = values.cpu()
    if hasattr(values, "tolist"):
        values = values.tolist()
    return [float(value) for value in values]


def calculate_owner_incentive_percent(
    hotkeys: Sequence[str],
    incentives: Iterable[object],
    owner_hotkey: str,
) -> tuple[float, list[int]]:
    incentive_values = as_float_list(incentives)
    if len(hotkeys) != len(incentive_values):
        raise ValueError(
            f"hotkey/incentive length mismatch: {len(hotkeys)} != "
            f"{len(incentive_values)}"
        )

    total = sum(incentive_values)
    owner_uids = [
        uid for uid, hotkey in enumerate(hotkeys) if hotkey == owner_hotkey
    ]
    owner_total = sum(incentive_values[uid] for uid in owner_uids)
    percent = 0.0 if total <= 0 else owner_total / total * 100.0
    return percent, owner_uids


def calculate_miner_tao_per_day(
    burn_percent: float,
    alpha_price_tao: float,
) -> float:
    unburned_share = 1.0 - burn_percent / 100.0
    return (
        ALPHA_EMISSION_PER_DAY
        * MINER_EMISSION_SHARE
        * max(0.0, unburned_share)
        * alpha_price_tao
    )


def count_recent_registrations(
    registration_blocks: Iterable[object],
    current_block: int,
    blocks_per_day: int = BLOCKS_PER_DAY,
) -> int:
    oldest_block = current_block - blocks_per_day
    return sum(int(block) >= oldest_block for block in registration_blocks)


def inspect_subnet(
    subtensor: Any,
    netuid: int,
    current_block: int,
) -> SubnetBurn:
    metagraph = subtensor.metagraph(netuid=netuid, lite=True)
    owner_hotkey = metagraph.owner_hotkey
    if not owner_hotkey:
        owner_hotkey = subtensor.get_subnet_owner_hotkey(netuid) or ""
    if not owner_hotkey:
        raise ValueError("subnet owner hotkey is unavailable")

    percent, _ = calculate_owner_incentive_percent(
        metagraph.hotkeys,
        metagraph.incentive,
        owner_hotkey,
    )
    alpha_price_tao = float(subtensor.get_subnet_price(netuid))
    registration_cost = subtensor.recycle(netuid)
    if registration_cost is None:
        raise ValueError("registration cost is unavailable")
    return SubnetBurn(
        netuid=netuid,
        name=str(getattr(metagraph, "name", "") or ""),
        incentive_burn_percent=percent,
        alpha_price_tao=alpha_price_tao,
        miner_tao_per_day=calculate_miner_tao_per_day(
            percent,
            alpha_price_tao,
        ),
        registrations_24h=count_recent_registrations(
            metagraph.block_at_registration,
            current_block,
        ),
        registration_cost_tao=float(registration_cost),
    )


def print_table(rows: Sequence[SubnetBurn]) -> None:
    headers = (
        "NETUID",
        "NAME",
        "BURN %",
        "ALPHA PRICE",
        "MINER TAO/DAY",
        "REGS 24H",
        "REG COST TAO",
    )
    body = [
        (
            str(row.netuid),
            row.name or "-",
            f"{row.incentive_burn_percent:.6f}",
            f"{row.alpha_price_tao:.9f}",
            f"{row.miner_tao_per_day:.6f}",
            str(row.registrations_24h),
            f"{row.registration_cost_tao:.9f}",
        )
        for row in rows
    ]
    widths = [
        max(len(headers[index]), *(len(row[index]) for row in body))
        for index in range(len(headers))
    ] if body else [len(header) for header in headers]

    def render(values: Sequence[str]) -> str:
        return "  ".join(
            value.ljust(widths[index]) for index, value in enumerate(values)
        )

    print(render(headers))
    print(render(tuple("-" * width for width in widths)))
    for row in body:
        print(render(row))


def print_csv(rows: Sequence[SubnetBurn]) -> None:
    writer = csv.DictWriter(
        sys.stdout,
        fieldnames=[
            "netuid",
            "name",
            "incentive_burn_percent",
            "alpha_price_tao",
            "miner_tao_per_day",
            "registrations_24h",
            "registration_cost_tao",
        ],
    )
    writer.writeheader()
    for row in rows:
        writer.writerow(
            {
                "netuid": row.netuid,
                "name": row.name,
                "incentive_burn_percent": f"{row.incentive_burn_percent:.9f}",
                "alpha_price_tao": f"{row.alpha_price_tao:.12f}",
                "miner_tao_per_day": f"{row.miner_tao_per_day:.9f}",
                "registrations_24h": row.registrations_24h,
                "registration_cost_tao": f"{row.registration_cost_tao:.9f}",
            }
        )


def format_duration(seconds: float) -> str:
    seconds = max(0, round(seconds))
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}h {minutes:02d}m {seconds:02d}s"
    if minutes:
        return f"{minutes}m {seconds:02d}s"
    return f"{seconds}s"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Find Bittensor subnets whose owner incentive allocation "
            "(incentive burn) is below a percentage."
        )
    )
    parser.add_argument(
        "--network",
        default="finney",
        help="Bittensor network or WebSocket endpoint (default: finney)",
    )
    parser.add_argument(
        "--max-burn",
        type=float,
        default=100.0,
        help="Exclusive maximum incentive burn percentage (default: 100)",
    )
    parser.add_argument(
        "--netuids",
        type=int,
        nargs="+",
        help="Only inspect these subnet IDs (default: all active subnets)",
    )
    parser.add_argument(
        "--include-root",
        action="store_true",
        help="Include root network netuid 0",
    )
    parser.add_argument(
        "--format",
        choices=("table", "json", "csv"),
        default="table",
        help="Output format (default: table)",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Hide per-subnet progress messages",
    )
    parser.add_argument(
        "--watch",
        action="store_true",
        help="Continuously rescan and redraw the result table",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=30.0,
        help="Seconds to wait between watch scans (default: 30)",
    )
    args = parser.parse_args()
    if not 0.0 <= args.max_burn <= 100.0:
        parser.error("--max-burn must be between 0 and 100")
    if args.interval < 0:
        parser.error("--interval cannot be negative")
    if args.watch and args.format != "table":
        parser.error("--watch currently supports only --format table")
    return args


def load_bittensor() -> Any:
    """Import Bittensor without allowing its config loader to consume our CLI."""
    original_argv = sys.argv[:]
    try:
        sys.argv[:] = [sys.argv[0]]
        import bittensor
    finally:
        sys.argv[:] = original_argv
    return bittensor


def get_netuids(subtensor: Any, args: argparse.Namespace) -> list[int]:
    netuids = (
        args.netuids
        if args.netuids is not None
        else [int(netuid) for netuid in subtensor.get_all_subnets_netuid()]
    )
    if not args.include_root:
        netuids = [netuid for netuid in netuids if netuid != 0]
    return sorted(set(netuids))


def scan_once(
    subtensor: Any,
    args: argparse.Namespace,
) -> tuple[list[SubnetBurn], int, float]:
    current_block = subtensor.get_current_block()
    netuids = get_netuids(subtensor, args)

    matches: list[SubnetBurn] = []
    failures = 0
    started_at = time.monotonic()
    total = len(netuids)
    if not args.quiet:
        print(
            f"Scanning {total} subnet(s) on {args.network}...",
            file=sys.stderr,
            flush=True,
        )

    for position, netuid in enumerate(netuids, start=1):
        try:
            subnet = inspect_subnet(subtensor, netuid, current_block)
        except Exception as error:
            failures += 1
            print(
                f"[{position}/{total}] netuid {netuid}: FAILED ({error})",
                file=sys.stderr,
                flush=True,
            )
            continue

        is_match = subnet.incentive_burn_percent < args.max_burn - 1e-9
        if is_match:
            matches.append(subnet)
        if not args.quiet:
            elapsed = time.monotonic() - started_at
            remaining = elapsed / position * (total - position)
            status = "MATCH" if is_match else "skip"
            print(
                f"[{position}/{total}] netuid {netuid} "
                f"({subnet.name or 'unnamed'}): "
                f"{subnet.incentive_burn_percent:.2f}% burn, {status} | "
                f"{subnet.miner_tao_per_day:.4f} miner TAO/day | "
                f"{subnet.registrations_24h} regs/24h | "
                f"{subnet.registration_cost_tao:.6f} TAO reg cost | "
                f"elapsed {format_duration(elapsed)}, "
                f"ETA {format_duration(remaining)}",
                file=sys.stderr,
                flush=True,
            )

    matches.sort(key=lambda row: (-row.miner_tao_per_day, row.netuid))
    elapsed = time.monotonic() - started_at
    return matches, failures, elapsed


def print_results(rows: Sequence[SubnetBurn], output_format: str) -> None:
    if output_format == "json":
        print(json.dumps([asdict(row) for row in rows], indent=2))
    elif output_format == "csv":
        print_csv(rows)
    else:
        print_table(rows)


def clear_terminal() -> None:
    if sys.stdout.isatty():
        print("\033[2J\033[H", end="", flush=True)


def main() -> int:
    args = parse_args()
    bt = load_bittensor()
    subtensor = bt.Subtensor(network=args.network)
    scan_number = 0
    last_status = 0

    try:
        while True:
            scan_number += 1
            if args.watch:
                clear_terminal()
                print(
                    f"Live subnet scan #{scan_number} | "
                    f"{time.strftime('%Y-%m-%d %H:%M:%S')}",
                    flush=True,
                )

            matches, failures, elapsed = scan_once(subtensor, args)

            if args.watch:
                clear_terminal()
                print(
                    f"Live subnet results | updated "
                    f"{time.strftime('%Y-%m-%d %H:%M:%S')} | "
                    f"scan {scan_number}",
                )
            print_results(matches, args.format)

            if failures:
                print(
                    f"warning: failed to inspect {failures} subnet(s)",
                    file=sys.stderr,
                )
            if not args.quiet:
                print(
                    f"Finished in {format_duration(elapsed)}; "
                    f"found {len(matches)} matching subnet(s).",
                    file=sys.stderr,
                )

            last_status = 1 if failures and not matches else 0
            if not args.watch:
                return last_status

            print(
                f"Next scan starts in {format_duration(args.interval)}. "
                "Press Ctrl+C to stop.",
                file=sys.stderr,
                flush=True,
            )
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nStopped live scanning.", file=sys.stderr)
        return last_status


if __name__ == "__main__":
    raise SystemExit(main())
