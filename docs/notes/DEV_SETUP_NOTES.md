# xtquant_big_convert — Dev Setup Notes

Session summary, 2026-10-11. Covers what the project is, how to set up a development
environment with pip or uv, PyCharm configuration, and background on packaging choices.

---

## 1. What the project is

**xtquant_big_convert** is an RPC bridge for "Big QMT", the full desktop trading
terminal from 迅投 (Thinktrader) used with Chinese brokers. Big QMT embeds a locked-down
Python 3.6 that can see quotes, positions and order functions, but only from inside the
terminal. This package runs a small server inside that Python and exposes those
capabilities over a network transport, so external programs can call them without the
paid XtQuantServer / MiniQMT permission.

Three parts:

| Part | Where it runs | Location in repo |
|---|---|---|
| **Server** | QMT's embedded Python 3.6 | `src/bigqmt_signal_trader/` plus top-level entry scripts (`BIGQMT_REDIS_DRYRUN.py`, `BIGQMT_ZMQ_DRYRUN.py`, ...) |
| **Transports** | Both sides | `src/bigqmt_signal_trader/transports/` — Redis, ZeroMQ or MySQL, switched by one config field |
| **Client** | Your dev machine, Python 3.8–3.13 | `xtquant_compat.py` and the `src/xtquant/` shim, which mimic MiniQMT's `xtdata` / `xt_trader` API |

Also included: a `bigqmt_backtest` engine, the `bigqmt-init` config wizard, a 47-subcommand
CLI skill for AI assistants in `qmt-trader/`, and a Windows one-click deploy script in `deploy/`.

- Published on PyPI as `xtquant-big-convert`, version 0.3.62, MIT licensed.
- About 137 read-only RPC methods plus 3 order methods. Order methods are **off by default**
  (`rpc_allow_order_methods=False`).
- `README.md` holds only the intro and disclaimer. Real docs are in `docs/USER_GUIDE.md`
  and the other files under `docs/`. Tests are the behavior contract.

---

## 2. Facts that affect setup

- **Only the client side is developable on a Mac.** Server code needs a running Windows
  Big QMT terminal. `run_all_tests.py` skips live tests unless you pass `--live`.
- **Tested Python range is 3.8–3.13.** The system Python here is 3.14, which is untested.
  The full offline suite did pass on 3.14, but if anything is odd, retry under 3.13 first.
