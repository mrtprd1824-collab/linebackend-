# app/blueprints/oa_groups/forms.py

from flask_wtf import FlaskForm
from wtforms import StringField, SubmitField
from wtforms.validators import DataRequired

class GroupForm(FlaskForm):
    """Form for adding or editing an OA Group."""
    name = StringField('Group Name', validators=[DataRequired(message="Group name is required.")])
    submit = SubmitField('Save')