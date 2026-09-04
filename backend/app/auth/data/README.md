# Common-password data

`common-passwords.txt` is a policy-relevant subset of SecLists release `2026.1`:

- repository: `https://github.com/danielmiessler/SecLists`;
- commit: `190c6f7bd58c847ceadfe57d9853592737f059e8`;
- source: `Passwords/Common-Credentials/xato-net-10-million-passwords-100000.txt`;
- source SHA-256: `1472aafa2561df5e3293aee252aee3ca660c12b399a283cf808bb01b39be388b`;
- local subset SHA-256: `d96ccdc44ae4d57e89840bcc06c00e04d9756c4440387f38b5b88d83dbcf4d48`.

The local file contains only the 72 complete source entries whose lengths are
between TrackSea's inclusive 15- and 128-character password limits. Entries
remain in source order and are compared against the complete NFC-normalized
password. The data is available locally at runtime and requires no network call.

SecLists is distributed under the MIT License. The required license and
copyright notice are preserved in `SECLISTS-LICENSE.txt`.
