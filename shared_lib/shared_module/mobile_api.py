"""Server-owned native auth and Basic API application contracts."""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Callable, Protocol

from .attendance_reply import AttendanceReplyCommand, AttendanceReplyService


class MobileApiError(RuntimeError):
    code = "service_unavailable"
    status = 503


class AuthenticationError(MobileApiError):
    code, status = "unauthenticated", 401


class MalformedRequest(MobileApiError):
    code, status = "malformed_request", 400


class PermissionDenied(MobileApiError):
    code, status = "forbidden", 403


class IdentityPending(PermissionDenied):
    code = "identity_pending"


class AccountUnavailable(PermissionDenied):
    code = "account_unavailable"


class NotFound(MobileApiError):
    code, status = "resource_not_found", 404


class Conflict(MobileApiError):
    code, status = "state_conflict", 409


class IdempotencyConflict(Conflict):
    code = "idempotency_conflict"


class InvalidArgument(MobileApiError):
    code, status = "validation_failed", 422


class AttendanceReplyValue(str, Enum):
    ATTENDING = "attending"
    NOT_ATTENDING = "not_attending"
    ARRIVING_LATE = "arriving_late"
    LEAVING_EARLY = "leaving_early"
    UNDECIDED = "undecided"

    @property
    def legacy_value(self) -> int:
        return list(type(self)).index(self) + 1

    @classmethod
    def from_legacy(cls, value: int) -> "AttendanceReplyValue":
        if type(value) is not int or not 1 <= value <= len(cls):
            raise InvalidArgument("unknown stored attendance reply")
        try:
            return list(cls)[value - 1]
        except IndexError:
            raise InvalidArgument("unknown stored attendance reply") from None


@dataclass(frozen=True)
class VerifiedAssertion:
    provider: str
    subject: str
    audience: str
    nonce: str
    expires_at: datetime


@dataclass(frozen=True)
class MobilePrincipal:
    session_id: str
    person_id: int
    identity_id: int
    access_level: str
    display_name: str
    access_epoch: int


@dataclass(frozen=True)
class TokenPair:
    access_token: str
    refresh_token: str
    session_id: str
    expires_in: int


class AssertionVerifier(Protocol):
    def verify(
        self, assertion: str, audience: str, nonce: str, now: datetime
    ) -> VerifiedAssertion: ...


class SuccessorCipher(Protocol):
    def seal(self, value: bytes) -> bytes: ...
    def open(self, value: bytes) -> bytes: ...


class MobileAuthRepository(Protocol):
    def exchange(self, **values) -> MobilePrincipal: ...
    def rotate(self, **values) -> tuple[TokenPair, bool]: ...
    def logout(self, session_id: str, now: datetime) -> None: ...
    def principal(
        self,
        session_id: str,
        person_id: int,
        identity_id: int,
        access_epoch: int,
        now: datetime,
    ) -> MobilePrincipal | None: ...
    def idempotent(self, **values) -> tuple[int, dict, bool]: ...


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def secret_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def canonical_hash(value: object) -> str:
    encoded = json.dumps(
        value, ensure_ascii=True, sort_keys=True, separators=(",", ":")
    )
    return secret_hash(encoded)


class HmacAccessTokenCodec:
    def __init__(self, key: bytes, *, ttl: timedelta = timedelta(minutes=15)):
        if len(key) < 32:
            raise ValueError("access token key must contain at least 32 bytes")
        self._key, self._ttl = key, ttl

    def issue(self, principal: MobilePrincipal, now: datetime) -> tuple[str, int]:
        expires = now + self._ttl
        payload = {
            "sid": principal.session_id,
            "sub": principal.person_id,
            "iid": principal.identity_id,
            "ep": principal.access_epoch,
            "exp": int(expires.timestamp()),
        }
        body = base64.urlsafe_b64encode(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).rstrip(b"=")
        signature = hmac.new(self._key, body, hashlib.sha256).digest()
        return b".".join(
            (body, base64.urlsafe_b64encode(signature).rstrip(b"="))
        ).decode(), int(self._ttl.total_seconds())

    def verify(self, token: str, now: datetime) -> dict:
        try:
            body_text, signature_text = token.split(".", 1)
            body = body_text.encode()
            signature = base64.urlsafe_b64decode(
                signature_text + "=" * (-len(signature_text) % 4)
            )
            expected = hmac.new(self._key, body, hashlib.sha256).digest()
            if not hmac.compare_digest(signature, expected):
                raise ValueError
            payload = json.loads(
                base64.urlsafe_b64decode(body_text + "=" * (-len(body_text) % 4))
            )
            if int(payload["exp"]) <= int(now.timestamp()):
                raise ValueError
            return payload
        except (
            binascii.Error,
            json.JSONDecodeError,
            KeyError,
            OverflowError,
            TypeError,
            UnicodeDecodeError,
            ValueError,
        ):
            raise AuthenticationError("invalid access token") from None


