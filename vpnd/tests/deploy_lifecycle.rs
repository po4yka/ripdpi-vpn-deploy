//! Process-boundary regressions; external infrastructure commands are explicit
//! test doubles. These are local lifecycle tests, not deployed-host evidence.
#![allow(clippy::unwrap_used, clippy::expect_used)]

use std::os::unix::fs::PermissionsExt;
use std::path::Path;
use std::process::{Command, Output};

struct Fixture {
    dir: tempfile::TempDir,
}

impl Fixture {
    fn new() -> Self {
        let fixture = Self {
            dir: tempfile::tempdir().unwrap(),
        };
        let root = fixture.dir.path();
        for path in [
            "bin",
            "ansible/inventory",
            "terraform/providers/upcloud",
            "runtime",
        ] {
            std::fs::create_dir_all(root.join(path)).unwrap();
        }
        std::fs::write(
            root.join("Makefile"),
            "# external commands are explicit doubles\n",
        )
        .unwrap();
        for path in [
            "home/.config/vpn-provision",
            "home/Library/Application Support/vpn-provision",
        ] {
            std::fs::create_dir_all(root.join(path)).unwrap();
            std::fs::write(root.join(path).join("hosts.toml"),
                "[hosts.alias]\nenv = 'test'\nprovider = 'upcloud'\nipv4 = '203.0.113.5'\n[hosts.wrong]\nenv = 'staging'\nprovider = 'upcloud'\nipv4 = '203.0.113.5'\n").unwrap();
        }
        fixture.executable("make", r#"#!/bin/sh
set -eu
target=$1
shift
for pair in "$@"; do
  case "$pair" in SECRETS_FILE=*) secret=${pair#SECRETS_FILE=} ;; HOST=*) host=${pair#HOST=} ;; ENV=*) export ENV=${pair#ENV=} ;; esac
done
printf 'make %s\n' "$target" >> "$FIXTURE_ROOT/calls"
case "$target" in
  decrypt)
    if [ -n "${SCRIPT_DECRYPT:-}" ]; then
      SECRETS_FILE="$secret" SOPS_FILE="$SOPS_FIXTURE" bash "$SCRIPT_DECRYPT"
    else
      mkdir -p "$(dirname "$secret")"; printf 'fixture: true\n' > "$secret"; chmod 0600 "$secret"
    fi ;;
  clean) rm -f "$secret"; exit "${CLEAN_EXIT:-0}" ;;
  test-tls-policing) test "$host" = 203.0.113.5 ;;
  emit-singbox) printf '%s\n' '{"outbounds":[]}' ;;
esac
if [ "${ECHO_SECRET_PATH:-0}" = 1 ]; then printf 'reading %s\n' "$secret"; fi
if [ "$target" = "${FAIL_TARGET:-none}" ]; then exit 31; fi
"#);
        fixture.executable("ansible-inventory", r#"#!/bin/sh
printf 'inventory\n' >> "$FIXTURE_ROOT/calls"
printf '%s\n' '{"vpn":{"hosts":["fixture-node","other-env"]},"_meta":{"hostvars":{"fixture-node":{"env":"test","provider":"upcloud","ansible_host":"100.64.0.5","vpn_service_address":"203.0.113.5"},"other-env":{"env":"staging","provider":"upcloud","ansible_host":"203.0.113.6"}}}}'
"#);
        fixture.executable(
            "ansible-playbook",
            r#"#!/bin/sh
set -eu
test -f "$VPN_SECRETS_FILE"
printf 'playbook %s\n' "$*" >> "$FIXTURE_ROOT/calls"
while [ "$#" -gt 0 ]; do
  if [ "$1" = --limit ]; then shift; test "$1" = fixture-node; fi
  shift
done
exit "${PLAYBOOK_EXIT:-0}"
"#,
        );
        fixture
    }

    fn executable(&self, name: &str, script: &str) {
        let path = self.dir.path().join("bin").join(name);
        std::fs::write(&path, script).unwrap();
        std::fs::set_permissions(path, std::fs::Permissions::from_mode(0o700)).unwrap();
    }

    fn command(&self, args: &[&str]) -> Command {
        let root = self.dir.path();
        let mut command = Command::new(env!("CARGO_BIN_EXE_vpnd"));
        command
            .args(["--root", root.to_str().unwrap(), "--env", "test", "--yes"])
            .args(args)
            .env("HOME", root.join("home"))
            .env("XDG_CONFIG_HOME", root.join("home/.config"))
            .env("XDG_RUNTIME_DIR", root.join("runtime"))
            .env("FIXTURE_ROOT", root)
            .env(
                "PATH",
                format!(
                    "{}:{}",
                    root.join("bin").display(),
                    std::env::var("PATH").unwrap()
                ),
            );
        command
    }

    fn calls(&self) -> String {
        std::fs::read_to_string(self.dir.path().join("calls")).unwrap_or_default()
    }

    fn secrets(&self) -> std::path::PathBuf {
        self.dir.path().join("runtime/vpn-test.secrets.yaml")
    }
}

fn assert_success(output: &Output) {
    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stderr)
    );
}

#[test]
fn reconverge_dry_run_cleans_plaintext_and_uses_scoped_inventory_name() {
    for host_args in [
        vec!["reconverge", "--dry-run"],
        vec!["reconverge", "--dry-run", "--host", "alias"],
    ] {
        let fixture = Fixture::new();
        assert_success(&fixture.command(&host_args).output().unwrap());
        assert!(!fixture.secrets().exists());
        let calls = fixture.calls();
        assert_eq!(calls.matches("playbook ").count(), 1);
        assert!(calls.contains("--limit fixture-node"));
        assert!(calls.ends_with("make clean\n"));
    }
}

