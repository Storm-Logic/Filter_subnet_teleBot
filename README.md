# Bittensor Incentive Burn Filter

Lists active Bittensor subnets whose owner hotkey receives less than 100% of
the subnet's miner incentive. Incentive assigned to the subnet owner hotkey is
burned by default (or recycled when the subnet configures recycling).

Results are sorted by estimated total miner TAO reward per day, highest first:

```text
7200 * 0.41 * (1 - burn rate) * current alpha price in TAO
```

This is the subnet's total post-burn miner reward pool. An individual miner's
reward also depends on its incentive share.

`REGS 24H` counts currently registered neurons whose registration block is
within the latest 7,200 blocks (approximately 24 hours). A neuron that
registered and was deregistered within that period is not present in the
current metagraph and therefore is not counted.

`REG COST TAO` is the subnet's current recycled TAO cost for one neuron
registration.

## Usage

Install the dependency:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Scan all non-root subnets on mainnet:

```bash
python filter_subnets.py
```

Progress is printed as each subnet completes, with elapsed time and an
estimated time remaining. Use `--quiet` to hide progress messages.

Continuously refresh the table after each completed scan:

```bash
python filter_subnets.py --watch
python filter_subnets.py --watch --interval 10
```

The default pause between scans is 30 seconds. Press `Ctrl+C` to stop.

Inspect selected subnets or use a stricter threshold:

```bash
python filter_subnets.py --netuids 1 18 64
python filter_subnets.py --max-burn 90
```

Machine-readable output:

```bash
python filter_subnets.py --format json
python filter_subnets.py --format csv > subnets.csv
```

Use `--network test` for testnet or pass a WebSocket endpoint to `--network`.
