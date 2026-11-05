from __future__ import annotations

import builtins
import hashlib
import hmac
import ipaddress
import json
import socket
import threading
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

from app.schemas import new_id, utcnow


@dataclass
class WebhookSubscription:
    id: str
    url: str
    events: builtins.list[str]
    secret: str = ""
    created_at: str = field(default_factory=lambda: utcnow().isoformat())
    deliveries: int = 0
    failures: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "url": self.url,
            "events": list(self.events),
            "created_at": self.created_at,
            "deliveries": self.deliveries,
            "failures": self.failures,
        }


class WebhookRegistry:
    def __init__(self, timeout_seconds: float = 2.0) -> None:
        self.timeout_seconds = timeout_seconds
        self._lock = threading.Lock()
        self._subscriptions: dict[str, WebhookSubscription] = {}

    @staticmethod
    def _safe_url(url: str) -> bool:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return False
        host = parsed.hostname or ""
        try:
            addresses = {info[4][0] for info in socket.getaddrinfo(host, None)}
        except socket.gaierror:
            return True
        for address in addresses:
            ip = ipaddress.ip_address(address)
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                return False
        return True

    def register(self, url: str, events: builtins.list[str] | None = None, secret: str = "") -> dict[str, Any]:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("webhook URL must be an absolute http(s) URL")
        if not self._safe_url(url):
            raise ValueError("webhook URL must not target a private or loopback address")
        selected = [str(event).strip() for event in (events or ["task.completed"]) if str(event).strip()]
        if not selected:
            raise ValueError("at least one webhook event is required")
        subscription = WebhookSubscription(
            id=new_id("wh"),
            url=url,
            events=sorted(set(selected)),
            secret=secret,
        )
        with self._lock:
            self._subscriptions[subscription.id] = subscription
        return subscription.to_dict()

    def list(self) -> builtins.list[dict[str, Any]]:
        with self._lock:
            subscriptions = list(self._subscriptions.values())
        return [subscription.to_dict() for subscription in subscriptions]

    def delete(self, subscription_id: str) -> bool:
        with self._lock:
            return self._subscriptions.pop(subscription_id, None) is not None

    def dispatch(self, event: str, payload: dict[str, Any]) -> builtins.list[dict[str, Any]]:
        with self._lock:
            targets = [
                subscription
                for subscription in self._subscriptions.values()
                if event in subscription.events
            ]
        body = json.dumps({"event": event, "payload": payload}, default=str).encode("utf-8")
        results = []
        for subscription in targets:
            headers = {"Content-Type": "application/json", "X-Agent-Bazaar-Event": event}
            if subscription.secret:
                signature = hmac.new(subscription.secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
                headers["X-Agent-Bazaar-Signature"] = f"sha256={signature}"
            if subscription.secret:
                headers["X-Agent-Bazaar-Secret"] = subscription.secret
            request = urllib.request.Request(
                subscription.url,
                data=body,
                headers=headers,
                method="POST",
            )
            try:
                with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                    status = response.status
                results.append({"subscription_id": subscription.id, "status": status})
            except (urllib.error.URLError, TimeoutError, OSError) as error:
                status = 0
                results.append({"subscription_id": subscription.id, "status": status, "error": str(error)})
            with self._lock:
                subscription.deliveries += 1
                if status < 200 or status >= 300:
                    subscription.failures += 1
        return results
