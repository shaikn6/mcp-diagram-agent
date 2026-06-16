# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| 0.1.x   | ✅        |

## Reporting a Vulnerability

**Do not open a public GitHub issue for security vulnerabilities.**

Please email the maintainer directly or use
[GitHub's private vulnerability reporting](https://docs.github.com/en/code-security/security-advisories/guidance-on-reporting-and-writing/privately-reporting-a-security-vulnerability).

Include:
- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if you have one)

You will receive a response within **72 hours**. We aim to publish a fix within
**14 days** of a confirmed vulnerability.

## Scope

In scope:
- Remote code execution
- Prompt injection leading to data exfiltration
- Authentication bypass
- Denial of service in the REST API

Out of scope:
- Rate limiting on local dev server
- Issues requiring physical access to the server

## Security Best Practices for Deployers

1. **Never expose `ANTHROPIC_API_KEY` in logs or responses.**
2. **Run the container as a non-root user** (the default Dockerfile already does this).
3. **Add a reverse proxy** (Nginx / Caddy) with TLS in front of the container.
4. **Set `CORS_ORIGINS`** to the specific allowed origins in production.
5. **Rotate your API key** immediately if you suspect it has been leaked.
