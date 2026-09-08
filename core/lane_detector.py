import cv2
import logging
import numpy as np

# BLOCK P.2: Прямой импорт из sign_models вместо легаси-шима sign_config
from configs.sign_models import model_lane_detect, model_lane_segment

logger = logging.getLogger(__name__)


class LaneDetector:
    def __init__(self, settings=None):
        """
        Инициализирует LaneDetector.
        
        Args:
            settings: AppSettings или None (используются defaults)
        """
        # BLOCK P.1: Применяем пороги уверенности из настроек
        if settings is None:
            from configs.settings import get_app_settings
            settings = get_app_settings()
        
        self.CONF_LANE_DETECT = settings.lane_conf_detect
        self.CONF_LANE_SEGMENT = settings.lane_conf_segment
        
        self.direction_sign = ["front", "back", "left", "right"]
        self.direction_type = {
            "reversal": "6.3.1",
            "left": "4.1.3",
            "right": "4.1.2"
        }
        
        logger.info(f"[LaneDetector] Инициализирован: "
                   f"CONF_DETECT={self.CONF_LANE_DETECT:.2f}, "
                   f"CONF_SEGMENT={self.CONF_LANE_SEGMENT:.2f}")

    def find_signs(self, img):
        boxes, class_numbers, masks = self.__process_sign(img)
        result_type_signs = []
        if masks is not None:
            for mask in masks:
                mask_raw = self.__mask_conversion(mask, img)
                for class_number, box in zip(class_numbers, boxes):
                    x, y, x1, y1 = box
                    w = box[2] - box[0]
                    h = box[3] - box[1]
                    #if self.direction_sign[class_number] == "front":
                    #    cv2.rectangle(img, [x, y, w, h], (255, 255, 0), 1)
                    #if self.direction_sign[class_number] == "back":
                    #    cv2.rectangle(img, [x, y, w, h], (168, 50, 50), 1)
                    #if self.direction_sign[class_number] == "left":
                    #    cv2.rectangle(img, [x, y, w, h], (107, 168, 50), 1)
                    #if self.direction_sign[class_number] == "right":
                    #    cv2.rectangle(img, [x, y, w, h], (0, 0, 0), 1)
                    #cv2.imshow("image", img)
                    #cv2.waitKey(100)
                    mask_arrow = mask_raw[y:y1, x:x1]
                    true_class_number = self.__find_direction(w, h, mask_arrow, class_number)
                    if self.direction_sign[true_class_number] == "back":
                        if self.__check_for_reversal(box, h, mask_raw):
                            #6.3.1 turn signreversal
                            result_type_signs.append("6.3.1")
                    elif true_class_number > 1:
                        result_type_signs.append(self.direction_type[self.direction_sign[true_class_number]])
        # BLOCK P.3: Заменить print на logging
        logger.debug(f"[LaneDetector] Результат: {'-'.join(result_type_signs)}")
        return '-'.join(result_type_signs)

    def __mask_conversion(self, mask, img):
        mask_raw = mask.cpu().data.numpy().transpose(1, 2, 0).tolist()
        mask_raw = np.asarray(mask_raw)
        shape_img = (img.shape[1], img.shape[0])
        mask_raw = cv2.resize(mask_raw, shape_img)
        return mask_raw
    def __check_for_reversal(self, box, h, mask):
        number_center_line_box = box[1] + int(h / 2)
        center_line = mask[number_center_line_box].tolist()
        is_white_line = False
        is_gap = False
        for item in center_line:
            if item == 1.0:
                is_white_line = True
            if is_white_line and item == 0.0:
                is_gap = True
            if is_gap and item == 1.0:
                return True

    def __process_sign(self, img):
        # BLOCK P.1: Используем настраиваемые пороги вместо хардкода
        detect = model_lane_detect.predict(img, conf=self.CONF_LANE_DETECT)
        boxes = detect[0].boxes.xyxy.cpu().numpy().astype(int)
        class_names = detect[0].boxes.cls.cpu().numpy().astype(int)

        segment = model_lane_segment.predict(img, conf=self.CONF_LANE_SEGMENT)
        masks = segment[0].masks

        return boxes, class_names, masks

    def __find_direction(self, w, h, mask, class_number):
        size_mask = w * h
        mask = mask.tolist()
        overlap = round(len([item for item in sum(mask, []) if item != 0.0]) / size_mask * 100, 0)
        return class_number if int(overlap > 25) else -1
