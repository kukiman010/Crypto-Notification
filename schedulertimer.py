"""
scheduler_timer.py

Готовый модуль:
- generate_schedule(limit_per_month, days_in_month=31, weights=None, tz_out='UTC', use_all_budget=False)
    -> возвращает расписание на день (список времён) и метрики.

- TimerScheduler(daily_times, callback=None, tz_out='UTC', name=None)
    -> запускает планировщик в отдельном потоке, по срабатыванию кладёт "сигнал" в signal_queue
       и опционально вызывает callback(signal_dict).

Сигнал (dict), который помещается в signal_queue и передаётся callback:
{
  'scheduled_time': 'YYYY-MM-DDTHH:MM:SS±hh:mm' (строка, время в tz_out),
  'fired_time': 'YYYY-MM-DDTHH:MM:SS±hh:mm' (строка),
  'since_last_seconds': float,
  'window_index': int,
  'window_range': (start_h, end_h)  # UTC часы окна
  'utc_fired': 'YYYY-MM-DDTHH:MM:SSZ'
}

Требования: Python 3.9+ (zoneinfo). Никаких внешних зависимостей.
"""

from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo
import threading
import time as time_module
import math
from typing import List, Dict, Optional, Tuple
from queue import Queue, Empty

# ---- Конфигурация окон (в UTC) ----
WINDOWS_UTC = [
    (7, 12),   # 07:00 - 12:00 UTC (300 мин)
    (12, 16),  # 12:00 - 16:00 UTC (240 мин)  <-- пик EU+US
    (16, 20),  # 16:00 - 20:00 UTC (240 мин)
    (20, 24),  # 20:00 - 00:00 UTC (240 мин)
    (0, 7),    # 00:00 - 07:00 UTC (420 мин)
]

DEFAULT_WEIGHTS = [0.1875, 0.5, 0.1875, 0.0625, 0.0625]


def minutes_in_window(start_h: int, end_h: int) -> int:
    start = start_h
    end = end_h if end_h > start_h else end_h + 24
    return (end - start) * 60


def generate_schedule(limit_per_month: int,
                      days_in_month: int = 31,
                      weights: Optional[List[float]] = None,
                      tz_out: str = 'UTC',
                      use_all_budget: bool = False) -> Dict:
    """
    Возвращает словарь с расписанием и метриками.
    - use_all_budget=False (по умолчанию) — берем floor(limit/days)*days, не тратим остаток.
    - use_all_budget=True — постараемся распределить residual по дням (равномерно).
    Результат:
    {
      'daily_requests': int,
      'monthly_used': int,
      'residual_monthly': int,
      'windows': [ { 'window': (start,end), 'minutes': X, 'requests': n, 'interval_min': y, 'times': [...] }, ... ],
      'daily_times_flat': ['HH:MM:SS', ...]  # отсортированные локальные времена
    }
    """
    if weights is None:
        weights = DEFAULT_WEIGHTS
    assert len(weights) == len(WINDOWS_UTC), "weights length mismatch"

    base_daily = limit_per_month // days_in_month
    monthly_used = base_daily * days_in_month
    residual = limit_per_month - monthly_used
    if use_all_budget and residual > 0:
        # Простой режим: увеличиваем base_daily на 1 для первых `residual` дней в месяце.
        # Но для ежедневного расписания мы оставим ровное daily_requests = base_daily, а
        # сигнализируем, что нужно добавить +1 в первые residual дней. Это можно обработать
        # на уровне вызова генератора (не реализуем ежедневную вариацию здесь).
        pass

    daily_requests = base_daily

    # распределяем по окнам пропорционально весам
    raw = [w * daily_requests for w in weights]
    counts = [int(math.floor(x)) for x in raw]
    deficit = daily_requests - sum(counts)
    if deficit > 0:
        fracs = [(raw[i] - counts[i], i) for i in range(len(raw))]
        fracs.sort(reverse=True)
        for _, idx in fracs[:deficit]:
            counts[idx] += 1

    tz = ZoneInfo(tz_out) if tz_out != 'UTC' else timezone.utc
    windows_output = []
    daily_times = []

    today_utc = datetime.now(timezone.utc).date()

    for widx, (start_h, end_h) in enumerate(WINDOWS_UTC):
        n = counts[widx]
        mins = minutes_in_window(start_h, end_h)
        if n <= 0:
            windows_output.append({
                'window': (start_h, end_h),
                'minutes': mins,
                'requests': 0,
                'interval_min': None,
                'times': []
            })
            continue
        interval_seconds = (mins * 60) / n
        first_offset = interval_seconds / 2.0
        times_in_window = []
        start_dt = datetime.combine(today_utc, time(hour=0, minute=0, second=0, tzinfo=timezone.utc)) + timedelta(hours=start_h)
        for k in range(n):
            t_utc = start_dt + timedelta(seconds=(first_offset + k * interval_seconds))
            t_local = t_utc.astimezone(tz)
            times_in_window.append(t_local.strftime('%H:%M:%S'))
            daily_times.append((t_local, widx))
        windows_output.append({
            'window': (start_h, end_h),
            'minutes': mins,
            'requests': n,
            'interval_min': interval_seconds / 60.0,
            'times': times_in_window
        })

    # сортируем по локальному времени (dt, widx) -> сформируем строки и отдельный mapping window_index per time
    daily_times_sorted = sorted(daily_times, key=lambda x: x[0])
    daily_times_str = [dt.strftime('%H:%M:%S') for dt, _ in daily_times_sorted]
    daily_times_window_index = [widx for _, widx in daily_times_sorted]

    return {
        'daily_requests': daily_requests,
        'monthly_used': monthly_used,
        'residual_monthly': residual,
        'windows': windows_output,
        'daily_times_flat': daily_times_str,
        'daily_times_window_index': daily_times_window_index
    }


