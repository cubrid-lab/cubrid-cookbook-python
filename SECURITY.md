# Security Policy

## Supported Versions

This repository is a collection of examples and is not published as a package.
Security fixes are applied only to `main`; tagged snapshots are not patched.
Runtime support (Python, CUBRID and driver versions) is defined in
[`SUPPORT_MATRIX.md`](SUPPORT_MATRIX.md).

## Reporting a Vulnerability

If you discover a security issue in cubrid-cookbook examples, please report it
privately:

1. **Email (preferred):** paikend@gmail.com
2. **GitHub private vulnerability reporting:** if the repository's **Security**
   tab shows a **Report a vulnerability** button, you can use it instead of email.
   It is equally private.
3. **Fallback:** if you receive no acknowledgment within the timeline below, or
   cannot use either route, open a public issue with the **Security contact
   request** issue form. It contains **no** vulnerability details; a maintainer
   replies with a private channel.

**Do not** put vulnerability details in a public GitHub issue, pull request or
discussion. Responsible disclosure allows us to address the issue before public
disclosure.

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
