"""Flask routes adapting Web OAuth to the canonical identity-link service."""

from flask import Blueprint, abort, current_app, redirect, request, session

from identity_link_oauth import (
    InvalidIdentityLinkOAuth,
    begin_flow,
    clear_flow,
    consume_callback,
)

LINK_KEYS = (
    "identity_link_candidate",
    "identity_link_proof",
    "identity_link_summary",
    "identity_link_binding",
    "identity_link_candidate_provider",
    "identity_link_purpose",
    "identity_link_oauth_stage",
)


def clear_identity_link_state():
    clear_flow(session)
    for key in LINK_KEYS:
        session.pop(key, None)


def create_identity_link_blueprint(
    *, provider_port, service, require_csrf, allowed_redirects, current_person_id
):
    blueprint = Blueprint("identity_link_web", __name__)

    @blueprint.post("/api/v1/auth/identity-link/web/begin/<provider>")
    def begin(provider):
        require_csrf()
        purpose, stage = request.form.get("purpose"), request.form.get("stage")
        if stage not in {"candidate", "proof"}:
            abort(400)
        if purpose == "self_link" and current_person_id() is None:
            abort(401)
        if stage == "candidate":
            clear_identity_link_state()
        elif "identity_link_candidate" not in session:
            abort(409)
        elif purpose != session.get("identity_link_purpose"):
            abort(409)
        redirect_uri = provider_port.redirect_uri(provider)
        oauth = begin_flow(
            session,
            secret_key=current_app.secret_key,
            provider=provider,
            purpose=purpose,
            redirect_uri=redirect_uri,
            allowed_redirects=allowed_redirects,
        )
        session["identity_link_oauth_stage"] = stage
        return redirect(
            provider_port.authorization_url(
                provider=provider,
                state=oauth["state"],
                nonce=oauth["nonce"],
                redirect_uri=redirect_uri,
                code_challenge=oauth["code_challenge"],
            )
        )

    @blueprint.get("/api/v1/auth/identity-link/web/callback/<provider>")
    def callback(provider):
        stage = session.pop("identity_link_oauth_stage", None)
        redirect_uri = provider_port.redirect_uri(provider)
        try:
            flow = consume_callback(
                session,
                secret_key=current_app.secret_key,
                state=request.args.get("state"),
                provider=provider,
                redirect_uri=redirect_uri,
                allowed_redirects=allowed_redirects,
            )
        except InvalidIdentityLinkOAuth:
            clear_identity_link_state()
            abort(400)
        if stage not in {"candidate", "proof"} or not request.args.get("code"):
            clear_identity_link_state()
            abort(400)
        token = provider_port.exchange_code(
            provider=provider,
            code=request.args["code"],
            redirect_uri=redirect_uri,
            code_verifier=flow["code_verifier"],
        )
        verified = provider_port.verify_id_token(
            provider=provider, id_token=token, nonce=flow["oidc_nonce"]
        )
        if stage == "candidate":
            result = service.begin_candidate(
                provider=provider,
                subject=verified.subject,
                raw_assertion=token,
                attempt_id=flow["flow_nonce"],
                binding=flow["flow_nonce"],
            )
            session["identity_link_candidate"] = result["candidate_credential"]
            session["identity_link_binding"] = flow["flow_nonce"]
            session["identity_link_candidate_provider"] = provider
            session["identity_link_purpose"] = flow["purpose"]
        else:
            result = service.issue_fresh_proof(
                candidate_credential=session["identity_link_candidate"],
                provider=provider,
                subject=verified.subject,
                attempt_id=flow["flow_nonce"],
                binding=session["identity_link_binding"],
            )
            session["identity_link_proof"] = result["proof_credential"]
            session["identity_link_summary"] = {
                "candidate_provider": result["candidate_provider"],
                "proof_provider": result["proof_provider"],
                "person": result["person"],
            }
        return redirect(
            "/identity-recovery"
            if flow["purpose"] == "recovery_link"
            else "/account#login-methods"
        )

    @blueprint.post("/api/v1/auth/identity-link/web/confirm")
    def confirm():
        require_csrf()
        if request.form.get("confirmed") != "true":
            abort(400)
        if request.form.get("purpose") != session.get("identity_link_purpose"):
            abort(409)
        result = service.confirm_web(
            candidate_credential=session.get("identity_link_candidate"),
            proof_credential=session.get("identity_link_proof"),
            binding=session.get("identity_link_binding"),
            outcome=session.get("identity_link_purpose"),
            current_person_id=current_person_id(),
            platform=None,
        )
        principal = result.web_principal
        if principal is None:
            abort(503)
        session.clear()
        session.update(
            person_id=principal.person_id,
            auth_identity_id=principal.identity_id,
        )
        if principal.member_id is not None:
            session["member_id"] = principal.member_id
        else:
            session.pop("member_id", None)
        return redirect("/account")

    @blueprint.post("/api/v1/auth/identity-link/web/cancel")
    def cancel():
        require_csrf()
        clear_identity_link_state()
        return {"status": "cancelled_on_this_device"}

    return blueprint
