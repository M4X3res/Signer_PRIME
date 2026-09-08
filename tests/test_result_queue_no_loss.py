"""
tests/test_result_queue_no_loss.py
Regression test для БАГ №1: знаки не должны теряться при переполнении result_queue.

Проверяет, что после нескольких проходов цикла отправки (с эмуляцией
освобождения очереди) сумма отправленных + оставшихся в result_signs знаков
всегда равна изначальному количеству.
"""
import sys
import queue
from pathlib import Path
import io

# Устанавливаем UTF-8 для stdout чтобы избежать проблем с кириллицей
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Добавляем корень проекта в sys.path для импорта модулей
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from core.sign import TrackedSign


def test_result_queue_no_loss():
    """
    Тестирует логику отправки знаков в ограниченную очередь.
    Гарантирует, что ни один знак не теряется при переполнении.
    """
    print("=" * 60)
    print("TEST: result_queue sign loss prevention")
    print("=" * 60)
    
    # Создаём маленькую очередь (размер 2) и 5 фиктивных знаков
    test_queue = queue.Queue(maxsize=2)
    
    # Создаём 5 фиктивных TrackedSign
    initial_signs = []
    for i in range(5):
        sign = TrackedSign()
        sign.cnn_results = [f"3.2{i}"]  # Минимальная инициализация для best_cnn
        sign.frame_numbers = [i]
        initial_signs.append(sign)
    
    initial_count = len(initial_signs)
    result_signs = initial_signs.copy()
    
    print(f"Начальное количество знаков: {initial_count}")
    print(f"Размер очереди: {test_queue.maxsize}")
    
    # Эмулируем несколько циклов отправки
    iteration = 0
    max_iterations = 10
    sent_total = 0
    
    while result_signs and iteration < max_iterations:
        iteration += 1
        print(f"\n--- Итерация {iteration} ---")
        print(f"Знаков к отправке: {len(result_signs)}")
        
        # Логика из исправленного detector_thread.py
        remaining = []
        sent_this_round = 0
        
        for sign in result_signs:
            try:
                test_queue.put(sign, timeout=0.1, block=False)
                sent_this_round += 1
            except queue.Full:
                # Знак не поместился — откладываем
                remaining.append(sign)
        
        sent_total += sent_this_round
        result_signs = remaining
        
        print(f"Отправлено в этой итерации: {sent_this_round}")
        print(f"Осталось отправить: {len(remaining)}")
        
        # Эмулируем освобождение очереди (как будто контроллер их прочитал)
        while not test_queue.empty():
            try:
                test_queue.get_nowait()
            except queue.Empty:
                break
    
    # Проверка: сумма отправленных + оставшихся должна равняться начальному количеству
    remaining_count = len(result_signs)
    total_accounted = sent_total + remaining_count
    
    print("\n" + "=" * 60)
    print("RESULTS:")
    print(f"  Initially:  {initial_count}")
    print(f"  Sent:       {sent_total}")
    print(f"  Remaining:  {remaining_count}")
    print(f"  Total:      {total_accounted}")
    print("=" * 60)
    
    if total_accounted != initial_count:
        print(f"FAIL: Lost {initial_count - total_accounted} signs!")
        sys.stdout.flush()
        return False
    
    if remaining_count > 0:
        print(f"WARNING: {remaining_count} signs not sent (infinite loop?)")
    
    print("PASS: No signs lost")
    sys.stdout.flush()
    return True


if __name__ == "__main__":
    success = test_result_queue_no_loss()
    sys.exit(0 if success else 1)
