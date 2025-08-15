"""
schedule_timer.py

Функции:
- generate_schedule(limit_per_month, days=31, weights=None, tz_out='UTC')
    -> возвращает словарь с расписанием на день (в часовом поясе tz_out) и метрики.

- run_scheduler(daily_times, callback, tz_out='UTC')
    -> простой циклический планировщик, который бесперебойно выполняет callback
       в моменты, указанные в daily_times (список "HH:MM:SS" строк) каждый день.

Требования: Python 3.9+ (для zoneinfo). Для Python <3.9 замените zoneinfo на pytz.
"""

from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo
import time as time_module
import math
from typing import List, Dict, Tuple
import signals

# Описанные окна в UTC (start_hour, end_hour) — end_hour может быть 24 или > start
WINDOWS_UTC = [
    (7, 12),   # 07:00 - 12:00 UTC (300 min)
    (12, 16),  # 12:00 - 16:00 UTC (240 min)  <-- пик EU+US
    (16, 20),  # 16:00 - 20:00 UTC (240 min)
    (20, 24),  # 20:00 - 00:00 UTC (240 min)
    (0, 7),    # 00:00 - 07:00 UTC (420 min)
]

DEFAULT_WEIGHTS = [0.1875, 0.5, 0.1875, 0.0625, 0.0625]  # как в предыдущем расчёте

def minutes_in_window(start_h: int, end_h: int) -> int:
    # учитывает оконный переход через полночь
    start = start_h
    end = end_h if end_h > start_h else end_h + 24
    return (end - start) * 60

def generate_schedule(limit_per_month: int,
                      days_in_month: int = 31,
                      weights: List[float] = None,
                      tz_out: str = 'UTC') -> Dict:
    """
    Возвращает словарь:
    {
      'daily_requests': int,
      'monthly_used': int,
      'residual_monthly': int,
      'windows': [
         { 'window': (start,end),
           'minutes': X,
           'requests': n,
           'interval_min': y,
           'times': ['HH:MM:SS', ...]  # в tz_out
         }, ...]
      'daily_times_flat': ['HH:MM:SS', ...]  # отсортированный список времен
    }
    """
    if weights is None:
        weights = DEFAULT_WEIGHTS
    assert len(weights) == len(WINDOWS_UTC), "weights length mismatch"

    daily_requests = limit_per_month // days_in_month  # floor -> гарантируем <= лимита
    monthly_used = daily_requests * days_in_month
    residual = limit_per_month - monthly_used

    # распределим запросы по окнам: округлим веса*daily_requests, поправим сумму
    raw = [w * daily_requests for w in weights]
    counts = [int(math.floor(x)) for x in raw]
    # распределяем недостающие (если сумма < daily_requests) добавляя к окнам с наибольшим дробным остатком
    deficit = daily_requests - sum(counts)
    if deficit > 0:
        fracs = [(raw[i] - counts[i], i) for i in range(len(raw))]
        fracs.sort(reverse=True)  # по убыванию дробной части
        for _, idx in fracs[:deficit]:
            counts[idx] += 1

    # Собираем времена (UTC базово), затем конвертируем в tz_out
    tz = ZoneInfo(tz_out) if tz_out != 'UTC' else timezone.utc
    windows_output = []
    daily_times = []

    for (widx, (start_h, end_h)) in enumerate(WINDOWS_UTC):
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
        interval_seconds = (mins * 60) / n  # может быть дробным
        # сдвигаем первый запрос на половину интервала (чтобы не попадать ровно в границы)
        first_offset = interval_seconds / 2.0

        # Для генерации времён возьмём "сегодня" в UTC
        today_utc = datetime.now(timezone.utc).date()
        times_in_window = []
        for k in range(n):
            # compute time in UTC
            offset_sec = first_offset + k * interval_seconds
            base = datetime.combine(today_utc, time(hour=0, minute=0, second=0, tzinfo=timezone.utc))
            # compute the start-of-window moment (UTC)
            start_hour = start_h
            # if window is like (0,7) start_h is 0, fine
            start_dt = base + timedelta(hours=start_hour)
            t_utc = start_dt + timedelta(seconds=offset_sec)
            # normalize in case end_h <= start_h (e.g., window crossing midnight handled by minutes_in_window)
            # convert to desired tz_out
            t_local = t_utc.astimezone(tz)
            times_in_window.append(t_local.strftime('%H:%M:%S'))
            daily_times.append(t_local)

        windows_output.append({
            'window': (start_h, end_h),
            'minutes': mins,
            'requests': n,
            'interval_min': interval_seconds / 60.0,
            'times': times_in_window
        })

    # сортируем и форматируем flat list
    daily_times_sorted = sorted(daily_times)
    daily_times_str = [dt.strftime('%H:%M:%S') for dt in daily_times_sorted]

    return {
        'daily_requests': daily_requests,
        'monthly_used': monthly_used,
        'residual_monthly': residual,
        'windows': windows_output,
        'daily_times_flat': daily_times_str
    }


