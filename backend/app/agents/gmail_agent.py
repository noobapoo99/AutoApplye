from __future__ import annotations

import asyncio
import base64
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import logging
from typing import Any

from agents.base import AgentFactory
from agents.base import BaseAgent


logger = logging.getLogger(__name__)

GMAIL_SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
MAX_GMAIL_MESSAGES = 10
MAX_CLASSIFICATION_ATTEMPTS = 3
EMAIL_CLASSIFICATIONS = [
    "interview_invite",
    "rejection",
    "assessment",
    "follow_up_needed",
    "other",
]


@AgentFactory.register("gmail")
class GmailTrackerAgent(BaseAgent):
    agent_name = "gmail_tracker"

    def __init__(
        self,
        credentials: dict[str, Any] | None = None,
        llm: Any | None = None,
        scorer: Any | None = None,
    ) -> None:
        super().__init__(llm=llm, scorer=scorer)
        self.credentials = credentials or {}

    def validate_input(self, payload: Any) -> bool:
        if not isinstance(payload, dict):
            return False

        return bool(
            payload.get("application_id")
            and payload.get("company_name")
            and payload.get("role_title")
            and payload.get("applied_at")
        )

    async def process(self, payload: Any) -> dict[str, Any]:
        application_id = str(payload["application_id"])
        company_name = str(payload["company_name"])
        role_title = str(payload["role_title"])
        applied_at = str(payload["applied_at"])

        emails = await self._fetch_emails(company_name, applied_at)
        grouped_threads = self._group_threads(emails)

        email_threads: list[dict[str, Any]] = []
        for email_data in grouped_threads:
            thread = await self._process_email(
                email_data,
                company_name,
                role_title,
                application_id,
            )
            if thread is not None:
                email_threads.append(thread)

        return {
            "application_id": application_id,
            "company_name": company_name,
            "role_title": role_title,
            "email_threads": email_threads,
            "total_emails_found": len(grouped_threads),
        }

    async def emit_result(
        self,
        result: dict[str, Any],
        original_payload: Any,
    ) -> None:
        logger.info(
            "Gmail tracker completed for application_id=%s threads=%s",
            result.get("application_id"),
            result.get("total_emails_found"),
        )

    async def _fetch_emails(
        self,
        company: str,
        applied_at: str,
    ) -> list[dict[str, Any]]:
        if not self.credentials:
            return []

        after_date = self._format_after_date(applied_at)
        query = f'from:*{company}* OR subject:"{company}" after:{after_date}'
        credentials_info = dict(self.credentials)
        loop = asyncio.get_running_loop()

        def _fetch_sync() -> list[dict[str, Any]]:
            from google.oauth2.credentials import Credentials
            from googleapiclient.discovery import build

            creds = self._build_credentials(Credentials, credentials_info)
            service = build(
                "gmail",
                "v1",
                credentials=creds,
                cache_discovery=False,
            )
            messages_response = (
                service.users()
                .messages()
                .list(
                    userId="me",
                    q=query,
                    maxResults=MAX_GMAIL_MESSAGES,
                )
                .execute()
            )
            messages = messages_response.get("messages", [])

            full_messages: list[dict[str, Any]] = []
            for message in messages:
                message_id = message.get("id")
                if not message_id:
                    continue
                full_message = (
                    service.users()
                    .messages()
                    .get(
                        userId="me",
                        id=message_id,
                        format="full",
                    )
                    .execute()
                )
                if isinstance(full_message, dict):
                    full_messages.append(full_message)

            return full_messages

        try:
            return await loop.run_in_executor(None, _fetch_sync)
        except Exception:
            logger.exception("Failed to fetch Gmail messages for company %s", company)
            return []

    async def _process_email(
        self,
        email_data: dict[str, Any],
        company: str,
        role: str,
        application_id: str,
    ) -> dict[str, Any] | None:
        gmail_thread_id = str(email_data.get("threadId") or email_data.get("id") or "").strip()
        if not gmail_thread_id:
            logger.warning(
                "Skipping Gmail message without thread identifier for application_id=%s",
                application_id,
            )
            return None

        subject = self._get_header(email_data, "Subject")
        sender = self._get_header(email_data, "From")
        received_at = self._message_received_at(email_data)
        body = self._extract_body(email_data)
        classification, dlq_attempts = await self._classify_with_dlq(
            body=body,
            subject=subject,
            company=company,
            role=role,
            application_id=application_id,
        )

        summary_source = "\n\n".join(
            part for part in [f"Subject: {subject}" if subject else "", body] if part
        )
        ai_summary = await self._summarize(summary_source)

        draft_followup = ""
        if classification in {"follow_up_needed", "other"}:
            draft_followup = await self._draft_followup(
                company=company,
                role=role,
                original_subject=subject,
                body=body,
                classification=classification,
            )

        return {
            "gmail_thread_id": gmail_thread_id,
            "subject": subject,
            "sender": sender,
            "received_at": received_at,
            "classification": classification,
            "ai_summary": ai_summary,
            "draft_followup": draft_followup,
            "application_id": application_id,
            "dlq_attempts": dlq_attempts,
        }

    async def _classify_with_dlq(
        self,
        *,
        body: str,
        subject: str,
        company: str,
        role: str,
        application_id: str,
        attempt: int = 0,
    ) -> tuple[str, int]:
        prompt = (
            "Classify the following job-application related email. "
            "Return only one label from this list:\n"
            f"{', '.join(EMAIL_CLASSIFICATIONS)}\n\n"
            f"Company: {company}\n"
            f"Role: {role}\n"
            f"Subject: {subject}\n\n"
            f"Body:\n{body[:8000]}"
        )

        try:
            response = await self.llm.complete(
                prompt=prompt,
                system=(
                    "You classify recruiting emails. Reply with one label only from "
                    "the allowed list."
                ),
                use_cache=False,
            )
            classification = response.strip().lower()
            if classification not in EMAIL_CLASSIFICATIONS:
                raise ValueError(f"Invalid email classification: {classification}")
            return classification, attempt
        except Exception as exc:
            if attempt >= MAX_CLASSIFICATION_ATTEMPTS - 1:
                logger.error(
                    "Gmail classification DLQ event application_id=%s company=%s role=%s "
                    "subject=%s attempts=%s error=%s",
                    application_id,
                    company,
                    role,
                    subject,
                    attempt + 1,
                    exc,
                )
                return "other", attempt + 1

            await asyncio.sleep(2**attempt)
            return await self._classify_with_dlq(
                body=body,
                subject=subject,
                company=company,
                role=role,
                application_id=application_id,
                attempt=attempt + 1,
            )

    async def _summarize(self, text: str) -> str:
        if not text.strip():
            return ""

        try:
            response = await self.llm.complete(
                prompt=(
                    "Summarize the following recruiting email in one sentence.\n\n"
                    f"{text[:8000]}"
                ),
                system="You summarize recruiting emails in one concise sentence.",
                use_cache=False,
            )
            return response.strip()
        except Exception:
            logger.exception("Failed to summarize Gmail thread")
            return ""

    async def _draft_followup(
        self,
        *,
        company: str,
        role: str,
        original_subject: str,
        body: str,
        classification: str,
    ) -> str:
        try:
            response = await self.llm.complete(
                prompt=(
                    "Write a professional follow-up email body only. Do not include a "
                    "subject line, salutation placeholder, or signature placeholder.\n\n"
                    f"Company: {company}\n"
                    f"Role: {role}\n"
                    f"Classification: {classification}\n"
                    f"Original subject: {original_subject}\n\n"
                    f"Original email body:\n{body[:8000]}"
                ),
                system=(
                    "You draft concise professional follow-up emails for job "
                    "applications. Return the email body only."
                ),
                use_cache=False,
            )
            return response.strip()
        except Exception:
            logger.exception("Failed to draft Gmail follow-up")
            return ""

    @staticmethod
    def _build_credentials(
        credentials_cls: Any,
        credentials_info: dict[str, Any],
    ) -> Any:
        scopes = credentials_info.get("scopes") or GMAIL_SCOPES
        try:
            return credentials_cls.from_authorized_user_info(
                credentials_info,
                scopes=scopes,
            )
        except Exception:
            return credentials_cls(
                token=credentials_info.get("token"),
                refresh_token=credentials_info.get("refresh_token"),
                token_uri=credentials_info.get("token_uri"),
                client_id=credentials_info.get("client_id"),
                client_secret=credentials_info.get("client_secret"),
                scopes=scopes,
            )

    @staticmethod
    def _format_after_date(applied_at: str) -> str:
        normalized = applied_at.strip()
        if normalized.endswith("Z"):
            normalized = normalized[:-1] + "+00:00"

        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            if len(applied_at) >= 10:
                return applied_at[:10].replace("-", "/")
            raise

        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).strftime("%Y/%m/%d")

    @staticmethod
    def _group_threads(emails: list[dict[str, Any]]) -> list[dict[str, Any]]:
        latest_by_thread: dict[str, dict[str, Any]] = {}

        for email_data in emails:
            if not isinstance(email_data, dict):
                continue
            thread_id = str(email_data.get("threadId") or email_data.get("id") or "").strip()
            if not thread_id:
                continue

            existing = latest_by_thread.get(thread_id)
            if existing is None or (
                GmailTrackerAgent._message_sort_key(email_data)
                > GmailTrackerAgent._message_sort_key(existing)
            ):
                latest_by_thread[thread_id] = email_data

        return sorted(
            latest_by_thread.values(),
            key=GmailTrackerAgent._message_sort_key,
            reverse=True,
        )

    @staticmethod
    def _get_header(email_data: dict[str, Any], name: str) -> str:
        payload = email_data.get("payload", {})
        headers = payload.get("headers", []) if isinstance(payload, dict) else []
        target = name.lower()
        for header in headers:
            if not isinstance(header, dict):
                continue
            header_name = str(header.get("name") or "").strip().lower()
            if header_name == target:
                return str(header.get("value") or "").strip()
        return ""

    @staticmethod
    def _extract_body(email_data: dict[str, Any]) -> str:
        payload = email_data.get("payload", {})
        if not isinstance(payload, dict):
            return str(email_data.get("snippet") or "").strip()

        body_data = payload.get("body", {})
        if isinstance(body_data, dict):
            decoded = GmailTrackerAgent._decode_base64_data(body_data.get("data"))
            if decoded:
                return decoded

        plain_text = GmailTrackerAgent._extract_plain_text_from_parts(payload.get("parts"))
        if plain_text:
            return plain_text

        return str(email_data.get("snippet") or "").strip()

    @staticmethod
    def _extract_plain_text_from_parts(parts: Any) -> str:
        if not isinstance(parts, list):
            return ""

        for part in parts:
            if not isinstance(part, dict):
                continue

            if part.get("mimeType") == "text/plain":
                body = part.get("body", {})
                if isinstance(body, dict):
                    decoded = GmailTrackerAgent._decode_base64_data(body.get("data"))
                    if decoded:
                        return decoded

            nested = GmailTrackerAgent._extract_plain_text_from_parts(part.get("parts"))
            if nested:
                return nested

        return ""

    @staticmethod
    def _decode_base64_data(value: Any) -> str:
        if not value:
            return ""

        encoded = str(value)
        padding = (-len(encoded)) % 4
        encoded += "=" * padding

        try:
            decoded = base64.urlsafe_b64decode(encoded.encode("utf-8"))
            return decoded.decode("utf-8", errors="ignore").strip()
        except Exception:
            logger.debug("Failed to decode Gmail body payload", exc_info=True)
            return ""

    @staticmethod
    def _message_sort_key(email_data: dict[str, Any]) -> float:
        internal_date = email_data.get("internalDate")
        if internal_date is not None:
            try:
                return float(internal_date) / 1000.0
            except (TypeError, ValueError):
                pass

        date_header = GmailTrackerAgent._get_header(email_data, "Date")
        if date_header:
            try:
                parsed = parsedate_to_datetime(date_header)
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                return parsed.astimezone(timezone.utc).timestamp()
            except Exception:
                logger.debug("Failed to parse Gmail Date header", exc_info=True)

        return 0.0

    @staticmethod
    def _message_received_at(email_data: dict[str, Any]) -> str:
        internal_date = email_data.get("internalDate")
        if internal_date is not None:
            try:
                parsed = datetime.fromtimestamp(
                    float(internal_date) / 1000.0,
                    tz=timezone.utc,
                )
                return parsed.isoformat()
            except (TypeError, ValueError, OverflowError):
                logger.debug("Failed to parse Gmail internalDate", exc_info=True)

        date_header = GmailTrackerAgent._get_header(email_data, "Date")
        if date_header:
            try:
                parsed = parsedate_to_datetime(date_header)
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                return parsed.astimezone(timezone.utc).isoformat()
            except Exception:
                logger.debug("Failed to parse Gmail header date", exc_info=True)

        return datetime.now(timezone.utc).isoformat()


__all__ = [
    "EMAIL_CLASSIFICATIONS",
    "GmailTrackerAgent",
]
