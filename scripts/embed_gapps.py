#!/usr/bin/env python3
"""Embed a MindTheGapps payload into an ext4 GSI system image, without root.

Reproduces what MindTheGapps' update-binary does:
  - dirs 0755 root:root, files 0644 root:root (0755 for *.sh / no extension)
  - SELinux label u:object_r:system_file:s0 on everything it adds
  - remove system_ext/priv-app/Provision when SetupWizard is installed

The image must be a plain ext4 (no shared_blocks), large enough, and fsck-clean.
Uses debugfs only (no mount, no sudo).

Usage: embed_gapps.py system.img payload_dir/system
"""
import os
import subprocess
import sys
import tempfile

img, payload = sys.argv[1], sys.argv[2]
IMG_ROOT = "/system"          # the GSI is system-as-root: /system/product, /system/system_ext
LABEL = b"u:object_r:system_file:s0\0"


def dbg(cmd):
    return subprocess.run(["debugfs", "-R", cmd, img], capture_output=True, text=True).stdout


def exists(path):
    return "Inode:" in dbg(f"stat {path}")


def list_dir(path):
    """Return [(name, is_dir)] using `ls -p`."""
    out = []
    for line in dbg(f"ls -p {path}").splitlines():
        p = line.split("/")
        if len(p) < 6 or p[5] in (".", ".."):
            continue
        mode = int(p[2], 8)
        out.append((p[5], (mode & 0o170000) == 0o040000))
    return out


def rm_tree(path, cmds):
    for name, is_dir in list_dir(path):
        child = f"{path}/{name}"
        if is_dir:
            rm_tree(child, cmds)
        else:
            cmds.append(f"rm {child}")
    cmds.append(f"rmdir {path}")


def main():
    label_file = tempfile.NamedTemporaryFile(delete=False)
    label_file.write(LABEL)
    label_file.close()

    cmds = []

    def meta(path, mode):
        cmds.append(f"sif {path} mode 0{mode:o}")
        cmds.append(f"sif {path} uid 0")
        cmds.append(f"sif {path} gid 0")
        cmds.append(f"ea_set -f {label_file.name} {path} security.selinux")

    dirs, files = [], []
    for root, ds, fs in os.walk(payload):
        rel = os.path.relpath(root, payload)
        for d in sorted(ds):
            dirs.append(os.path.normpath(os.path.join(rel, d)))
        for f in sorted(fs):
            files.append(os.path.normpath(os.path.join(rel, f)))
    dirs.sort(key=lambda p: (p.count("/"), p))

    for d in dirs:
        target = f"{IMG_ROOT}/{d}"
        if exists(target):
            continue                      # keep existing dirs (and their labels) untouched
        cmds.append(f"mkdir {target}")
        meta(target, 0o040755)

    for f in files:
        target = f"{IMG_ROOT}/{f}"
        ext = os.path.splitext(f)[1]
        mode = 0o100755 if (ext == ".sh" or ext == "") else 0o100644
        if exists(target):
            cmds.append(f"rm {target}")
        cmds.append(f"write {os.path.join(payload, f)} {target}")
        meta(target, mode)

    if os.path.exists(os.path.join(payload, "system_ext/priv-app/SetupWizard")):
        prov = f"{IMG_ROOT}/system_ext/priv-app/Provision"
        if exists(prov):
            rm_tree(prov, cmds)

    with tempfile.NamedTemporaryFile("w", suffix=".cmds", delete=False) as cf:
        cf.write("\n".join(cmds) + "\n")
    print(f"{len(dirs)} dirs, {len(files)} files, {len(cmds)} debugfs commands -> {cf.name}")
    r = subprocess.run(["debugfs", "-w", "-f", cf.name, img], capture_output=True, text=True)
    bad = [l for l in (r.stdout + r.stderr).splitlines()
           if any(k in l.lower() for k in ("error", "no space", "not found", "illegal", "bad "))]
    print("debugfs problems:", bad if bad else "none")
    os.unlink(label_file.name)
    os.unlink(cf.name)


main()
