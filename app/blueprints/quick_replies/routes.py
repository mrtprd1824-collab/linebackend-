from flask import render_template, request, redirect, url_for, flash
from flask_login import login_required
from sqlalchemy import or_
from . import bp
from app.models import QuickReply, db, LineAccount
from .forms import QuickReplyForm

@bp.route("/")
@login_required
def index():
    selected_oa_id = request.args.get('oa_filter', type=int)

    query = QuickReply.query
    if selected_oa_id:
        query = query.filter(
            or_(
                QuickReply.line_account_id == selected_oa_id,
                QuickReply.line_account_id == None
            )
        )
    
    replies = query.order_by(QuickReply.line_account_id, QuickReply.shortcut).all()

    add_form = QuickReplyForm()
    edit_form = QuickReplyForm()
    # [แก้ไข] เปลี่ยนชื่อตัวแปรตรงนี้ให้ถูกต้อง
    all_accounts = LineAccount.query.order_by(LineAccount.name).all()

    return render_template(
        "quick_replies/index.html", 
        replies=replies, 
        add_form=add_form, 
        edit_form=edit_form,
        all_accounts=all_accounts, # <--- ตอนนี้มันจะหาเจอแล้ว
        selected_oa_id=selected_oa_id
    )

@bp.route("/add", methods=["POST"])
@login_required
def add():
    form = QuickReplyForm()
    if form.validate_on_submit():
        selected_account = form.line_account.data
        new_reply = QuickReply(
            shortcut=form.shortcut.data,
            message=form.message.data,
            line_account_id=selected_account.id if selected_account else None
        )
        db.session.add(new_reply)
        db.session.commit()
        flash("Quick reply added successfully!", "success")
    else:
        flash("Error creating quick reply.", "danger")
    return redirect(url_for("quick_replies.index"))

@bp.route("/edit/<int:id>", methods=["POST"])
@login_required
def edit(id):
    reply = QuickReply.query.get_or_404(id)
    form = QuickReplyForm()
    if form.validate_on_submit():
        reply.shortcut = form.shortcut.data
        reply.message = form.message.data
        selected_account = form.line_account.data
        reply.line_account_id = selected_account.id if selected_account else None
        db.session.commit()
        flash("Quick reply updated successfully!", "success")
    else:
        flash("Error updating quick reply.", "danger")
    return redirect(url_for("quick_replies.index"))

@bp.route("/delete/<int:id>", methods=["POST"])
@login_required
def delete(id):
    reply = QuickReply.query.get_or_404(id)
    db.session.delete(reply)
    db.session.commit()
    flash("Quick reply deleted successfully!", "danger")
    return redirect(url_for("quick_replies.index"))