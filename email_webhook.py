"""
channels/email_webhook.py — inbound email webhook (cookbook §06).

Cookbook spec:
  Route: POST /support/email-webhook
  customer_id = sender email address (consistent cross-channel identity)
  Fields: data["from"], data["text"], data["message_id"]

Compatible with SendGrid, Postmark, and similar inbound parse services.
"""

import os
import sys
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from flask import Flask, request, jsonify

from support.respond import handle_ticket

flask_app = Flask(__name__)


# ── Cookbook route (§06 exact) ─────────────────────────────────────────────

@flask_app.route("/support/email-webhook", methods=["POST"])
def handle_inbound_email():
    """
    Compatible with SendGrid, Postmark, and similar inbound email services.
    Uses the customer's email address as customer_id for consistent cross-
    channel memory — the same email they used to sign up.
    """
    data = request.get_json(silent=True) or request.form.to_dict()

    customer_id  = (data.get("from") or "").lower().strip()
    customer_msg = (data.get("text") or "").strip()
    ticket_id    = data.get("message_id") or str(uuid.uuid4())

    # Handle "Name <email@example.com>" format
    if "<" in customer_id and ">" in customer_id:
        customer_id = customer_id.split("<")[1].split(">")[0].strip()

    if not customer_id or not customer_msg:
        return jsonify({"status": "ignored", "reason": "missing_from_or_text"}), 200

    # Prepend subject if present — helps intent classification
    subject = data.get("subject") or data.get("Subject") or ""
    if subject:
        customer_msg = f"Subject: {subject}\n\n{customer_msg}"

    reply = handle_ticket(customer_id, customer_msg, ticket_id)
    return jsonify({"reply": reply, "ticket_id": ticket_id})


# ── SendGrid multipart variant ─────────────────────────────────────────────

@flask_app.route("/support/email-webhook/sendgrid", methods=["POST"])
def handle_sendgrid():
    """SendGrid Inbound Parse posts multipart/form-data — same logic, different field names."""
    customer_id  = (request.form.get("from") or "").lower().strip()
    customer_msg = (request.form.get("text") or "").strip()
    subject      = request.form.get("subject") or ""
    ticket_id    = f"email-{request.form.get('message-id', str(uuid.uuid4()))}"

    if "<" in customer_id and ">" in customer_id:
        customer_id = customer_id.split("<")[1].split(">")[0].strip()

    if subject:
        customer_msg = f"Subject: {subject}\n\n{customer_msg}"

    reply = handle_ticket(customer_id, customer_msg, ticket_id)
    return jsonify({"reply": reply, "ticket_id": ticket_id})


# ── Health check ───────────────────────────────────────────────────────────

@flask_app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200


if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    print(f"📧 Email webhook listening on :{port} → POST /support/email-webhook")
    flask_app.run(host="0.0.0.0", port=port, debug=os.getenv("FLASK_ENV") == "development")
