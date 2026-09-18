from ultralytics import YOLO

# 1. Apna fine-tuned model load karein
model = YOLO('models/best.pt')

# 2. Inference run karein 
results = model.predict(
    source='data/test-video-2.mp4',  # Yahan apni test video ka path dein
    conf=0.60,                    # Sirf 60% se zyada confidence wali detections allow karein
    show=True,                    # Aap ki screen par live video play hogi with boxes
    save=True                     # Bounding boxes ke sath result video save bhi hogi
)