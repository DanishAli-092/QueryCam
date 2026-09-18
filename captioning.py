"""
Stage 3: Captioning (BLIP)
Only run on frames that had at least one detection, to save VRAM/time
on the 4GB budget card.
"""

import torch
from PIL import Image
from transformers import BlipProcessor, BlipForConditionalGeneration
import config


class BlipCaptioner:
    def __init__(self):
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.processor = BlipProcessor.from_pretrained(config.BLIP_MODEL_NAME)
        self.model = BlipForConditionalGeneration.from_pretrained(
            config.BLIP_MODEL_NAME
        ).to(self.device)

    def caption(self, frame_bgr) -> str:
        """
        frame_bgr: numpy array in BGR (as read by OpenCV).
        Returns a natural-language caption string.
        """
        # Convert BGR (OpenCV) -> RGB (PIL) before feeding BLIP
        rgb = frame_bgr[:, :, ::-1]
        image = Image.fromarray(rgb)

        inputs = self.processor(images=image, return_tensors="pt").to(self.device)
        output_ids = self.model.generate(**inputs, max_new_tokens=40)
        caption = self.processor.decode(output_ids[0], skip_special_tokens=True)
        return caption

