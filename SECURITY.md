# Security

agentbox is a sandbox, so security problems matter more here than in most projects.

## Reporting a problem

Please do not open a public issue for a way out of the sandbox, a way around the egress
rules, or a way to reach host files or credentials. Use GitHub's private reporting
instead: the **Security** tab of this repository → **Report a vulnerability**.

Include the output of `scripts/agentbox-check.sh`, your distribution, kernel, Podman and
gVisor versions, and the steps to reproduce.

## Scope

In scope: anything that lets code inside a sandbox read or change host files outside the
mounted folders, reach blocked networks, obtain host credentials, escape the resource
caps, or run code on the host (for example through files agentbox writes or reads).

Known limits, not vulnerabilities: see "What agentbox does not protect" in the README.
