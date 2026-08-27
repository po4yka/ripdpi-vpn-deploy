//! One descriptor owns the security decision and the subsequent file operation.

use anyhow::{anyhow, Context as _, Result};
use rustix::fs::{Mode, OFlags};
use std::fs::File;
use std::os::unix::fs::{MetadataExt, PermissionsExt};
use std::path::Path;

fn open_owned(path: &Path) -> Result<(File, std::fs::Metadata)> {
    // NOFOLLOW makes the final-component symlink check atomic with open.
    // NONBLOCK prevents a swapped FIFO from hanging before fstat can reject it.
    let fd = rustix::fs::open(
        path,
        OFlags::RDONLY | OFlags::NOFOLLOW | OFlags::NONBLOCK | OFlags::CLOEXEC,
        Mode::empty(),
    )
    .context("open protected regular file without following symlinks")?;
    let file = File::from(fd);
    let metadata = file.metadata().context("stat protected file descriptor")?;
    require_owner(&metadata, uzers::get_current_uid())?;
    Ok((file, metadata))
}

fn require_owner(metadata: &std::fs::Metadata, uid: u32) -> Result<()> {
    if !metadata.is_file() || metadata.uid() != uid {
        return Err(anyhow!(
            "protected file must be a regular file owned by the current user"
        ));
    }
    Ok(())
}

pub(crate) fn open_private(path: &Path) -> Result<File> {
    let (file, metadata) = open_owned(path)?;
    if metadata.mode() & 0o077 != 0 {
        return Err(anyhow!(
            "protected file has unsafe owner, type, or permissions; use 0600"
        ));
    }
    Ok(file)
}

pub(crate) fn harden(path: &Path) -> Result<()> {
    let (file, _) = open_owned(path)?;
    file.set_permissions(std::fs::Permissions::from_mode(0o600))
        .context("set 0600 on protected file descriptor")
}

pub(crate) fn write_private(path: &Path, bytes: &[u8]) -> Result<()> {
    use std::io::{ErrorKind, Write};
    use std::os::unix::fs::OpenOptionsExt;
    use std::sync::atomic::{AtomicU64, Ordering};

    static NEXT_TEMP: AtomicU64 = AtomicU64::new(0);
    let parent = path
        .parent()
        .filter(|parent| !parent.as_os_str().is_empty())
        .unwrap_or_else(|| Path::new("."));
    let filename = path
        .file_name()
        .context("protected output must name a file")?;
    // Create exclusively under a unique name. A stale file or concurrent
    // writer is never ours to unlink, including reports sharing a basename.
    for _ in 0..128 {
        let mut name = filename.to_os_string();
        name.push(format!(
            ".{}.{}.tmp",
            std::process::id(),
            NEXT_TEMP.fetch_add(1, Ordering::Relaxed)
        ));
        let temp = parent.join(name);
        let mut file = match std::fs::OpenOptions::new()
            .write(true)
            .create_new(true)
            .mode(0o600)
            .open(&temp)
        {
            Ok(file) => file,
            Err(error) if error.kind() == ErrorKind::AlreadyExists => continue,
            Err(error) => return Err(error.into()),
        };
        let outcome = (|| -> Result<()> {
            file.write_all(bytes)?;
            file.sync_all()?;
            std::fs::rename(&temp, path)?;
            Ok(())
        })();
        if outcome.is_err() {
            let _ = std::fs::remove_file(&temp);
        }
        return outcome;
    }
    Err(anyhow!("cannot reserve a protected temporary file"))
}

#[cfg(test)]
mod tests {
    #![allow(clippy::unwrap_used)]
    use super::*;

    #[test]
    fn private_write_preserves_an_unrelated_temp_file() {
        let dir = tempfile::tempdir().unwrap();
        let output = dir.path().join("report.json");
        let unrelated = dir.path().join("report.tmp");
        std::fs::write(&unrelated, b"another writer's bytes").unwrap();
        write_private(&output, b"new report").unwrap();
        assert_eq!(std::fs::read(unrelated).unwrap(), b"another writer's bytes");
        assert_eq!(std::fs::read(&output).unwrap(), b"new report");
        assert_eq!(std::fs::metadata(output).unwrap().mode() & 0o777, 0o600);
    }

    #[test]
    fn parallel_private_writes_with_shared_stems_do_not_collide() {
        let dir = tempfile::tempdir().unwrap();
        std::thread::scope(|scope| {
            for extension in ["json", "jsonl", "html", "svg"] {
                let path = dir.path().join(format!("report.{extension}"));
                scope.spawn(move || {
                    for _ in 0..20 {
                        write_private(&path, extension.as_bytes()).unwrap();
                    }
                    assert_eq!(std::fs::read(path).unwrap(), extension.as_bytes());
                });
            }
        });
        assert_eq!(std::fs::read_dir(dir.path()).unwrap().count(), 4);
    }

    #[test]
    fn metadata_gate_rejects_a_foreign_uid_even_for_a_private_regular_file() {
        let file = tempfile::tempfile().unwrap();
        file.set_permissions(std::fs::Permissions::from_mode(0o600))
            .unwrap();
        let metadata = file.metadata().unwrap();
        assert!(require_owner(&metadata, metadata.uid()).is_ok());
        assert!(require_owner(&metadata, metadata.uid().wrapping_add(1)).is_err());
    }
}
