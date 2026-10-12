"""Ask a mail server whether it would accept mail for an address, without sending anything.

Connect, EHLO, MAIL FROM, RCPT TO for each address, QUIT. The server's answer
to RCPT says whether the mailbox exists. No DATA is sent, so no email is delivered.

Outbound port 25 is blocked by most home ISPs and cloud providers, so this
needs to run on a server that allows it.
"""

import os
import random
import smtplib
import socket
import string

ACCEPTED = "accepted"
REJECTED = "rejected"
UNKNOWN = "unknown"

# 550s that mean "we don't like you", not "no such user"
BLOCK_HINTS = ("spamhaus", "blocked", "block list", "blocklist", "blacklist", "policy",
               "reputation", "not permitted", "denied", "rbl", "abuse", "client host",
               "access denied", "too many", "rate")


def classify(code: int, message: str) -> str:
    msg = message.lower()
    if code in (250, 251):
        return ACCEPTED
    if code in (550, 551, 553, 554, 552) or (500 <= code < 600):
        if any(h in msg for h in BLOCK_HINTS) and "user" not in msg and "mailbox" not in msg:
            return UNKNOWN
        return REJECTED
    return UNKNOWN  # 4xx: greylisting, rate limits, temporary failures


def random_local(n: int = 14) -> str:
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=n))


class SMTPChecker:
    """Checks recipients on one domain's mail servers. Reuse it for several addresses."""

    def __init__(self, helo: str | None = None, mail_from: str | None = None,
                 port: int | None = None, timeout: float = 15.0):
        self.helo = helo or os.environ.get("SMTP_HELO") or socket.getfqdn()
        self.mail_from = mail_from or os.environ.get("SMTP_FROM") or f"verify@{self.helo}"
        self.port = port or int(os.environ.get("SMTP_PORT", "25"))
        self.timeout = timeout

    def _connect(self, hosts) -> tuple[smtplib.SMTP | None, str]:
        error = "no mail servers"
        for host in hosts[:3]:
            try:
                conn = smtplib.SMTP(timeout=self.timeout)
                conn.connect(host, self.port)
                code, msg = conn.ehlo(self.helo)
                if code != 250:
                    conn.helo(self.helo)
                code, msg = conn.mail(self.mail_from)
                if code != 250:
                    error = f"{host} refused MAIL FROM: {code} {msg.decode(errors='replace')}"
                    conn.close()
                    continue
                return conn, ""
            except (OSError, smtplib.SMTPException) as e:
                error = f"{host}: {e.__class__.__name__}: {e}"
        return None, error

    def check(self, hosts, addresses) -> dict[str, tuple[str, int, str]]:
        """{address: (accepted|rejected|unknown, code, server message)}.

        Stops at the first accepted address, which is how the finder uses it:
        [random probe, candidate1, candidate2, ...] - an accepted probe means
        the server accepts everything, so the rest would tell us nothing.
        Call check_all() to test every address.
        """
        return self._run(hosts, addresses, stop_on_accept=True)

    def check_all(self, hosts, addresses):
        return self._run(hosts, addresses, stop_on_accept=False)

    def _run(self, hosts, addresses, stop_on_accept):
        results: dict[str, tuple[str, int, str]] = {}
        pending = list(addresses)
        reconnects = 0
        while pending and reconnects < 3:
            conn, error = self._connect(hosts)
            if conn is None:
                for a in pending:
                    results[a] = (UNKNOWN, 0, error)
                return results
            try:
                while pending:
                    addr = pending[0]
                    code, msg = conn.rcpt(addr)
                    text = msg.decode(errors="replace")
                    results[addr] = (classify(code, text), code, text)
                    pending.pop(0)
                    if code == 421:  # server is closing the connection
                        break
                    if stop_on_accept and results[addr][0] == ACCEPTED:
                        pending.clear()
            except (OSError, smtplib.SMTPException):
                pass  # dropped mid-session; reconnect for the rest
            finally:
                try:
                    conn.quit()
                except (OSError, smtplib.SMTPException):
                    conn.close()
            reconnects += 1
        for a in pending:
            results.setdefault(a, (UNKNOWN, 0, "server kept dropping the connection"))
        return results
