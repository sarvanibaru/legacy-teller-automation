"""
Mock legacy bank teller app.

Deliberately ugly HTML (nested tables, no test IDs) to simulate a legacy
enterprise UI, but with correct <label> associations so the accessibility
tree remains meaningful -- that contrast is the point of this app.
"""
import time

from functools import wraps

from flask import Flask, render_template, request, redirect, session, url_for

from data import VALID_USERNAME, VALID_PASSWORD, MEMBERS

app = Flask(__name__)
app.secret_key = "dev-only-secret-not-for-production"

SESSION_TTL_SECONDS = 120  # short on purpose, so you can actually test expiry


def login_required(view_func):
    @wraps(view_func)
    def wrapped(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login"))

        login_time = session.get("login_time", 0)
        force_expired = request.args.get("inject") == "session_expired"
        if force_expired or (time.time() - login_time) > SESSION_TTL_SECONDS:
            session.clear()
            return redirect(url_for("login", expired="1"))

        return view_func(*args, **kwargs)
    return wrapped


@app.route("/", methods=["GET"])
def root():
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.args.get("expired") == "1":
        error = "Your session has expired. Please log in again."
    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        if username == VALID_USERNAME and password == VALID_PASSWORD:
            session["logged_in"] = True
            session["login_time"] = time.time()
            return redirect(url_for("search"))
        error = "Invalid username or password."
    return render_template("login.html", error=error)


@app.route("/search", methods=["GET"])
@login_required
def search():
    queried_id = request.args.get("member_id")
    not_found = False
    if queried_id is not None:
        if queried_id in MEMBERS:
            return redirect(url_for("member_detail", member_id=queried_id))
        not_found = True
    return render_template("search.html", not_found=not_found, queried_id=queried_id)


@app.route("/member/<member_id>", methods=["GET"])
@login_required
def member_detail(member_id):
    inject = request.args.get("inject")

    if inject == "permission_denied":
        return render_template("permission_denied.html", member_id=member_id), 403

    if inject == "error":
        raise RuntimeError("Simulated unexpected application error")

    if inject == "slow":
        time.sleep(4)

    member = MEMBERS.get(member_id)
    if member is None:
        return redirect(url_for("search", member_id=member_id))
    return render_template("member_detail.html", member=member)


@app.route("/member/<member_id>/close", methods=["GET"])
@login_required
def close_account(member_id):
    # Intentionally a dead end: this represents an irreversible, blocked
    # action. The policy layer should refuse to click this link at all --
    # this route existing is what proves the block is meaningful rather
    # than the button simply not being there.
    return render_template("permission_denied.html", member_id=member_id), 403


@app.route("/member/<member_id>/sub-account", methods=["GET"])
@login_required
def sub_account_form(member_id):
    member = MEMBERS.get(member_id)
    if member is None:
        return redirect(url_for("search"))
    inject = request.args.get("inject", "")
    return render_template("sub_account_form.html", member=member, inject=inject)


@app.route("/member/<member_id>/sub-account/confirm", methods=["POST"])
@login_required
def sub_account_confirm(member_id):
    member = MEMBERS.get(member_id)
    if member is None:
        return redirect(url_for("search"))

    account_type = request.form.get("account_type")
    initial_deposit = request.form.get("initial_deposit", "")

    try:
        deposit_value = float(initial_deposit)
        if deposit_value <= 0:
            raise ValueError("must be positive")
    except ValueError:
        return render_template(
            "sub_account_form.html",
            member=member,
            validation_error=f'"{initial_deposit}" is not a valid deposit amount.',
        )

    inject_dialog = request.args.get("inject") == "dialog"
    return render_template(
        "sub_account_confirm.html",
        member=member,
        account_type=account_type,
        initial_deposit=initial_deposit,
        inject_dialog=inject_dialog,
    )


@app.route("/member/<member_id>/sub-account/submit", methods=["POST"])
@login_required
def sub_account_submit(member_id):
    member = MEMBERS.get(member_id)
    if member is None:
        return redirect(url_for("search"))
    account_type = request.form.get("account_type")
    initial_deposit = request.form.get("initial_deposit")
    reference_number = f"SA-{member_id}-{account_type[:3].upper()}"
    return render_template(
        "sub_account_success.html",
        member=member,
        account_type=account_type,
        initial_deposit=initial_deposit,
        reference_number=reference_number,
    )


from werkzeug.exceptions import HTTPException


@app.errorhandler(Exception)
def handle_uncaught_error(e):
    if isinstance(e, HTTPException):
        # Let Flask/Werkzeug handle real HTTP errors (404, etc.) normally --
        # this handler is only for genuine unexpected application crashes.
        return e
    app.logger.exception("Unhandled error while serving request")
    return render_template("app_error.html"), 500


if __name__ == "__main__":
    # debug=False so our own error handler renders instead of Flask's
    # interactive debugger, which would otherwise leak internals to the page.
    app.run(host="0.0.0.0", port=5001, debug=False)