- **`redis` must stay `<8.0.0`.** redis-py 8.x raises default retries to 10, and RPC
  requests use non-idempotent `RPUSH`, so a retried order could dispatch twice (issue #245).
- **pandas is an undeclared test dependency.** Six tests fail at collection without it.
  No extra pulls it in; install it by hand.
- **The `mysql` extra is required for a green test run.** One transport test fails
  without DBUtils.
- **The committed `uv.lock` is stale.** It records version 0.1.0, lacks the `mysql` and
  `msgpack` extras, and pins redis 8.0.1 on Python 3.10+. `uv sync` re-resolves and
  rewrites it. Do not use `uv sync --locked` or `--frozen` with the stale file.
- **Server-side code runs on Python 3.6.** Code under `src/bigqmt_signal_trader` that
  executes inside QMT must avoid 3.7+ syntax (walrus, positional-only params, etc.).
- **Never commit** `bigqmt_signal_trader_local_config.py` or
  `bigqmt_signal_trader_client_config.py`. They hold account ids and Redis passwords.
  Their `.gitignore` entries are commented out, so git will stage them.

Verified offline test results (Python 3.14, all extras + pandas):

| Group | Result |
|---|---|
| signal_trader | 2313 passed, 25 skipped |
| backtest | 33 passed |
| root-level `tests/*.py` | 77 passed |

---

## 3. Setup with uv

uv 0.13.0 is installed at `~/.local/bin/uv`. CPython 3.11.17 is already available to uv,
so no download is needed.

### 3a. Manual venv, pip-style installs (leaves `uv.lock` untouched)

```bash
cd /Users/colin/wnix/m0/02code/public/xtquant_big_convert

uv venv --python 3.11                  # creates .venv with CPython 3.11.17
source .venv/bin/activate

uv pip install -e ".[dev,redis,mysql,msgpack]"
uv pip install pandas

python -c "import sys, bigqmt_signal_trader, redis, pandas; print(sys.version, redis.__version__)"
python run_all_tests.py
```

Notes:
- `uv pip install` is a drop-in replacement for `pip install`. A uv-created venv has no
  `pip` binary, so plain `pip install` fails there. Use `uv pip install` or run
  `uv pip install pip` once.
- Nothing in the repo changes except the gitignored `.venv`.

### 3b. Project workflow with lockfile (`uv sync`)

```bash
cd /Users/colin/wnix/m0/02code/public/xtquant_big_convert

uv python pin 3.11                     # writes .python-version
uv sync --all-extras                   # creates .venv, installs all extras, rewrites uv.lock
uv pip install pandas                  # or: uv add --optional dev pandas

uv run python -c "import sys, bigqmt_signal_trader, redis, pandas; print(sys.version)"
uv run python run_all_tests.py
```

`uv sync --all-extras` means: create `.venv` if missing, re-resolve `uv.lock` if
`pyproject.toml` changed, install exactly the locked versions plus the project in editable
mode, and remove anything not in the lock. `--all-extras` adds every optional group
(`redis`, `mysql`, `msgpack`, `dev`); without it you get only pyzmq.

After this, `uv.lock` is modified and `.python-version` is untracked. Either commit both
(the refreshed lock fixes the redis 8.x pin) or `git checkout uv.lock` and add
`.python-version` to `.gitignore`.

To undo everything from 3b: `rm -rf .venv .python-version && git checkout uv.lock`.

### Useful test runner options

```bash
python run_all_tests.py -v                      # verbose
python run_all_tests.py --group backtest        # one group
python run_all_tests.py --group signal_trader
python run_all_tests.py --live                  # needs running QMT + Redis
python -m pytest tests/*.py -q                  # root-level tests, not in run_all_tests groups
```

Live tests read these environment variables: `BIGQMT_ACCOUNT_ID`, `BIGQMT_REDIS_HOST`,
`BIGQMT_REDIS_PORT`, `BIGQMT_REDIS_DB`, `BIGQMT_REDIS_PASSWORD`.

Other entry points:
- `python -m bigqmt_signal_trader.init_config` — config wizard (same as `bigqmt-init`)
- `tools/build_single_file.py` — builds the all-in-one deploy artifacts (gitignored)

---

## 4. PyCharm setup

1. **Open** the project root as a project. `.idea/` is already gitignored.
2. **Interpreter:** Settings > Project > Python Interpreter > Add Interpreter > Add Local
   Interpreter > "Select existing" > type **uv** (PyCharm 2024.3+) or **Virtualenv** >
   browse to `.venv/bin/python`. If you let PyCharm generate the venv instead, still run
   `uv pip install -e ".[dev,redis,mysql,msgpack]" pandas` in the terminal afterwards.
3. **Sources root:** right-click `src` > Mark Directory as > Sources Root. The package
   lives under `src`, and this makes navigation and inspections resolve
   `bigqmt_signal_trader`. Optionally mark `tests` as Test Sources Root.
4. **Test runner:** Settings > Tools > Python Integrated Tools > Testing > **pytest**.
5. **Run configurations** (working directory = project root for all):
   - Offline suite: script `run_all_tests.py`, optional params `--group backtest`, `-v`.
   - Live suite: same script with `--live`, and the `BIGQMT_*` variables in the
     Environment field rather than in a config file.
6. **Exclude** `.venv`, `backtest_runs/`, `qmt_backtest_runs/`, `build/` if they appear.
7. **Terminal:** PyCharm's terminal activates the venv automatically. In a system
   terminal run `source .venv/bin/activate` first.

---

## 5. Background: uv vs pip, and packaging questions

### uv vs pip for this project
- Both read the same `pyproject.toml`. The project has no uv-specific config.
- uv is much faster, creates the venv for you, and maintains `uv.lock` with every
  transitive package pinned. pip records nothing.
- Nothing in the code or tests cares which tool installed the packages.

### Why there is no `requirements.txt`
- `pyproject.toml` (PEP 621) is the single source of truth. When a user runs
  `pip install xtquant-big-convert[redis]`, pip reads dependencies from the package
  metadata on PyPI. A `requirements.txt` in the GitHub repo would never reach that user.
- Extras (`redis`, `mysql`, `msgpack`, `dev`) let a ZMQ-only user skip redis and MySQL
  packages. A flat requirements file cannot express that.
- `uv.lock` covers the "exact pins" role.
- If a tool insists on one: `uv pip compile pyproject.toml --all-extras -o requirements.txt`
  or `uv export --format requirements-txt -o requirements.txt`.

### Does `pyproject.toml` work for application projects?
Yes. Same format, different usage:
- Keep direct dependencies with sensible ranges in `pyproject.toml`; deploy from the
  lockfile (`uv.lock`, `poetry.lock`, `pdm.lock`).
- Apps usually skip `[build-system]`; uv then treats the project as virtual (venv +
  lock, no wheel build).
- Put dev tools in `[dependency-groups]` (PEP 735), not in extras. Extras are public
  package metadata for end users; dependency groups are private to developers.
  `uv sync` installs the `dev` group by default.
- Day to day: `uv add pkg`, `uv sync`; in production `uv sync --frozen --no-dev`.

Minimal app manifest:

```toml
[project]
name = "my-app"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = ["fastapi>=0.115", "uvicorn>=0.30"]

[dependency-groups]
dev = ["pytest>=8", "ruff"]

[project.scripts]
my-app = "my_app.cli:main"
```

---

## 6. Mapping an in-QMT API layer onto this project

Inside Big QMT a strategy receives `ContextInfo` (often named `g`) and calls
`g.get_full_tick`, `get_trade_detail_data`, `passorder`, ... With this project the
strategy runs **outside** QMT and talks to it over RPC through
`bigqmt_signal_trader.xtquant_compat`, so `g` disappears: market data goes through the
`xtdata` object and trading through `xt_trader`, using **MiniQMT method names**.

### One-time setup

Put `bigqmt_signal_trader_client_config.py` next to your script (copy
`src/bigqmt_signal_trader_client_config.example.py`), then:

```python
from bigqmt_signal_trader.xtquant_compat import configure, xt_trader, xtdata, StockAccount
from xtquant.xtconstant import STOCK_BUY, STOCK_SELL, FIX_PRICE

configure()   # reads the client config; updates xt_trader / xtdata in place
```

Account arguments accept a plain id string or `StockAccount(acc_id, "STOCK")`.

### Call-by-call

| In-QMT call | xtquant_big_convert equivalent | Notes |
|---|---|---|
| `g.run_time(func_name, period, start)` | none | QMT's in-process scheduler. Schedule yourself (thread, APScheduler) or use `xtdata.subscribe_whole_quote(codes, callback=...)` for tick-driven work |
| `timetag_to_datetime(ms, pattern)` | `xtdata.timetag_to_datetime(ms, pattern)` | local computation, no RPC |
| `g.get_full_tick(codes)` | `xtdata.get_full_tick(codes)` | dict keyed by code, same field names; `timeout_seconds=` for big lists |
| `g.get_full_tick([code])[code]` | `xtdata.get_full_tick([code])[code]` | |
| `g.get_instrumentdetail(code)` | `xtdata.get_instrument_detail(code)` | alias `get_instrumentdetail` also exists |
| `get_trade_detail_data(acc, 'stock', 'account')` | `xt_trader.query_stock_asset(acc)` | returns **one object**, not a list: `cash`, `frozen_cash`, `market_value`, `total_asset` plus `m_d*` aliases |
| `get_trade_detail_data(acc, 'stock', 'position')` | `xt_trader.query_stock_positions(acc)` | list of objects: `stock_code`, `volume`, `can_use_volume`, `avg_price`, `market_value` plus `m_*` aliases |
| `get_trade_detail_data(acc, 'stock', 'order', strat)` | `xt_trader.query_stock_orders(acc, cancelable_only=False, strategy_name=strat or "")` | `""` returns all orders |
| `get_trade_detail_data(acc, 'stock', 'deal', strat)` | `xt_trader.query_stock_trades(acc, strategy_name=strat or "")` | |
| `passorder(23, 1101, acc, code, 11, price, vol, clid, 2, '', g)` | `xt_trader.order_stock(acc, code, STOCK_BUY, vol, FIX_PRICE, price, clid, "")` | returns order id or -1 |
| `passorder(24, 1101, acc, code, 11, price, vol, clid, 2, '', g)` | `xt_trader.order_stock(acc, code, STOCK_SELL, vol, FIX_PRICE, price, clid, "")` | |
| `cancel(order_id, acc, 'stock', g)` | `xt_trader.cancel_order_stock(acc, order_id)` | 0 on success, -1 on failure |

Constants: 23/24 are `STOCK_BUY`/`STOCK_SELL`, 11 is `FIX_PRICE`, 1101 and quick_trade 2
are supplied server-side as defaults.

### Things that differ from in-QMT behaviour

- **Order methods are off by default.** Server config needs `rpc_allow_order_methods=True`.
- **`order_stock` vs `passorder`.** `order_stock` waits for the order id, validates, and
  on timeout checks whether the order went through before you retry. A raw
  `xt_trader.passorder(23, 1101, acc, code, 11, price, vol, strategy_name=clid, quick_trade=2)`
  also exists: async, returns only an ack dict, no safety nets. `dry_run=True` returns the
  exact tuple the server would pass.
- **`strategy_name` filtering only sees bridge-placed orders.** QMT's ORDER/DEAL rows carry
  no strategy name; the bridge back-fills it from its own records. Manually placed orders
  come back with `""`.
- **Order ids** wrap the broker's contract-number string; usable as int or string, pass
  straight back to `cancel_order_stock`.

### Abstract API + live adapter + mock

The classes live in the **alamar** project, not in this repo:
`appcarrier/apps/alamar/app/tasks/qmt_api/` (import as `app.tasks.qmt_api`).

| File | What |
|---|---|
| `base.py` | `QmtApi` abstract base class with the method set above (`timetag_to_datetime`, `get_full_tick[_one]`, `get_instrumentdetail`, `get_account_data`, `get_position_data`, `get_order_data`, `get_deal_data`, `buy`, `sell`, `cancel`) and the xtconstant values it needs. No `run_time`: scheduling is the caller's job |
| `bigconvert.py` | `BigConvertQmtApi(QmtApi)`: the table above as code. `order_route="order_stock"` (default, `buy`/`sell` return order id or -1) or `"passorder"` (native call, `buy`/`sell` return the ack dict). `buy_native` / `sell_native` always take the native route, with `dry_run=True` to see the args without ordering |
| `mock.py` | `MockQmtApi(QmtApi)`: in-memory cash/positions/orders/deals. `set_tick()`, `fill()`, `auto_fill=True` |
| `__init__.py` | re-exports the three classes and the constants |
| `../../../tests/test_qmt_api_mock.py` | 14 pytest cases (mock behaviour plus both order routes of the live adapter against a fake trader), including a tiny strategy (`rebalance_to_target`) written against `QmtApi` and run on the mock |

Strategy code should take a `QmtApi` and never import the concrete classes:

```python
def rebalance_to_target(api, acc_id, code, target_volume, clid):
    held = {p.stock_code: p.volume for p in api.get_position_data(acc_id)}.get(code, 0)
    delta = target_volume - held
    if delta == 0:
        return None
    price = api.get_full_tick_one(code)["lastPrice"]
    return api.buy(acc_id, code, price, delta, clid) if delta > 0 \
        else api.sell(acc_id, code, price, -delta, clid)
```

Run the mock tests:

```bash
cd appcarrier/apps/alamar
uv run --with pytest python -m pytest tests -q      # pytest is not in alamar's deps
```

Swap in the live adapter with `api = BigConvertQmtApi()` once a QMT server and the client
config are in place. The mock is deliberately simple: T+0 availability, no price limits, no
lot-size checks, fills at the limit price.