# Простой синхронный планировщик
def run_scheduler(daily_times: List[str], callback, tz_out: str = 'UTC'):
    """
    daily_times: список строк "HH:MM:SS" в часовом поясе tz_out (повторяется каждый день).
    callback: функция без аргументов, вызываемая в запланированное время.
    tz_out: временная зона строкой, например 'UTC', 'America/New_York', 'Europe/Berlin'.
    Этот цикл будет работать в основном потоке и блокировать его (использует time.sleep).
    """
    tz = ZoneInfo(tz_out) if tz_out != 'UTC' else timezone.utc

    print(f"Scheduler started (timezone={tz_out}). Today times count = {len(daily_times)}")
    while True:
        now = datetime.now(tz)
        # сформируем list of datetimes на ближайшие 24 часа (текущий день и, при необходимости, завтра)
        upcoming = []
        today = now.date()
        for tstr in daily_times:
            hh, mm, ss = map(int, tstr.split(':'))
            dt = datetime.combine(today, time(hh, mm, ss), tz)
            if dt <= now:
                dt = dt + timedelta(days=1)  # уже прошло — запланировать на завтра
            upcoming.append(dt)
        # выберем ближайший
        next_dt = min(upcoming)
        wait_seconds = (next_dt - now).total_seconds()
        # safety floor
        if wait_seconds > 0:
            # печатаем, когда следующий вызов
            print(f"[{datetime.now(tz).isoformat()}] Next call at {next_dt.isoformat()} (wait {int(wait_seconds)} s)")
            time_module.sleep(wait_seconds)
        else:
            # на случай негативного интервала, сразу вызываем
            pass
        try:
            callback()
        except Exception as e:
            print("Callback error:", e)
        # после выполнения цикл повторится и пересчитает ближайшее время


# Пример callback — здесь вы помещаете код запроса курса
def example_callback():
    now = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')
    print(f"Fetching price... ({now})")
    signals.finish_payment.send('PaymentManager', time=0)
    # Здесь ваш код: запрос API, логирование и т.д.
    # Например: requests.get(...)


if __name__ == "__main__":
    # Пример использования: вывести расписание для нескольких лимитов
    # list = [1000, 2000, 3333, 5000]
    # list = [10000]
    # for limit in list:
    #     sched = generate_schedule(limit_per_month=limit, days_in_month=31, tz_out='UTC')
    #     print("=== limit:", limit, "daily:", sched['daily_requests'], "monthly_used:", sched['monthly_used'], "residual:", sched['residual_monthly'])
    #     for w in sched['windows']:
    #         print(f"Window {w['window']}: requests={w['requests']}, interval_min={w['interval_min']}, times_sample={w['times'][:3]}")
    #     print("Total times in day:", len(sched['daily_times_flat']))
    #     print("First 10 times (UTC):", sched['daily_times_flat'][:10])
    #     print()

    # Если хотите запускать таймер прямо сейчас — раскомментируйте следующие строки:
    pick_limit = 10000
    sched = generate_schedule(limit_per_month=pick_limit, days_in_month=31, tz_out='UTC')
    run_scheduler(sched['daily_times_flat'], example_callback, tz_out='UTC')
