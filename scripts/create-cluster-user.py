#!/usr/bin/env python3
"""Create an NPD cluster user on bastion01 and condor01."""

from __future__ import annotations

import argparse
import base64
import os
import re
import subprocess
import sys
from pathlib import Path


PVE02 = "root@10.10.20.12"
BASTION_CTID = "102"
CONDOR = "npdadmin@10.10.80.20"
UID_MIN = 20000
UID_MAX = 29999
VALID_KEY_TYPES = (
    "ssh-ed25519",
    "ssh-rsa",
    "ecdsa-sha2-nistp256",
    "ecdsa-sha2-nistp384",
    "ecdsa-sha2-nistp521",
    "sk-ssh-ed25519@openssh.com",
    "sk-ecdsa-sha2-nistp256@openssh.com",
)


def run(
    cmd: list[str],
    *,
    input_text: str | None = None,
    dry_run: bool = False,
    capture: bool = False,
) -> subprocess.CompletedProcess[str]:
    if dry_run:
        print("+ " + " ".join(cmd))
        if input_text:
            print(input_text)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    return subprocess.run(
        cmd,
        input=input_text,
        text=True,
        check=True,
        capture_output=capture,
    )


def validate_username(username: str) -> None:
    if not re.fullmatch(r"[a-z_][a-z0-9_-]{0,31}", username):
        raise SystemExit(
            "Username must match: [a-z_][a-z0-9_-]{0,31}. "
            "Use lowercase login names, for example: denis"
        )


def read_public_key(path: Path) -> str:
    key = path.read_text(encoding="utf-8").strip()
    if "\n" in key or "\r" in key:
        raise SystemExit("Public key file must contain exactly one key line.")
    parts = key.split()
    if len(parts) < 2 or parts[0] not in VALID_KEY_TYPES:
        raise SystemExit(
            "Unsupported or invalid SSH public key. Expected an OpenSSH public key."
        )
    try:
        base64.b64decode(parts[1].encode("ascii"), validate=True)
    except Exception as exc:  # noqa: BLE001
        raise SystemExit("SSH public key payload is not valid base64.") from exc
    return key


def passwd_text_bastion() -> str:
    result = run(
        ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5", PVE02,
         "pct", "exec", BASTION_CTID, "--", "getent", "passwd"],
        capture=True,
    )
    return result.stdout


def passwd_text_condor() -> str:
    result = run(
        ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5", CONDOR,
         "getent", "passwd"],
        capture=True,
    )
    return result.stdout


def used_uids(passwd_outputs: list[str]) -> set[int]:
    uids: set[int] = set()
    for output in passwd_outputs:
        for line in output.splitlines():
            fields = line.split(":")
            if len(fields) > 2 and fields[2].isdigit():
                uids.add(int(fields[2]))
    return uids


def next_uid() -> int:
    used = used_uids([passwd_text_bastion(), passwd_text_condor()])
    for uid in range(UID_MIN, UID_MAX + 1):
        if uid not in used:
            return uid
    raise SystemExit(f"No free UID in range {UID_MIN}-{UID_MAX}.")


def remote_user_script(username: str, uid: int, key_b64: str) -> str:
    return f"""set -euo pipefail
user={username!r}
uid={str(uid)!r}
key_b64={key_b64!r}

if getent passwd "$user" >/dev/null; then
  current_uid="$(id -u "$user")"
  if [ "$current_uid" != "$uid" ]; then
    echo "User $user already exists with UID $current_uid, expected $uid" >&2
    exit 1
  fi
else
  useradd -m -u "$uid" -U -s /bin/bash "$user"
fi

passwd -l "$user" >/dev/null 2>&1 || true
home="$(getent passwd "$user" | cut -d: -f6)"
install -d -m 700 -o "$user" -g "$user" "$home/.ssh"
printf '%s' "$key_b64" | base64 -d > "$home/.ssh/authorized_keys"
chown "$user:$user" "$home/.ssh/authorized_keys"
chmod 600 "$home/.ssh/authorized_keys"
command -v restorecon >/dev/null 2>&1 && restorecon -R "$home/.ssh" || true
"""


def create_on_bastion(script: str, dry_run: bool) -> None:
    run(
        ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5", PVE02,
         "pct", "exec", BASTION_CTID, "--", "bash", "-s"],
        input_text=script,
        dry_run=dry_run,
    )


def create_on_condor(script: str, dry_run: bool) -> None:
    run(
        ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5", CONDOR,
         "sudo", "-n", "bash", "-s"],
        input_text=script,
        dry_run=dry_run,
    )


def create_storage_dirs(username: str, uid: int, dry_run: bool) -> None:
    script = f"""set -euo pipefail
user={username!r}
uid={str(uid)!r}
install -d -m 0755 /data/projects/users /data/results/users
install -d -m 1777 /data/scratch/users
install -d -m 0750 "/data/projects/users/$user"
install -d -m 1777 "/data/results/users/$user" "/data/scratch/users/$user"
chown "$uid:$uid" "/data/projects/users/$user" "/data/results/users/$user" "/data/scratch/users/$user"
"""
    run(["bash", "-s"], input_text=script, dry_run=dry_run)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create a key-only cluster user on bastion01 and condor01.",
    )
    parser.add_argument("username", help="lowercase Linux login name")
    parser.add_argument("public_key", type=Path, help="path to SSH public key")
    parser.add_argument("--uid", type=int, help="explicit UID, default: first free 20000-29999")
    parser.add_argument("--dry-run", action="store_true", help="print actions without changing hosts")
    args = parser.parse_args()

    validate_username(args.username)
    key = read_public_key(args.public_key)
    uid = args.uid if args.uid is not None else next_uid()
    if not (UID_MIN <= uid <= UID_MAX):
        raise SystemExit(f"UID must be in range {UID_MIN}-{UID_MAX}.")

    key_b64 = base64.b64encode((key + "\n").encode("utf-8")).decode("ascii")
    script = remote_user_script(args.username, uid, key_b64)

    print(f"Creating cluster user {args.username!r} with UID {uid}")
    create_on_bastion(script, args.dry_run)
    create_on_condor(script, args.dry_run)
    create_storage_dirs(args.username, uid, args.dry_run)

    print()
    print("Done.")
    print(f"Public SSH entry: ssh -p 10000 {args.username}@pve02.taile43d6d.ts.net")
    print(f"Project dir: /data/projects/users/{args.username}")
    print(f"Results dir: /data/results/users/{args.username}")
    print(f"Scratch dir: /data/scratch/users/{args.username}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
