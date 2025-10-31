from flask import render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required
from sqlalchemy import or_
from . import bp
from app.models import QuickReply, db, LineAccount
from .forms import QuickReplyForm


def _wants_json_response() -> bool:
    """Check if the caller prefers a JSON payload (used by fetch requests)."""
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return True
    best = request.accept_mimetypes.best_match(["application/json", "text/html"])
    return best == "application/json"


def _quick_reply_to_dict(reply: QuickReply) -> dict:
    """Serialize a quick reply model into a JSON-friendly payload."""
    return {
        "id": reply.id,
        "shortcut": reply.shortcut,
        "message": reply.message,
        "line_account_id": reply.line_account_id,
        "line_account_name": reply.line_account.name if reply.line_account else "Global",
        "is_global": reply.line_account_id is None,
    }


@bp.route("/")
@login_required
def index():
    selected_oa_id = request.args.get("oa_filter", type=int)

    query = QuickReply.query
    if selected_oa_id:
        query = query.filter(
            or_(
                QuickReply.line_account_id == selected_oa_id,
                QuickReply.line_account_id == None,  # noqa: E711
            )
        )

    replies = query.order_by(QuickReply.line_account_id, QuickReply.shortcut).all()

    add_form = QuickReplyForm()
    edit_form = QuickReplyForm()
    all_accounts = LineAccount.query.order_by(LineAccount.name).all()
    account_options = [{"id": account.id, "name": account.name} for account in all_accounts]

    return render_template(
        "quick_replies/index.html",
        replies=replies,
        add_form=add_form,
        edit_form=edit_form,
        all_accounts=all_accounts,
        selected_oa_id=selected_oa_id,
        account_options=account_options,
    )


@bp.route("/data")
@login_required
def data():
    selected_oa_id = request.args.get("oa_id", type=int)
    only_global = request.args.get("only_global", default=0, type=int)

    query = QuickReply.query
    if only_global:
        query = query.filter(QuickReply.line_account_id == None)  # noqa: E711
    elif selected_oa_id:
        query = query.filter(
            or_(
                QuickReply.line_account_id == selected_oa_id,
                QuickReply.line_account_id == None,  # noqa: E711
            )
        )

    replies = query.order_by(QuickReply.line_account_id, QuickReply.shortcut).all()
    payload = [_quick_reply_to_dict(reply) for reply in replies]
    return jsonify({"replies": payload})


@bp.route("/add", methods=["POST"])
@login_required
def add():
    form = QuickReplyForm()
    if form.validate_on_submit():
        selected_account = form.line_account.data
        new_reply = QuickReply(
            shortcut=form.shortcut.data,
            message=form.message.data,
            line_account_id=selected_account.id if selected_account else None,
        )
        db.session.add(new_reply)
        db.session.commit()
        flash("Quick reply added successfully!", "success")
        if _wants_json_response():
            return (
                jsonify(
                    {
                        "success": True,
                        "message": "Quick reply added successfully!",
                        "reply": _quick_reply_to_dict(new_reply),
                    }
                ),
                201,
            )
    else:
        flash("Error creating quick reply.", "danger")
        if _wants_json_response():
            return jsonify({"success": False, "errors": form.errors}), 400
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
        if _wants_json_response():
            return jsonify(
                {
                    "success": True,
                    "message": "Quick reply updated successfully!",
                    "reply": _quick_reply_to_dict(reply),
                }
            )
    else:
        flash("Error updating quick reply.", "danger")
        if _wants_json_response():
            return jsonify({"success": False, "errors": form.errors}), 400
    return redirect(url_for("quick_replies.index"))


@bp.route("/delete/<int:id>", methods=["POST"])
@login_required
def delete(id):
    reply = QuickReply.query.get_or_404(id)
    db.session.delete(reply)
    db.session.commit()
    flash("Quick reply deleted successfully!", "danger")
    if _wants_json_response():
        return jsonify({"success": True, "message": "Quick reply deleted successfully!", "id": id})
    return redirect(url_for("quick_replies.index"))
