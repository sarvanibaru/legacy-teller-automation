"""
The minimal, real operator console. Deliberately bare (per the brief's
scope note: "a minimal but real handoff... mock the operator UI if
needed") -- what matters is that it's a genuine Flask app sharing the
same EscalationManager/SessionController in memory as the automation
thread, so clicking a button here actually wakes up a blocked thread
elsewhere in the same process, not a simulation of doing so.

Two different screens depending on InterventionRequest.kind:
  - "approval": shows the proposed action, offers Approve / Reject.
  - "takeover": tells the human to go operate the live browser window
    directly, then click Resume once they're done.
"""
from __future__ import annotations

import threading

from flask import Flask, redirect, render_template_string, request, send_file
from werkzeug.serving import make_server

PAGE_TEMPLATE = """
<!doctype html>
<html>
<head>
  <title>Operator Console</title>
  <meta http-equiv="refresh" content="3">
  <style>
    body { font-family: -apple-system, sans-serif; max-width: 700px; margin: 40px auto; padding: 0 20px; }
    .reason { background: #fff3cd; padding: 12px; border-radius: 6px; }
    .tree { background: #f0f0f0; padding: 12px; border-radius: 6px; white-space: pre-wrap; font-family: monospace; font-size: 13px; max-height: 300px; overflow-y: auto; }
    .proposed { background: #e7f3ff; padding: 12px; border-radius: 6px; }
    button { padding: 10px 20px; font-size: 15px; margin-right: 10px; border-radius: 6px; border: none; cursor: pointer; }
    .approve { background: #28a745; color: white; }
    .reject { background: #dc3545; color: white; }
    .resume { background: #007bff; color: white; }
    img { max-width: 100%; border: 1px solid #ccc; margin-top: 10px; }
  </style>
</head>
<body>
  <h2>Operator Console</h2>
  {% if request_obj is none %}
    <p>No active intervention. Waiting... (this page refreshes automatically)</p>
  {% else %}
    <p class="reason"><b>Reason:</b> {{ request_obj.reason }}</p>
    <p><b>Kind:</b> {{ request_obj.kind }} &nbsp; <b>Capability:</b> {{ request_obj.capability_id or "n/a" }} &nbsp; <b>Step:</b> {{ request_obj.step_id or "n/a" }}</p>
    <p><b>URL:</b> {{ request_obj.url }}</p>

    {% if request_obj.kind == "approval" %}
      <div class="proposed"><b>Proposed action:</b><br>{{ request_obj.proposed_action }}</div>
      <form method="POST" action="/resolve">
        <input type="hidden" name="approved" value="true">
        <input type="text" name="note" placeholder="optional note">
        <br><br>
        <button class="approve" type="submit">Approve</button>
      </form>
      <form method="POST" action="/resolve">
        <input type="hidden" name="approved" value="false">
        <input type="text" name="note" placeholder="reason for rejection">
        <br><br>
        <button class="reject" type="submit">Reject</button>
      </form>
    {% else %}
      <p><b>The automation is paused.</b> Go operate the live browser window directly to fix the situation, then click Resume.</p>
      <form method="POST" action="/resolve">
        <input type="hidden" name="approved" value="true">
        <input type="text" name="note" placeholder="what did you do?">
        <br><br>
        <button class="resume" type="submit">Resume</button>
      </form>
    {% endif %}

    {% if request_obj.screenshot_path %}
      <img src="/screenshot">
    {% endif %}
    <p><b>Accessibility tree:</b></p>
    <div class="tree">{{ request_obj.accessibility_tree }}</div>
  {% endif %}
</body>
</html>
"""


def create_operator_app(escalation) -> Flask:
    app = Flask(__name__)

    @app.route("/")
    def index():
        return render_template_string(PAGE_TEMPLATE, request_obj=escalation.active_request)

    @app.route("/resolve", methods=["POST"])
    def resolve():
        approved = request.form.get("approved") == "true"
        note = request.form.get("note", "")
        escalation.session.resolve(approved=approved, note=note)
        return redirect("/")

    @app.route("/screenshot")
    def screenshot():
        req = escalation.active_request
        if req is None or req.screenshot_path is None:
            return "", 404
        return send_file(req.screenshot_path)

    return app


def run_operator_app_in_background(escalation, port: int = 5050):
    """Starts the operator app in a background thread within this same
    process, so it shares the EscalationManager by reference. Returns
    the werkzeug server -- call server.shutdown() when done."""
    app = create_operator_app(escalation)
    server = make_server("localhost", port, app)
    thread = threading.Thread(target=server.serve_forever)
    thread.daemon = True
    thread.start()
    return server