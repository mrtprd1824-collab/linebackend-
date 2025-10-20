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

    attachments = db.relationship(
        "ChangeLogFile",
        back_populates="changelog",
        cascade="all, delete-orphan",
        order_by="ChangeLogFile.id",
    )

    def __repr__(self) -> str:
        return f"<ChangeLog {self.id}: {self.title[:30]!r}>"


class ChangeLogFile(db.Model):
    __tablename__ = "change_log_files"

    id = db.Column(db.Integer, primary_key=True)
    change_log_id = db.Column(db.Integer, db.ForeignKey("change_logs.id", ondelete="CASCADE"), nullable=False, index=True)
    file_name = db.Column(db.String(255), nullable=False)
    file_url = db.Column(db.String(1024), nullable=False)
    content_type = db.Column(db.String(255), nullable=True)
    file_size = db.Column(db.Integer, nullable=True)
    uploaded_at = db.Column(db.DateTime(timezone=True), server_default=func.now(), nullable=False)

    changelog = db.relationship("ChangeLog", back_populates="attachments")

    def __repr__(self) -> str:
        return f"<ChangeLogFile {self.file_name!r}>"
