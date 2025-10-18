# app/models/changelog.py - โมเดลจัดเก็บบันทึกการเปลี่ยนแปลงระบบ
from __future__ import annotations

from sqlalchemy import Index, func

from ..extensions import db


class ChangeLog(db.Model):
    __tablename__ = "change_logs"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    body = db.Column(db.Text, nullable=False)
    image_url = db.Column(db.String(1024), nullable=True)
    created_by_admin_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    created_at = db.Column(db.DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    updated_at = db.Column(db.DateTime(timezone=True), onupdate=func.now())

    __table_args__ = (
        Index("ix_change_logs_created_at", created_at.desc()),
    )

    def __repr__(self) -> str:
        return f"<ChangeLog {self.id}: {self.title[:30]!r}>"
