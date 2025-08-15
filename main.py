import schedulertimer
from queue import Empty
import signals

# ---- Пример использования ----
# if __name__ == "__main__":
#     # Пример: генерируем расписание для лимита 2000/мес, tz UTC,
#     # затем запускаем планировщик в отдельном потоке.
#     LIMIT = 10000
#     TZ = 'UTC'  # можно 'America/New_York' или 'Europe/Berlin'

#     sched = schedulertimer.generate_schedule(limit_per_month=LIMIT, days_in_month=31, tz_out=TZ)
#     times = sched['daily_times_flat']
#     window_indices = sched['daily_times_window_index']

#     print("Daily requests:", sched['daily_requests'], "monthly_used:", sched['monthly_used'], "residual:", sched['residual_monthly'])
#     print("Times today sample (first 10):", times[:10])

#     # Пример callback: печатаем сигнал кратко
#     def my_callback(signal):
#         print("[callback] Signal received:", signal['fired_time'], "since_last:", signal['since_last_seconds'])

#     scheduler = schedulertimer.TimerScheduler(daily_times=times, daily_window_indices=window_indices, callback=my_callback, tz_out=TZ, name="MyScheduler")
#     scheduler.start(daemon=True)

#     print("Scheduler started in background. Press Ctrl+C to stop or wait to receive signals.")
#     try:
#         # Демонстрация получения сигналов из очереди в основном потоке:
#         while True:
#             try:
#                 sig = scheduler.signal_queue.get(timeout=5.0)  # ждём сигнал 5 сек
#                 print("[main] Got signal from queue:", sig['fired_time'], "since_last:", sig['since_last_seconds'])
#                 # Здесь вы можете обработать сигнал в основном потоке: отправить запрос, логировать и т.д.
#             except Empty:
#                 # каждый 5 секунд проверяем, что поток всё ещё жив
#                 if not scheduler.is_running():
#                     break
#     except KeyboardInterrupt:
#         print("Stopping scheduler...")
#     finally:
#         scheduler.stop(wait=True)
#         print("Scheduler stopped.")




def on_task_done(sender, last_scheduler):
    print(sender, last_scheduler)



signals.task_done.connect(on_task_done, sender='MediaWorker')



import threading
import time
import asyncio
from blinker import signal

task_done = signal('task_done')

# Получаем основной asyncio loop
loop = asyncio.get_event_loop()

def handle_in_main_loop(sender, kwargs):
    # это будет выполнено в event loop
    print(f"[asyncio main loop] got from {sender}: {kwargs}")

@task_done.connect
def _on_task_done(sender, **kwargs):
    # этот код выполняется в потоке планировщика — безопасно запланируем обработку в loop
    loop.call_soon_threadsafe(handle_in_main_loop, sender, kwargs)

def scheduler_loop():
    i = 0
    while i < 3:
        time.sleep(1)
        i += 1
        task_done.send('scheduler', n=i)
        threading.Thread(target=scheduler_loop, daemon=True).start()

async def main():
    # даём время событиям прийти
    await asyncio.sleep(4)

asyncio.run(main())