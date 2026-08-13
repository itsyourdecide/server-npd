#!/usr/bin/env python3
"""Create an NPD cluster user for bastion, submit, storage, and execute nodes."""

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
ANSIBLE_DIR = Path(__file__).resolve().parents[1] / "ansible"
EXECUTE_GROUP = "asus_nodes"
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
    cwd: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    if dry_run:
        prefix = f"(cd {cwd} &&) " if cwd else ""
        print("+ " + prefix + " ".join(cmd))
        if input_text:
            print(input_text)
        return subprocess.CompletedProcess(cmd, 0, "", "")

    return subprocess.run(
        cmd,
        input=input_text,
        text=True,
        check=True,
        capture_output=capture,
        cwd=cwd,
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


def passwd_text_execute_nodes() -> str:
    result = run(
        ["ansible", EXECUTE_GROUP, "-m", "command", "-a", "getent passwd"],
        capture=True,
        cwd=ANSIBLE_DIR,
    )
    return result.stdout


def next_uid(*, include_execute_nodes: bool = False) -> int:
    passwd_outputs = [passwd_text_bastion(), passwd_text_condor()]
    if include_execute_nodes:
        passwd_outputs.append(passwd_text_execute_nodes())
    used = used_uids(passwd_outputs)
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


def execute_user_script(username: str, uid: int) -> str:
    return f"""set -euo pipefail
user={username!r}
uid={str(uid)!r}

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

# Execute-node accounts are for HTCondor/POSIX identity only.
# Users enter through bastion01 -> condor01, not by SSHing to execute nodes.
home="$(getent passwd "$user" | cut -d: -f6)"
rm -rf "$home/.ssh"
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


def create_on_execute_nodes(script: str, dry_run: bool) -> None:
    run(
        ["ansible", EXECUTE_GROUP, "-m", "shell", "-a", script],
        dry_run=dry_run,
        cwd=ANSIBLE_DIR,
    )


def create_storage_dirs(username: str, uid: int, dry_run: bool) -> None:
    if dry_run:
        storage_ready = True
    else:
        storage_ready = os.path.ismount("/data") and os.access("/data", os.X_OK)
    if not storage_ready:
        print()
        print("Storage note: /data is not mounted or not accessible; skipping user")
        print("storage directories for now. Re-run later with --storage-only after JBOD")
        print("storage is online.")
        return False

    script = f"""set -euo pipefail
user={username!r}
uid={str(uid)!r}
test -d /data
test -x /data
install -d -m 0755 /data/projects/users /data/results/users
install -d -m 1777 /data/scratch/users
install -d -m 0750 "/data/projects/users/$user"
install -d -m 1777 "/data/results/users/$user" "/data/scratch/users/$user"
chown "$uid:$uid" "/data/projects/users/$user" "/data/results/users/$user" "/data/scratch/users/$user"
"""
    run(["bash", "-s"], input_text=script, dry_run=dry_run)
    return True


def get_user_uid(username: str, passwd_output: str) -> int | None:
    for line in passwd_output.splitlines():
        fields = line.split(":")
        if len(fields) > 2 and fields[0] == username and fields[2].isdigit():
            return int(fields[2])
    return None


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Create a key-only cluster user on bastion01/condor01, with optional "
            "locked POSIX identity accounts on HTCondor execute nodes."
        ),
    )
    parser.add_argument("username", help="lowercase Linux login name")
    parser.add_argument(
        "public_key",
        nargs="?",
        type=Path,
        help="path to SSH public key; not needed with --storage-only or --execute-only",
    )
    parser.add_argument("--uid", type=int, help="explicit UID, default: first free 20000-29999")
    parser.add_argument("--dry-run", action="store_true", help="print actions without changing hosts")
    parser.add_argument(
        "--accounts-only",
        action="store_true",
        help="create only bastion01/condor01 accounts, skip /data directories",
    )
    parser.add_argument(
        "--storage-only",
        action="store_true",
        help="create only /data directories for an existing user",
    )
    parser.add_argument(
        "--execute-nodes",
        action="store_true",
        help=(
            "also create locked-password POSIX identity accounts on ASUS "
            "HTCondor execute nodes, without authorized_keys"
        ),
    )
    parser.add_argument(
        "--execute-only",
        action="store_true",
        help="create only execute-node POSIX identity accounts for an existing user",
    )
    args = parser.parse_args()

    account_modes = [args.accounts_only, args.storage_only, args.execute_only]
    if sum(bool(mode) for mode in account_modes) > 1:
        raise SystemExit("--accounts-only, --storage-only and --execute-only are mutually exclusive.")
    validate_username(args.username)

    key = None
    if not args.storage_only and not args.execute_only:
        if args.public_key is None:
            raise SystemExit("public_key is required unless --storage-only or --execute-only is used.")
        key = read_public_key(args.public_key)

    if (args.storage_only or args.execute_only) and args.uid is None:
        condor_uid = get_user_uid(args.username, passwd_text_condor())
        if condor_uid is None:
            raise SystemExit(
                f"User {args.username!r} does not exist on condor01; "
                "create accounts first or pass --uid explicitly."
            )
        uid = condor_uid
    else:
        uid = args.uid if args.uid is not None else next_uid(
            include_execute_nodes=args.execute_nodes,
        )

    if not (UID_MIN <= uid <= UID_MAX):
        raise SystemExit(f"UID must be in range {UID_MIN}-{UID_MAX}.")

    script = ""
    if key is not None:
        key_b64 = base64.b64encode((key + "\n").encode("utf-8")).decode("ascii")
        script = remote_user_script(args.username, uid, key_b64)

    if not args.storage_only and not args.execute_only:
        print(f"Creating cluster user {args.username!r} with UID {uid}")
        create_on_bastion(script, args.dry_run)
        create_on_condor(script, args.dry_run)

    if args.execute_nodes or args.execute_only:
        print(f"Creating execute-node POSIX identity for {args.username!r} with UID {uid}")
        create_on_execute_nodes(execute_user_script(args.username, uid), args.dry_run)

    storage_created = False
    if not args.accounts_only and not args.execute_only:
        storage_created = create_storage_dirs(args.username, uid, args.dry_run)

    print()
    print("Done.")
    print(f"Public SSH entry: ssh -p 10000 {args.username}@pve02.taile43d6d.ts.net")
    if storage_created:
        print(f"Project dir: /data/projects/users/{args.username}")
        print(f"Results dir: /data/results/users/{args.username}")
        print(f"Scratch dir: /data/scratch/users/{args.username}")
    else:
        print("Storage dirs: not created in this run")
    return 0


if __name__ == "__main__":
    sys.exit(main())
