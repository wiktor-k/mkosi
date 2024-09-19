# SPDX-License-Identifier: LGPL-2.1-or-later


import tempfile
from collections.abc import Mapping
from pathlib import Path

import pytest

from mkosi.run import find_binary, run

from . import Image, ImageConfig

pytestmark = pytest.mark.integration


def test_signing_checksums_with_sop(config: ImageConfig) -> None:
    if find_binary("sqop", root=config.tools) is None:
        pytest.skip("Needs 'sqop' binary in PATH to perform sop tests.")
    with tempfile.TemporaryDirectory() as path, Image(config) as image:
        tmp_path = Path(path)
        tmp_path.chmod(0o755)

        signing_key = tmp_path / "signing-key.pgp"
        signing_cert = tmp_path / "signing-cert.pgp"

        # create a brand new signing key
        with open(signing_key, "wb") as o:
            run(cmdline=["sqop", "generate-key", "--signing-only", "Test"], stdout=o)

        signing_key.chmod(0o744)

        # extract public key (certificate)
        with open(signing_key, "rb") as i, open(signing_cert, "wb") as o:
            run(cmdline=["sqop", "extract-cert"], stdin=i, stdout=o)

        signing_cert.chmod(0o744)

        image.build(
            options=["--checksum=true", "--openpgp-tool=sqop", "--sign=true", f"--key={signing_key}"]
        )

        signed_file = image.output_dir / "image.SHA256SUMS"
        signature = image.output_dir / "image.SHA256SUMS.gpg"

        with open(signed_file, "rb") as i:
            run(cmdline=["sqop", "verify", signature, signing_cert], stdin=i)


def test_signing_checksums_with_gpg(config: ImageConfig) -> None:
    with tempfile.TemporaryDirectory() as path, Image(config) as image:
        tmp_path = Path(path)
        tmp_path.chmod(0o755)

        signing_key = "mkosi-test@example.org"
        signing_cert = tmp_path / "signing-cert.pgp"
        gnupghome = tmp_path / ".gnupg"

        env: Mapping[str, str] = dict(GNUPGHOME=str(gnupghome))

        # Creating GNUPGHOME directory and appending an *empty* common.conf
        # file stops GnuPG from spawning keyboxd which causes issues when switching
        # users. See https://stackoverflow.com/a/72278246 for details
        gnupghome.mkdir()
        (gnupghome / "common.conf").touch()

        # create a brand new signing key
        run(cmdline=["gpg", "--quick-gen-key", "--batch", "--passphrase", "", signing_key], env=env)

        # GnuPG will set 0o700 permissions so that the secret files are not available
        # to other users. Since this is for tests only and we need that keyring for signing
        # enable all permissions. We need write permissions since GnuPG creates temporary
        # files in this directory during operation.
        gnupghome.chmod(0o777)
        for p in gnupghome.rglob("*"):
            p.chmod(0o777)

        # export public key (certificate)
        with open(signing_cert, "wb") as o:
            run(cmdline=["gpg", "--export", signing_key], env=env, stdout=o)

        signing_cert.chmod(0o744)

        image.build(options=["--checksum=true", "--sign=true", f"--key={signing_key}"], env=env)

        signed_file = image.output_dir / "image.SHA256SUMS"
        signature = image.output_dir / "image.SHA256SUMS.gpg"

        run(cmdline=["gpg", "--verify", signature, signed_file], env=env)
