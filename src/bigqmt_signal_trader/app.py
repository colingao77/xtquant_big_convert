"""信号交易应用编排层。"""

import datetime as _dt

from .models import AccountSnapshot, OrderRequest, SignalAction
from .price_engine import build_order_price
from .risk_guard import validate_signal


class SignalTradingApp:
    def __init__(
        self,
        account_id,
        signal_source,
        market_data,
        position_provider,
        order_gateway,
        position_sync_sink,
        state_store,
        consumer_id="bigqmt-signal-trader",
        fetch_limit=20,
        position_sync_interval_seconds=0.0,
    ):
        """
        ``position_sync_interval_seconds`` rate-limits the per-tick position
        sync: 0 (default) syncs on every tick as before; N > 0 syncs at most
        once per N seconds. Event-driven syncs (``trade_event``) are never
        limited. Every sync is two or three native ``get_trade_detail_data``
        calls, and the terminal keeps a few KB per call (measured: ~5-8KB per
        adjust tick, 480MB over 95 minutes at 10 ticks/s with no client).
        """
        self.account_id = account_id
        self.signal_source = signal_source
        self.market_data = market_data
        self.position_provider = position_provider
        self.order_gateway = order_gateway
        self.position_sync_sink = position_sync_sink
        self.state_store = state_store
        self.consumer_id = consumer_id
        self.fetch_limit = int(fetch_limit)
        self.position_sync_interval_seconds = max(0.0, float(position_sync_interval_seconds or 0.0))
        self._last_tick_sync_at = None

    def tick(self, now=None):
        now = now or _dt.datetime.now()
        signals = self.signal_source.fetch(self.account_id, self.fetch_limit)
        # Positions are only needed to validate signals. Fetching them up
        # front cost one native get_trade_detail_data per tick on every
        # deployment, signals or not; sync_positions below fetches its own.
        positions = self.position_provider.get_positions(self.account_id) if signals else {}

        for signal in signals:
            if not self.state_store.claim(signal, self.consumer_id):
                continue
            try:
                self._handle_signal(signal, now, positions)
            except Exception as exc:
                self.state_store.mark_finished(signal.signal_id, "FAILED", str(exc))
                self.signal_source.ack(signal)

        self.sync_positions("tick", now=now)

    def _handle_signal(self, signal, now, positions):
        decision = validate_signal(signal, now, positions)
        if not decision.allowed:
            self.state_store.mark_finished(signal.signal_id, "SKIPPED", decision.reason)
            self.signal_source.ack(signal)
            return

        price = build_order_price(
            self.market_data,
            decision.stock_code,
            signal.action.value,
            price_type=signal.price_type,
            fixed_price=signal.price,
        )
        request = OrderRequest(
            signal_id=signal.signal_id,
            account_id=signal.account_id,
            action=signal.action.value,
            stock_code=decision.stock_code,
            volume=decision.volume,
            price=price,
            price_type="LIMIT",
            strategy_name=signal.strategy_name,
            remark=signal.remark,
        )
        result = self.order_gateway.submit(request)
        self.state_store.mark_submitted(signal.signal_id, result)
        self.signal_source.ack(signal)

    def on_init(self, runtime):
        return None

    def on_order_event(self, event):
        return None

    def on_trade_event(self, event):
        self.sync_positions("trade_event")

    def sync_positions(self, reason, now=None):
        now = now or _dt.datetime.now()
        # A sink that discards snapshots (pipe / zmq deployments with no Redis
        # position cache) gets nothing from the two or three native queries a
        # sync costs -- and the terminal keeps memory on every one of them.
        # Duck-typed so the app never imports adapter_factory (it imports us).
        if getattr(self.position_sync_sink, "is_noop", False):
            return None
        if reason == "tick" and self.position_sync_interval_seconds > 0:
            last = self._last_tick_sync_at
            if last is not None:
                try:
                    elapsed = (now - last).total_seconds()
                except Exception:
                    elapsed = None
                if elapsed is not None and 0 <= elapsed < self.position_sync_interval_seconds:
                    return None
            self._last_tick_sync_at = now
        asset = self.position_provider.get_asset(self.account_id)
        positions = self.position_provider.get_positions(self.account_id)
        snapshot = AccountSnapshot(
            account_id=self.account_id,
            asset=asset,
            positions=positions,
            reason=reason,
            updated_at=now,
        )
        self.position_sync_sink.publish(snapshot)