class MobileAuthService:
    def __init__(
        self,
        repository: MobileAuthRepository,
        verifier: AssertionVerifier,
        cipher: SuccessorCipher,
        token_codec: HmacAccessTokenCodec,
        *,
        audience: str,
        clock: Callable[[], datetime] = utc_now,
        token_factory: Callable[[], str] = lambda: secrets.token_urlsafe(48),
    ):
        if not audience:
            raise ValueError("audience is required")
        self.repository, self.verifier, self.cipher = repository, verifier, cipher
        self.token_codec, self.audience, self.clock, self.token_factory = (
            token_codec,
            audience,
            clock,
            token_factory,
        )

    def exchange(
        self,
        *,
        assertion: str,
        nonce: str,
        login_attempt_id: str,
        installation_id: str,
        platform: str,
    ) -> TokenPair:
        self._bounded(assertion, 1, 2048)
        for value in (nonce, login_attempt_id, installation_id):
            self._bounded(value, 16, 200)
        if platform not in {"ios", "android"}:
            raise InvalidArgument("unsupported platform")
        now = self.clock()
        verified = self.verifier.verify(assertion, self.audience, nonce, now)
        if (
            verified.audience != self.audience
            or verified.nonce != nonce
            or verified.expires_at <= now
        ):
            raise AuthenticationError("invalid provider assertion")
        refresh = self.token_factory()
        principal = self.repository.exchange(
            provider=verified.provider,
            subject=verified.subject,
            assertion_hash=secret_hash(assertion),
            login_attempt_hash=secret_hash(login_attempt_id),
            installation_id_hash=secret_hash(installation_id),
            platform=platform,
            refresh_hash=secret_hash(refresh),
            now=now,
        )
        access, expires = self.token_codec.issue(principal, now)
        return TokenPair(access, refresh, principal.session_id, expires)

    def refresh(
        self, *, refresh_token: str, refresh_attempt_id: str, installation_id: str
    ) -> TokenPair:
        self._bounded(refresh_token, 32, 2048)
        self._bounded(refresh_attempt_id, 16, 200)
        self._bounded(installation_id, 16, 200)
        now, successor = self.clock(), self.token_factory()
        pair, _replayed = self.repository.rotate(
            refresh_hash=secret_hash(refresh_token),
            attempt_id_hash=secret_hash(refresh_attempt_id),
            request_hash=canonical_hash(
                {
                    "refresh": secret_hash(refresh_token),
                    "installation": secret_hash(installation_id),
                }
            ),
            installation_id_hash=secret_hash(installation_id),
            successor_hash=secret_hash(successor),
            successor=successor,
            cipher=self.cipher,
            token_codec=self.token_codec,
            now=now,
        )
        return pair

    def authenticate(self, token: str) -> MobilePrincipal:
        now = self.clock()
        payload = self.token_codec.verify(token, now)
        principal = self.repository.principal(
            payload["sid"],
            int(payload["sub"]),
            int(payload["iid"]),
            int(payload["ep"]),
            now,
        )
        if principal is None:
            raise AuthenticationError("inactive session")
        return principal

    @staticmethod
    def _bounded(value: str, minimum: int, maximum: int) -> None:
        if not isinstance(value, str) or not minimum <= len(value) <= maximum:
            raise InvalidArgument("required field is malformed")


