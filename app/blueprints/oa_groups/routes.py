from flask import render_template, request, redirect, url_for, flash
from flask_login import login_required
from . import bp
from app.models import OAGroup
from app.extensions import db
from .forms import GroupForm

@bp.route("/")
@login_required
def index():
    groups = OAGroup.query.order_by(OAGroup.name).all()
    return render_template("oa_groups/index.html", groups=groups)

@bp.route("/add", methods=["GET", "POST"])
@login_required
def add():
    form = GroupForm()
    if form.validate_on_submit():
        new_group = OAGroup(name=form.name.data)
        db.session.add(new_group)
        db.session.commit()
        flash("Group added successfully!", "success")
        return redirect(url_for("oa_groups.index"))
    return render_template("oa_groups/add.html", form=form)

@bp.route("/edit/<int:id>", methods=["GET", "POST"])
@login_required
def edit(id):
    group = OAGroup.query.get_or_404(id)
    form = GroupForm(obj=group)
    if form.validate_on_submit():
        group.name = form.name.data
        db.session.commit()
        flash("Group updated successfully!", "success")
        return redirect(url_for("oa_groups.index"))
    return render_template("oa_groups/edit.html", group=group, form=form)

@bp.route("/delete/<int:id>", methods=["POST"])
@login_required
def delete(id):
    group = OAGroup.query.get_or_404(id)
    db.session.delete(group)
    db.session.commit()
    flash("Group deleted successfully!", "danger")
    return redirect(url_for("oa_groups.index"))