#[test]
fn deploy_and_reconverge_preserve_primary_failures_and_still_clean() {
    for args in [vec!["deploy"], vec!["reconverge"]] {
        let fixture = Fixture::new();
        let output = fixture
            .command(&args)
            .env("FAIL_TARGET", "plan")
            .env("CLEAN_EXIT", "7")
            .output()
            .unwrap();
        assert!(!output.status.success());
        assert!(!fixture.secrets().exists());
        assert!(fixture.calls().ends_with("make clean\n"));
        let error = String::from_utf8_lossy(&output.stderr);
        assert!(error.contains("make plan"));
        assert!(error.contains("cleanup also failed"));
    }
}

#[test]
fn registered_probe_uses_address_and_invalid_aliases_fail_before_work() {
    let fixture = Fixture::new();
    assert_success(
        &fixture
            .command(&["probe", "--profile", "p1", "--host", "alias"])
            .output()
            .unwrap(),
    );
    assert!(fixture.calls().contains("make test-tls-policing"));
    for subcommand in ["probe", "doctor", "reconverge"] {
        for alias in ["missing", "wrong"] {
            let fixture = Fixture::new();
            let output = fixture
                .command(&[subcommand, "--host", alias])
                .output()
                .unwrap();
            assert!(!output.status.success());
            assert!(fixture.calls().is_empty());
        }
    }
}

#[test]
fn reconverge_explain_does_not_execute_or_harden_an_existing_file() {
    let fixture = Fixture::new();
    std::fs::write(fixture.secrets(), "fixture: true\n").unwrap();
    std::fs::set_permissions(fixture.secrets(), std::fs::Permissions::from_mode(0o644)).unwrap();
    assert_success(
        &fixture
            .command(&["--explain", "reconverge"])
            .output()
            .unwrap(),
    );
    assert!(fixture.calls().is_empty());
    assert_eq!(
        Path::new(&fixture.secrets())
            .metadata()
            .unwrap()
            .permissions()
            .mode()
            & 0o777,
        0o644
    );
}

#[test]
fn doctor_redacts_both_ai_and_every_bundle_entry() {
    use std::io::Read;
    let fixture = Fixture::new();
    for program in ["uname", "terraform", "ansible"] {
        fixture.executable(program, "#!/bin/sh\nprintf 'diagnostic %s/runtime/vpn-test.secrets.yaml\\n' \"$FIXTURE_ROOT\"\n");
    }
    let bundle = fixture.dir.path().join("report.tar.gz");
    let output = fixture
        .command(&["doctor", "--ai", "--bundle", bundle.to_str().unwrap()])
        .env("ECHO_SECRET_PATH", "1")
        .output()
        .unwrap();
    assert_success(&output);
    let secrets_path = fixture.secrets().display().to_string();
    assert!(!String::from_utf8_lossy(&output.stdout).contains(&secrets_path));
    assert!(!String::from_utf8_lossy(&output.stderr).contains(&secrets_path));
    assert!(String::from_utf8_lossy(&output.stdout).contains("<redacted: secrets file path>"));
    let decoder = flate2::read::GzDecoder::new(std::fs::File::open(bundle).unwrap());
    let mut archive = tar::Archive::new(decoder);
    let mut count = 0;
    for entry in archive.entries().unwrap() {
        let mut entry = entry.unwrap();
        let mut text = String::new();
        entry.read_to_string(&mut text).unwrap();
        assert!(!text.contains(&secrets_path));
        count += 1;
    }
    assert_eq!(count, 6);
}

#[test]
fn share_without_xdg_decrypts_once_through_the_canonical_script() {
    let fixture = Fixture::new();
    fixture.executable("sops", "#!/bin/sh\ncat \"$SOPS_FIXTURE\"\n");
    let source = fixture.dir.path().join("source.yaml");
    std::fs::write(
        &source,
        "xray:\n  clients:\n    - name: phone\nsubscription:\n  server_name: sub.example.com\n",
    )
    .unwrap();
    let token = fixture.dir.path().join("token");
    std::fs::write(&token, "synthetic_token\n").unwrap();
    std::fs::set_permissions(&token, std::fs::Permissions::from_mode(0o600)).unwrap();
    let tmpdir = fixture.dir.path().join("temporary directory");
    let script = Path::new(env!("CARGO_MANIFEST_DIR")).join("../scripts/decrypt-secrets.sh");
    for _ in 0..2 {
        let output = fixture
            .command(&["share", "phone", "--token-file", token.to_str().unwrap()])
            .env_remove("XDG_RUNTIME_DIR")
            .env_remove("VPN_RUNTIME_DIR")
            .env("TMPDIR", &tmpdir)
            .env("SOPS_FIXTURE", &source)
            .env("SCRIPT_DECRYPT", &script)
            .output()
            .unwrap();
        assert_success(&output);
    }
    assert_eq!(fixture.calls().matches("make decrypt\n").count(), 1);
    assert_eq!(fixture.calls().matches("make emit-singbox\n").count(), 2);
    let plaintext = tmpdir
        .join(format!("vpn-provision-{}", uzers::get_current_uid()))
        .join("vpn-test.secrets.yaml");
    assert!(plaintext.is_file());
    assert!(fixture.dir.path().join("share/phone/index.html").is_file());
}
