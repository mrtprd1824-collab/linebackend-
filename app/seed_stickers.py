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
        if not Sticker.query.filter_by(packageId=s["packageId"], stickerId=s["stickerId"]).first():
            db.session.add(Sticker(packageId=s["packageId"], stickerId=s["stickerId"]))
    db.session.commit()
    print("Seed complete")
