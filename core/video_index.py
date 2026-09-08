"""
core/video_index.py

Task C: Корректная функция для преобразования абсолютного номера кадра
в (video_idx, frame_in_video) с использованием РЕАЛЬНЫХ длин видеофайлов,
а не константы config.FRAMES_PER_VIDEO.
"""
import cv2
from configs import config


def resolve_video_and_frame(abs_frame: int) -> tuple[int, int]:
    """
    Корректно определяет (video_idx, frame_in_video) по абсолютному номеру кадра,
    используя РЕАЛЬНЫЕ длины видеофайлов (config.VIDEO_FRAME_COUNTS), а не
    config.FRAMES_PER_VIDEO.
    
    Args:
        abs_frame: Абсолютный номер кадра (от начала всех видео)
    
    Returns:
        tuple[video_idx, frame_in_video]:
            - video_idx: индекс видео в config.VIDEOS
            - frame_in_video: номер кадра внутри этого видео (0-based)
    
    Raises:
        ValueError: если abs_frame выходит за пределы всех видео
    """
    # Заполняем кэш реальных длин видео, если пусто или неполно
    _ensure_video_frame_counts()
    
    if not config.VIDEO_FRAME_COUNTS:
        raise ValueError("Не удалось определить длины видеофайлов")
    
    # Проходим по кумулятивным суммам, находим видео, в которое попадает abs_frame
    cumulative = 0
    for video_idx, frame_count in enumerate(config.VIDEO_FRAME_COUNTS):
        if abs_frame < cumulative + frame_count:
            frame_in_video = abs_frame - cumulative
            return video_idx, frame_in_video
        cumulative += frame_count
    
    # abs_frame выходит за пределы всех видео
    raise ValueError(
        f"abs_frame={abs_frame} выходит за пределы всех видео "
        f"(всего {cumulative} кадров в {len(config.VIDEO_FRAME_COUNTS)} видео)"
    )


def _ensure_video_frame_counts():
    """
    Заполняет config.VIDEO_FRAME_COUNTS реальными длинами видеофайлов,
    если кэш пуст или короче списка config.VIDEOS.
    
    Использует cv2.VideoCapture для чтения FRAME_COUNT каждого видео.
    """
    # Инициализируем список, если его ещё нет
    if not hasattr(config, 'VIDEO_FRAME_COUNTS'):
        config.VIDEO_FRAME_COUNTS = []
    
    # Досчитываем недостающие длины
    num_cached = len(config.VIDEO_FRAME_COUNTS)
    num_videos = len(config.VIDEOS)
    
    if num_cached >= num_videos:
        return  # Кэш уже полный
    
    print(f"[video_index] Определяем длины видеофайлов ({num_cached}/{num_videos} закэшировано)...")
    
    for i in range(num_cached, num_videos):
        video_path = config.VIDEOS[i]
        try:
            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                print(f"[video_index] ОШИБКА: не удалось открыть {video_path}, используем дефолт")
                frame_count = config.FRAMES_PER_VIDEO  # Fallback к константе
            else:
                frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                if frame_count <= 0:
                    print(f"[video_index] ВНИМАНИЕ: {video_path} вернул frame_count={frame_count}, используем дефолт")
                    frame_count = config.FRAMES_PER_VIDEO
                else:
                    print(f"[video_index] {video_path}: {frame_count} кадров")
            cap.release()
        except Exception as e:
            print(f"[video_index] ОШИБКА при чтении {video_path}: {e}, используем дефолт")
            frame_count = config.FRAMES_PER_VIDEO
        
        config.VIDEO_FRAME_COUNTS.append(frame_count)
    
    print(f"[video_index] Готово: {len(config.VIDEO_FRAME_COUNTS)} видео в кэше")
