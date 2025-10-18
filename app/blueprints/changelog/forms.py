# app/blueprints/changelog/forms.py - ฟอร์มจัดการบันทึกการเปลี่ยนแปลง
from __future__ import annotations

from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField, TextAreaField
from wtforms.fields import URLField
from wtforms.validators import DataRequired, Length, Optional, URL


class ChangeLogForm(FlaskForm):
    title = StringField("หัวข้อ", validators=[DataRequired(), Length(max=255)])
    body = TextAreaField("รายละเอียด", validators=[DataRequired()])
    image_url = URLField("ลิงก์รูปภาพ (URL)", validators=[Optional(), URL(), Length(max=1024)])

    submit = SubmitField("บันทึกการเปลี่ยนแปลง")
