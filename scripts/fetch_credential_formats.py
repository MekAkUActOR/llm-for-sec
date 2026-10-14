"""常见凭证格式知识（合成描述层）→ C2 隐私/泄露知识语料（docs/04 C2 小节）。

定位：M2 行为目标——识别文本中的凭证并判断"为何不能外传"。本源为**描述性
结构知识**（长什么样、各段含义、泄露后果、检测特征），不含任何真实凭证、
不含武器化内容（docs/04 §0 uplift 红线）。

内容为原创描述文本;事实性格式规范（前缀/长度/分段结构,事实不受著作权
保护）取自各厂商公开文档与 IETF RFC,来源与许可逐字记录于 manifest note:

  RFC 7519 (JWT) — IETF,版权告示逐字:"Copyright (c) 2015 IETF Trust and
    the persons identified as the document authors. All rights reserved."
    并按 BCP 78 授予复制与分发权（RFC 文本允许 unlimited distribution）。
  AWS Docs — AWS Documentation Terms（aws.amazon.com/terms/,2026-09-26
    核验,摘要:"The AWS Documentation is provided ... subject to the terms
    of the AWS Customer Agreement or other agreement governing your use of
    AWS services"）——本源仅引用其事实性格式串（arn:partition:service:
    region:account-id:resource 等）,不复制其行文。
  GitHub Docs — MIT-licensed docs.github.com 代码仓（github.com/github/
    docs,MIT License）。
  Stripe/Slack/Azure/GCP 公开文档 — 仅引用事实性前缀与长度特征。

产物：data/corpora/clean/c2_privacy_credential_formats.jsonl
manifest：id=credential-formats

用法：python scripts/fetch_credential_formats.py [--no-tokens]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_c0 import count_tokens, upsert_manifest, write_clean  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]

SPEC = {
    "url": "synthesized from public format specifications (see note)",
    "license": ("Original descriptive text; factual format strings cited from "
                "public documentation (facts, no creative expression copied). "
                "Sources: IETF RFC 7519 (Copyright (c) 2015 IETF Trust and the "
                "persons identified as the document authors. All rights "
                "reserved.; BCP 78 grants distribution), AWS Documentation "
                "Terms, GitHub Docs (MIT), Stripe/Slack/Azure/GCP public docs"),
    "domain": "privacy",
    "lang": "en",
    "note": ("Defensive identification knowledge only: describes what common "
             "credential formats look like, their structure, and why they "
             "must not be exposed. No real secrets, no weaponized content "
             "(docs/04 sec.0 uplift red line). Factual format specifications "
             "(prefixes, lengths, segment grammar) are not copyrightable and "
             "are cited to sources; all prose is original. RFC 7519 copyright "
             "notice recorded verbatim: \"Copyright (c) 2015 IETF Trust and "
             "the persons identified as the document authors. All rights "
             "reserved.\" AWS docs terms summary (aws.amazon.com/terms/): "
             "\"The AWS Documentation is provided subject to the terms of the "
             "AWS Customer Agreement or other agreement governing your use of "
             "AWS services.\" GitHub Docs: MIT License."),
    "files": ["data/corpora/clean/c2_privacy_credential_formats.jsonl"],
}


# ---------------------------------------------------------------- 内容（纯数据） --
DOCS: list[str] = [
    """Machine credential taxonomy for leakage detection. Machine credentials are strings that grant access to systems, APIs, or data when presented to a service. For privacy and security review purposes they fall into broad families: (1) bearer tokens, which grant access to whoever presents them (API keys, session tokens, JWTs); (2) asymmetric key material, where a private key file proves identity (PEM-encoded RSA/EC/Ed25519 keys, SSH keys); (3) secrets used for signing or symmetric encryption (HMAC secrets, client secrets); (4) aggregate connection strings, which bundle identity plus endpoint plus secret in one string (database URLs, cloud provider connection strings); and (5) structured identity identifiers that are not secret by themselves but become sensitive in combination (account IDs, ARNs, project IDs). In data-loss-prevention and document-sanitization work, the first two families are the highest priority: a single leaked bearer token or private key is immediately usable by anyone who obtains it. Reviewers should know the characteristic surface shapes of each family: fixed vendor prefixes followed by long random alphabets, base64 or base64url segments, PEM armor lines, and quoted key=value connection parameters. High-entropy character runs in otherwise human-readable text are a strong signal of embedded credentials. Machine credentials must never be committed to repositories, pasted into tickets, or included in training corpora without redaction, because they are designed for automated replay: presentation alone, without any additional proof of identity, is sufficient for access.""",

    """JSON Web Token (JWT) structure, per IETF RFC 7519. A JWT is a compact, URL-safe token format consisting of three base64url-encoded segments joined by periods: header.payload.signature. The header segment decodes to a JSON object naming the algorithm (alg, e.g. HS256 or RS256) and the token type (typ: JWT). The payload segment decodes to a JSON object of claims: registered claims include iss (issuer), sub (subject), aud (audience), exp (expiration time), nbf (not-before), iat (issued-at), and jti (unique token ID). The signature segment is a keyed hash or asymmetric signature computed over header and payload; verifying it requires the shared secret or public key held by the intended recipient only. A JWT in the wild is recognizable by the two-dot-separated three-part pattern with base64url characters (A-Z, a-z, 0-9, hyphen, underscore) and often a 100-800 character total length. Security properties that reviewers must know: the payload is NOT encrypted by default - anyone can base64-decode and read the claims, so payloads must never contain passwords, personal data, or secrets. The exp claim bounds validity, but a leaked token remains fully usable until it expires. Tokens signed with alg:none or with weak HMAC secrets are forgeable. In sanitization work, JWTs appearing in logs, browser captures, or support tickets should be treated as live credentials and redacted, along with any refresh tokens accompanying them.""",

    """AWS access keys and Amazon Resource Names (ARNs). An AWS long-term access credential pair consists of an access key ID and a secret access key. The access key ID is 20 characters, uppercase alphanumeric, with well-known 4-character prefixes: AKIA for standard long-term keys, and ASIA for temporary (STS-issued) keys. The secret access key is 40 characters of mixed-case base64-style alphabet. Only the key ID is an identifier - the secret access key is the actual bearer secret and must never appear in code, tickets, logs, or documents. The characteristic detection pattern is a 20-character AKIA/ASIA-prefixed token near a 40-character high-entropy string. AWS temporary credentials additionally include a session token (aws_session_token), typically a 300-1200 character base64 string; any of the three pieces alone identifies or authenticates, so all three must be redacted together. An Amazon Resource Name (ARN) is the structural identifier of an AWS resource, with the grammar: arn:partition:service:region:account-id:resource, for example arn:aws:s3:::my-bucket or arn:aws-cn:iam::123456789012:role/DeployRole. ARNs are not secrets by themselves - they identify but do not authenticate - yet they leak infrastructure layout (account IDs, bucket names, role names) that assists targeted attacks, so sanitization policies commonly redact account IDs and resource paths as sensitive metadata. Both formats are documented publicly in AWS General Reference documentation.""",

    """Azure storage keys, connection strings, and SAS tokens. Microsoft Azure long-term storage credentials come as account-scoped key pairs: each storage account has two 88-character base64 keys (key1/key2) shown in the portal and usable with either key. The higher-leakage aggregate form is the connection string, which bundles endpoint and secret: DefaultEndpointsProtocol=https;AccountName=<account>;AccountKey=<88-char-base64>;EndpointSuffix=core.windows.net. A connection string alone grants full control of the storage account (blobs, tables, queues, files), so any document containing DefaultEndpointsProtocol or AccountKey= must be treated as containing a live secret. Shared Access Signatures (SAS) are delegating tokens: a service SAS or account SAS is a query-string fragment beginning with sv=<version>&st=<start>&se=<expiry>&sp=<permissions>&sig=<signature> where sig is a computed HMAC over the signed parameters. SAS tokens grant precisely-scoped rights (read-only, specific container, bounded time), which limits but does not eliminate the damage of leakage - a leaked read-scoped SAS still exposes every readable object until expiry. The character shape to recognize: long URL query strings containing sig= plus st=/se= pairs. Azure service principals add a client secret (suffix-terminated random string labeled client_secret or Password in app registrations) and a certificate thumbprint; client secrets follow the same bearer-secret rules as storage keys. In document sanitization, the strings AccountKey=, sig=, and client_secret are redaction anchors.""",

    """Google API keys, OAuth clients, and service account keys. Google Cloud and Google Maps credentials take several recognizable shapes. A Google API key (issued by Google Cloud Console and the Maps platform) is a 39-character string beginning with AIza, drawn from the URL-safe base64 alphabet. API keys alone identify the calling project and enforce quota and restriction, but when embedded client-side in web pages or mobile apps they are public by design - their protection comes from key restrictions (HTTP referrer, IP, API allowlists), not secrecy. What must never leak: OAuth 2.0 client secrets, which are typically 24-35 character strings (gsk_, GOCSPX- prefix for Google OAuth client secrets), and service account private keys. A Google service account key is a JSON file containing fields type: service_account, private_key with an embedded PEM RSA private key, client_email of the form <name>@<project>.iam.gserviceaccount.com, and token_uri - the private_key block inside makes the whole file a live bearer credential for the project. Old P12/PFX key files serve the same role. Detection anchors in text: the AIza prefix, the literal private_key within a JSON block, and the @...iam.gserviceaccount.com email pattern. The gcloud configuration files (~/.config/gcloud/credentials.db, legacy_refresh_token entries) and Application Default Credentials files carry the same sensitivity. Any of these appearing in a document, ticket, or dataset means the credential must be rotated and the text redacted before further handling.""",

    """PEM-encoded private key blocks. PEM (Privacy-Enhanced Mail, RFC 7468) armor wraps base64-encoded binary key material between BEGIN and END delimiter lines. Private key armor lines a reviewer must recognize: -----BEGIN RSA PRIVATE KEY----- (traditional PKCS#1 RSA), -----BEGIN EC PRIVATE KEY----- (SEC1 elliptic curve), -----BEGIN PRIVATE KEY----- (PKCS#8 unencrypted), -----BEGIN ENCRYPTED PRIVATE KEY----- (PKCS#8 passphrase-encrypted), -----BEGIN OPENSSH PRIVATE KEY----- (OpenSSH native format), and -----BEGIN DSA PRIVATE KEY----- (legacy DSA). The body is 25-30 wrapped base64 lines. Any file or text block containing private key armor is a live authentication credential: whoever holds it can impersonate the key owner for TLS client authentication, code signing, SSH, or token signing, until the key is revoked or rotated. Encryption ("ENCRYPTED PRIVATE KEY") only slows the attacker if the passphrase is strong and absent from the same document. Corresponding public material - -----BEGIN PUBLIC KEY-----, -----BEGIN CERTIFICATE-----, -----BEGIN OPENSSH PUBLIC KEY-----, -----BEGIN SSH2 PUBLIC KEY----- - is not secret: public keys and certificates are designed for disclosure, and redacting them is unnecessary (though certificate contents may leak identity metadata). In sanitization pipelines, matching the BEGIN ... PRIVATE KEY armor as a block, plus the base64 body up to the END line, is the standard redaction unit; truncating only the header leaves recoverable key material behind. Detection of private key material must always precede publishing logs, stack traces, configuration dumps, or training data assembled from machine output.""",

    """GitHub token families. GitHub issues several distinguishable token types, each with a fixed prefix that makes them highly recognizable in text. Classic personal access tokens begin ghp_ followed by 36 characters of base64-style alphabet (total 40). Fine-grained personal access tokens begin github_pat_ followed by a long 62+ character body containing underscores. OAuth access tokens begin gho_, GitHub App user-to-server tokens ghu_, GitHub App server-to-server tokens ghs_, and refresh tokens ghr_; each family uses the same 22-character random body convention as classic tokens, totaling 36-41 characters. Older 40-hex-character tokens (the format of classic PATs before the 2021 prefix migration) also still validate and appear in older documentation and logs. A token grants the scopes and repository access of the identity that created it: a classic PAT with repo scope can read private source code and push commits; fine-grained tokens leak more narrowly but are still live credentials. Webhook signatures (a hex digest of the payload keyed with the webhook secret), and Actions secrets in workflow files (referenced as ${{ secrets.NAME }} - the reference is not a secret, but the stored value is) complete the family. Detection anchors: ghp_, gho_, ghu_, ghs_, ghr_, github_pat_ prefixes and 40-hex GitHub-shaped tokens near git remote URLs (https://<token>@github.com/...). Any of these in a document requires immediate revocation plus redaction; committed tokens are automatically scanned and revoked by GitHub only in public repositories, not in private ones or documents outside git.""",

    """Slack, Stripe, and other fixed-prefix platform tokens. Slack tokens are the clearest example of a fixed family grammar: xoxb- (bot user token), xoxp- (legacy user token), xoxa- (workspace app token), xoxs- (search token), xapp- (new-generation app-level token), each followed by numeric workspace/user segments and a final random body (for example a 10-12 digit ID, a hyphen, then 20-24 characters). A xoxp user token grants the reading user's full account powers - including private channels and DM history - so its leakage is account-level compromise. Stripe keys are production-or-test scoped with obvious prefixes: sk_live_ (secret API key, full account access), rk_live_ (restricted key), pk_live_ (publishable key - safe to expose, used client-side), whsec_ (webhook signing secret), sk_test_/pk_test_/whsec_ for test mode. The sk_live_ and whsec_ families are the sensitive ones. SendGrid uses SG. followed by a two-segment key; Twilio API keys begin SK with a 32-hex character body; npm automation tokens begin npm_ ; Docker Hub PATs begin dckr_pat_; GitLab PATs begin glpat-. The common structural rule: a fixed human-readable prefix (which vendors add precisely to make leakage detectable), then 20-64 characters of high-entropy random material, sometimes with separator dots or underscores between segments. For sanitization systems, the prefix table is the primary detector; the redaction rule is to replace the entire token, never just the tail, and to treat any string matching a known vendor prefix as live regardless of whether it was recently rotated.""",

    """Kubernetes Secrets, .env files, and connection-string bundles. Kubernetes Secrets are not encryption: by default they are merely base64-encoded values stored in etcd, retrievable by anyone with read access to the Secret object or with cluster-level list/watch rights. The literal file shape is a YAML manifest with kind: Secret and stringData (plain) or data (base64) keys; because base64 is trivially reversible, a leaked Secret manifest equals plaintext leakage. The kubectl get secret -o yaml output is a common leak vector in pasted debugging sessions. Environment-variable files (.env) bundle credentials as KEY=value lines - DATABASE_URL=postgres://user:password@host:5432/db, REDIS_URL=redis://:password@host:6379, AWS_SECRET_ACCESS_KEY=..., SMTP_PASSWORD=... - and are designed to be gitignored, which makes accidental commits (or copies pasted into tickets to "show the config") the dominant leakage path. Database URLs embed the password after the second slash and before the @: scheme://user:password@host[:port]/database. In DLP terms the whole URL must be redacted, not just the password fragment, because the pair user@host is itself identifying. Other bundle shapes: JDBC URLs (jdbc:postgresql://host/db?user=...&password=...), MongoDB SRV strings (mongodb+srv://user:pass@cluster...), AMQP URLs, and cloud SDK config files (~/.aws/credentials with aws_access_key_id/aws_secret_access_key, ~/.kube/config with client-certificate-data and token fields). Each is a complete bearer credential in one artifact; the redaction unit is the entire file or line, not the secret fragment alone.""",

    """Defensive review heuristics for credential detection in documents. A practical reviewer checklist for recognizing embedded credentials, ordered by signal strength. (1) Fixed vendor prefixes: AKIA/ASIA (AWS), ghp_/github_pat_/gho_ (GitHub), xoxb-/xoxp-/xapp_ (Slack), sk_live_/pk_live_/whsec_ (Stripe), AIza (Google), SG. (SendGrid), glpat- (GitLab), npm_ (npm), dckr_pat_ (Docker), GOCSPX- (Google OAuth client secret). (2) PEM armor lines: any -----BEGIN ... PRIVATE KEY----- block, including the base64 body through the END line. (3) Grammar matches: JWT shape (three base64url segments joined by dots, often starting eyJ because the decoded header begins with {"alg), ARN shape (arn:partition:service:region:account:resource), database URL shape (scheme://user:password@host). (4) Assignment anchors: KEY=value lines whose key name contains password, secret, token, api_key, access_key, private_key, client_secret, AccountKey, sig. (5) Statistical signals: character runs of length 20+ with entropy near the base64 maximum (approximately 5.5-6 bits/character) in otherwise natural-language text, and base64 bodies immediately following armor headers. (6) Context signals: proximity to the words credential, token, key, deploy, production, prod, staging, secret even when the value shape is unfamiliar. The correct handling sequence on detection: mask the credential in the document, report to the credential owner for rotation, and record the document as unsuitable for unrestricted redistribution. For corpora construction: any candidate training document matching families (1)-(3) should be excluded or redacted before ingestion, because model memorization of a live credential reproduces it verbatim at inference time. This knowledge is detection-oriented: it describes shapes and handling rules, and deliberately excludes any usage instructions for credentials found in the wild.""",
]


def build_docs() -> list[str]:
    """纯函数:静态内容 → doc 列表(便于单测断言覆盖与结构)。"""
    return list(DOCS)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Credential format knowledge (C2)")
    ap.add_argument("--no-tokens", action="store_true")
    args = ap.parse_args(argv)

    docs = build_docs()
    out, n = write_clean("c2_privacy_credential_formats", docs)
    tokens = 0 if args.no_tokens else count_tokens(out)
    upsert_manifest("credential-formats", SPEC, "ingested", n, tokens)
    print(f"-> {out.name}: {n} docs, {tokens:,} tokens", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
