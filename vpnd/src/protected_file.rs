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

#[cfg(test)]
mod tests {
    #![allow(clippy::unwrap_used)]
    use super::*;

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
