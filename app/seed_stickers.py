from app import create_app
from app.extensions import db
from app.models import Sticker

app = create_app()

stickers = [
    {"packageId": "11537", "stickerId": "52002734"},
    {"packageId": "11537", "stickerId": "52002735"},
    {"packageId": "11537", "stickerId": "52002736"},
    {"packageId": "11537", "stickerId": "52002737"},
    {"packageId": "11537", "stickerId": "52002738"},
    {"packageId": "11537", "stickerId": "52002739"},
    {"packageId": "11537", "stickerId": "52002740"},
    {"packageId": "11537", "stickerId": "52002741"},
    {"packageId": "11537", "stickerId": "52002742"},
    {"packageId": "11537", "stickerId": "52002743"},
    {"packageId": "11537", "stickerId": "52002744"},
    {"packageId": "11537", "stickerId": "52002745"},
]

with app.app_context():
    for s in stickers:
        # ตรวจสอบว่ามีอยู่แล้วหรือยัง
        exists = Sticker.query.filter_by(
            packageId=str(s["packageId"]),
            stickerId=str(s["stickerId"])
        ).first()
        if not exists:
            sticker = Sticker(
                packageId=str(s["packageId"]),
                stickerId=str(s["stickerId"])
            )
            db.session.add(sticker)

    db.session.commit()
    print("✅ Seed complete")