# ---- Планировщик, работающий в отдельном потоке ----
class TimerScheduler:
    """
    TimerScheduler:
    - daily_times: список "HH:MM:SS" в часовом поясе tz_out (текущая конфигурация расписания).
    - callback: необязательная функция callback(signal_dict). Вызывается из потока планировщика.
    - signal_queue: очередь (Queue) — в неё помещаются сигналы (signal_dict) для внешнего получения.
    - Методы: start(), stop(), join(timeout=None), is_running()
    """
    def __init__(self, daily_times: List[str], daily_window_indices: Optional[List[int]] = None,
                 callback=None, tz_out: str = 'UTC', name: Optional[str] = None):
        self.daily_times = sorted(daily_times)
        self.daily_window_indices = daily_window_indices or [None] * len(self.daily_times)
        self.callback = callback
        self.tz_out = tz_out
        self.name = name or f"TimerScheduler-{id(self)%10000}"
        self._stop_event = threading.Event()
        self._thread = None
        self.signal_queue: Queue = Queue()
        self._last_fired_time: Optional[datetime] = None

        # Validate times format
        for t in self.daily_times:
            hh, mm, ss = map(int, t.split(':'))
            assert 0 <= hh < 24 and 0 <= mm < 60 and 0 <= ss < 60

    def _next_scheduled_datetime(self, now_dt: datetime) -> Tuple[datetime, int]:
        """Возвращает ближайший datetime в tz_out и индекс в daily_times_window_index"""
        tz = ZoneInfo(self.tz_out) if self.tz_out != 'UTC' else timezone.utc
        today = now_dt.date()
        candidates = []
        for idx, tstr in enumerate(self.daily_times):
            hh, mm, ss = map(int, tstr.split(':'))
            dt = datetime.combine(today, time(hh, mm, ss), tz)
            if dt <= now_dt:
                dt += timedelta(days=1)
            candidates.append((dt, idx))
        next_dt, idx = min(candidates, key=lambda x: x[0])
        return next_dt, idx

    def _run_loop(self):
        tz = ZoneInfo(self.tz_out) if self.tz_out != 'UTC' else timezone.utc
        while not self._stop_event.is_set():
            now = datetime.now(tz)
            next_dt, idx = self._next_scheduled_datetime(now)
            wait_seconds = (next_dt - now).total_seconds()
            if wait_seconds > 0:
                # Спим до следующего события, но прерываем сон каждые 1 секунду для возможности стопа
                # (чтобы реагировать быстро на stop())
                # Если интервал маленький, просто sleep(wait_seconds)
                if wait_seconds > 2.0:
                    slept = 0.0
                    # блок sleep цикла с проверкой стопа
                    while slept < wait_seconds and not self._stop_event.is_set():
                        to_sleep = min(1.0, wait_seconds - slept)
                        time_module.sleep(to_sleep)
                        slept += to_sleep
                    if self._stop_event.is_set():
                        break
                else:
                    time_module.sleep(wait_seconds)
            # Если стоп был установлен во время ожидания — выйти
            if self._stop_event.is_set():
                break

            # Время достигнуто — формируем сигнал
            fired = datetime.now(tz)
            fired_utc = fired.astimezone(timezone.utc)
            since_last = None
            if self._last_fired_time is not None:
                since_last = (fired - self._last_fired_time).total_seconds()
            else:
                since_last = None  # первый запуск

            scheduled_time = next_dt  # уже в tz
            window_index = self.daily_window_indices[idx] if idx < len(self.daily_window_indices) else None
            window_range = WINDOWS_UTC[window_index] if (window_index is not None and 0 <= window_index < len(WINDOWS_UTC)) else None

            signal = {
                'scheduled_time': scheduled_time.isoformat(),
                'fired_time': fired.isoformat(),
                'since_last_seconds': since_last,
                'window_index': window_index,
                'window_range': window_range,
                'utc_fired': fired_utc.strftime('%Y-%m-%dT%H:%M:%SZ')
            }

            # Помещаем сигнал в очередь (не блокируя)
            try:
                self.signal_queue.put_nowait(signal)
            except Exception:
                # очередь не должна падать — в крайнем случае игнорируем
                pass

            # Вызываем callback (если задан)
            if self.callback:
                try:
                    self.callback(signal)
                except Exception as e:
                    # Не даём исключению убить поток
                    print(f"[{self.name}] Callback exception:", e)

            # Обновляем последний fired time
            self._last_fired_time = fired

            # Небольшая пауза перед следующей итерацией, чтобы цикл пересчитал следующий момент
            time_module.sleep(0.1)

    def start(self, daemon: bool = True):
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, name=self.name, daemon=daemon)
        self._thread.start()

    def stop(self, wait: bool = False, timeout: Optional[float] = None):
        self._stop_event.set()
        if wait and self._thread:
            self._thread.join(timeout=timeout)

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def join(self, timeout: Optional[float] = None):
        if self._thread:
            self._thread.join(timeout=timeout)



