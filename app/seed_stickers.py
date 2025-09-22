from app.extensions import db
from app.models import Sticker
from app import create_app

app = create_app()
with app.app_context():
    stickers = [
        {"packageId": 11537, "stickerId": str(i)}
        for i in range(52002734, 52002758)
    ]
    for s in stickers:
        if not Sticker.query.filter_by(
            packageId=str(s["packageId"]),   # 👈 cast เป็น string
            stickerId=str(s["stickerId"])    # 👈 cast เป็น string
        ).first():
            sticker = Sticker(
                packageId=str(s["packageId"]),
                stickerId=str(s["stickerId"]),
                keywords=s.get("keywords", "")
            )
            db.session.add(sticker)

db.session.commit()
print("Seed complete ✅")
