# Security Policy

## Supported Versions

This repository is a collection of examples and is not published as a package.
Security fixes are applied only to `main`; tagged snapshots are not patched.
Runtime support (Python, CUBRID and driver versions) is defined in
[`SUPPORT_MATRIX.md`](SUPPORT_MATRIX.md).

## Reporting a Vulnerability

If you discover a security issue in cubrid-cookbook examples, please report it responsibly by emailing:

**Email:** paikend@gmail.com

GitHub private vulnerability reporting is not currently enabled for this
repository, so email is the supported private route.

**Do not** open a public GitHub issue for security vulnerabilities. Responsible disclosure allows us to address the issue before public disclosure.

### Response Timeline

- **48 hours:** Initial acknowledgment of your report
- **7 days:** Security assessment and initial response with remediation plan
- **Ongoing:** Regular updates on progress until resolution

## What Qualifies as a Security Issue

A security issue is any vulnerability that could:

- Allow unauthorized access to data
- Permit SQL injection or other code execution attacks
- Expose sensitive information (credentials, tokens, private data)
- Compromise confidentiality, integrity, or availability of the system

Examples include:
- SQL injection vulnerabilities in example code
- Hardcoded credentials in examples
- Insecure configuration patterns

## Security Best Practices

When using cubrid-cookbook examples in production:

- Always use parameterized queries to prevent SQL injection
- Never hardcode credentials — use environment variables
- Keep all dependencies updated to the latest versions
- Follow the principle of least privilege for database credentials
- Use secure connection parameters when connecting to CUBRID databases

## Disclosure Policy

Once a security vulnerability is fixed:

1. The fix lands on `main`
2. The vulnerability is described in `CHANGELOG.md`
3. Credit will be given to the reporter (if requested)

We appreciate your responsible disclosure and help in keeping cubrid-cookbook secure.