class BasicApiService:
    def __init__(
        self,
        data_repository,
        attendance: AttendanceReplyService,
        auth_repository: MobileAuthRepository,
        *,
        clock: Callable[[], datetime] = utc_now,
    ):
        self.data, self.attendance, self.auth, self.clock = (
            data_repository,
            attendance,
            auth_repository,
            clock,
        )

    def games(self, principal: MobilePrincipal):
        return self.data.scoped_games(principal.person_id, self.clock())

    def games_page(
        self, principal: MobilePrincipal, cursor: str | None, limit: int
    ) -> dict:
        if not 1 <= limit <= 100:
            raise InvalidArgument("limit must be between 1 and 100")
        offset = 0
        if cursor:
            try:
                offset = int(
                    base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)).decode(
                        "ascii"
                    )
                )
            except (ValueError, UnicodeError):
                raise InvalidArgument("cursor is malformed") from None
            if offset < 0:
                raise InvalidArgument("cursor is malformed")
        games = self.games(principal)
        page = games[offset : offset + limit]
        next_offset = offset + len(page)
        next_cursor = None
        if next_offset < len(games):
            next_cursor = (
                base64.urlsafe_b64encode(str(next_offset).encode("ascii"))
                .rstrip(b"=")
                .decode("ascii")
            )
        return {
            "items": [self._public_game(game) for game in page],
            "next_cursor": next_cursor,
        }

    def attendance_view(self, principal: MobilePrincipal, game_id: int) -> dict:
        self._game(principal, game_id)
        own = self.data.own_attendance_reply(principal.person_id, game_id)
        summary = self.data.attendance_summaries((game_id,), use_display_name=True).get(
            game_id
        )
        participants = []
        if summary is not None:
            participants = [
                {
                    "person_id": f"person_{item['person_id']}",
                    "display_name": item["name"],
                    "reply": AttendanceReplyValue.from_legacy(item["reply"]).value,
                    "qualification": item["qualification"],
                }
                for item in summary.participants
            ]
        return {
            "game_id": f"game_{game_id}",
            "own_reply": (
                None if own is None else AttendanceReplyValue.from_legacy(own).value
            ),
            "replied": participants,
        }

    def game(self, principal: MobilePrincipal, game_id: int):
        return self._public_game(self._game(principal, game_id))

    def _game(self, principal: MobilePrincipal, game_id: int):
        game = self.data.scoped_game(principal.person_id, game_id, self.clock())
        if game is None:
            raise NotFound("game not found")
        return game

    @staticmethod
    def _public_game(game: dict) -> dict:
        result = dict(game)
        result["id"] = f"game_{result['id']}"
        start = result.get("start_at")
        if isinstance(start, datetime):
            result["start_at"] = (
                start.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
            )
        return result

    def attendance_reply(
        self,
        principal: MobilePrincipal,
        game_id: int,
        reply: int,
        key: str,
        notification,
    ) -> tuple[int, dict, bool]:
        try:
            value = AttendanceReplyValue(reply)
        except ValueError:
            raise InvalidArgument("unknown attendance reply") from None
        game = self._game(principal, game_id)
        request = {"reply": value.value}

        def mutation():
            result = self.attendance.reply(
                AttendanceReplyCommand(
                    principal.person_id,
                    game_id,
                    value.legacy_value,
                    game["start_at"],
                    notification,
                )
            )
            return 200, {
                "game_id": f"game_{game_id}",
                "reply": value.value,
                "changed": result.changed,
                "updated_at": self.clock()
                .astimezone(timezone.utc)
                .isoformat()
                .replace("+00:00", "Z"),
                "notification": {
                    "status": result.notification_status.value,
                    "code": getattr(result, "notification_error", None),
                },
            }

        return self.auth.idempotent(
            session_id=principal.session_id,
            person_id=principal.person_id,
            method="PUT",
            route=f"/api/v1/games/game_{game_id}/attendance-reply",
            key_hash=secret_hash(key),
            request_hash=canonical_hash(request),
            mutation=mutation,
            now=self.clock(),
        )
