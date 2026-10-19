"""Content-disposition policy, not a scanner, mutation permit or erasure proof.

Only a trusted server adapter may supply evidence. Legacy free text has incomplete
attribution by default: a missing subject reference is not proof of anonymity.
USER_CONTENT means personal authored content, not merely an actor FK on a shared
team record. Classification must come from a reviewed field contract, never from
the applicant or an administrator choosing a convenient exemption at deletion time.

Apply only to a bounded inventory. This function cannot discover every mention,
establish inventory completeness, authorize access, or approve a text replacement.
Review decisions require exact record/version checks and storage-level removal;
UI overlays and removing the author's name do not count as deleting own content.
"""

from dataclasses import dataclass
from enum import Enum


class ContentOrigin(Enum):
    USER_CONTENT = "user_content"
    SHARED_TEAM_RECORD = "shared_team_record"
    SYSTEM_TEMPLATE = "system_template"
    UNKNOWN = "unknown"


class ContentDisposition(Enum):
    DELETE_OWN_CONTENT = "delete_own_content"
    REVIEW_SHARED_CONTENT = "review_shared_content"
    REMOVE_ACTOR_REFERENCE = "remove_actor_reference"
    KEEP_UNRELATED = "keep_unrelated"


class ContentPolicyRejected(ValueError):
    def __init__(self):
        super().__init__("invalid_content_evidence")


@dataclass(frozen=True)
class ContentEvidence:
    origin: ContentOrigin
    author_person_id: int | None
    subject_person_ids: frozenset[int]
    attribution_complete: bool = False


def disposition_for(
    target_person_id: int, evidence: ContentEvidence
) -> ContentDisposition:
    """Choose a bounded action without reading or emitting personal text.

    attribution_complete must be established by structured field provenance or
    an authorized review of the exact content version. Neither empty tags nor a
    negative name search establish it. REMOVE_ACTOR_REFERENCE is NOT an anonymity
    guarantee: indirect identifying text must have been reviewed independently.
    """
    if (
        type(target_person_id) is not int
        or target_person_id <= 0
        or type(evidence) is not ContentEvidence
    ):
        raise ContentPolicyRejected()
    if (
        type(evidence.origin) is not ContentOrigin
        or type(evidence.attribution_complete) is not bool
        or type(evidence.subject_person_ids) is not frozenset
        or any(
            type(value) is not int or value <= 0
            for value in evidence.subject_person_ids
        )
        or (
            evidence.author_person_id is not None
            and (
                type(evidence.author_person_id) is not int
                or evidence.author_person_id <= 0
            )
        )
    ):
        raise ContentPolicyRejected()
    if evidence.origin is ContentOrigin.UNKNOWN:
        return ContentDisposition.REVIEW_SHARED_CONTENT
    if evidence.origin is ContentOrigin.USER_CONTENT:
        if evidence.author_person_id == target_person_id:
            return ContentDisposition.DELETE_OWN_CONTENT
        if evidence.author_person_id is None:
            return ContentDisposition.REVIEW_SHARED_CONTENT
    if (
        not evidence.attribution_complete
        or target_person_id in evidence.subject_person_ids
    ):
        return ContentDisposition.REVIEW_SHARED_CONTENT
    if evidence.author_person_id == target_person_id:
        return ContentDisposition.REMOVE_ACTOR_REFERENCE
    return ContentDisposition.KEEP_UNRELATED
