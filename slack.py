"""
channels/slack.py — Slack Bolt listener (cookbook §06).

Cookbook spec:
  - Listen for app_mention events
  - slack_uid_to_customer() resolves Slack UID → canonical customer_id
  - Acknowledge immediately with "_Looking up your account..._"
  - Call handle_ticket(), update the ack message with the reply

Usage:
    export SLACK_BOT_TOKEN=xoxb-...
    export SLACK_APP_TOKEN=xapp-...
    python channels/slack.py
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from support.respond import handle_ticket

app = App(token=os.environ["SLACK_BOT_TOKEN"])


def slack_uid_to_customer(slack_uid: str) -> str:
    """
    Cookbook §06: resolve Slack UID → canonical customer_id.
    In production: call your CRM / auth system here.
    Consistent customer_id across channels enables cross-channel memory.
    """
    # Replace with: return crm_lookup(slack_uid)
    return f"slack-{slack_uid}"


@app.event("app_mention")
def handle_support_mention(event, client):
    customer_id  = slack_uid_to_customer(event["user"])
    customer_msg = event["text"].split(">", 1)[-1].strip()
    ticket_id    = f"slack-{event['ts']}"

    # Acknowledge immediately — customers hate silence (cookbook §06)
    ack = client.chat_postMessage(
        channel=event["channel"],
        thread_ts=event["ts"],
        text="_Looking up your account..._",
    )

    reply = handle_ticket(customer_id, customer_msg, ticket_id)

    client.chat_update(
        channel=event["channel"],
        ts=ack["ts"],
        text=reply,
    )


if __name__ == "__main__":
    handler = SocketModeHandler(app, os.environ["SLACK_APP_TOKEN"])
    print("⚡ Slack support agent running in Socket Mode...")
    handler.start()
