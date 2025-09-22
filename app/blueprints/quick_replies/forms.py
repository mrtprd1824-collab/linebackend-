# app/blueprints/quick_replies/forms.py

from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, SubmitField
from wtforms.validators import DataRequired
from wtforms_sqlalchemy.fields import QuerySelectField
from app.models import LineAccount

def get_line_accounts():
    return LineAccount.query.all()

class QuickReplyForm(FlaskForm):
    shortcut = StringField('Shortcut', validators=[DataRequired()])
    message = TextAreaField('Message', validators=[DataRequired()])
    
    # --- [เพิ่ม] Field สำหรับเลือก OA ---
    # allow_blank=True จะทำให้มีตัวเลือก "ว่าง" ซึ่งเราจะใช้แทน "Global"
    line_account = QuerySelectField(
        'Specific to OA (Optional)',
        query_factory=get_line_accounts,
        get_label='name',
        allow_blank=True,
        blank_text='-- Global --'
    )
    submit = SubmitField('Save')