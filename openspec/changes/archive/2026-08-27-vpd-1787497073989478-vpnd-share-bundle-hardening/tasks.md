# VPD-1787497073989478: Harden share bundle token handling and file permissions

## Objective

Share emits bundles only from validated tokens and configured hosts, and every bundle byte lands 0600 through a crash-safe write path.

## Ownership

- The primary agent owns vpnd/src/commands/share.rs, vpnd/src/pages/qr.rs, vpnd/tests/share_bundle.rs, vpnd/tests/share_command.rs, and this change's artifacts.

## Execution

- [x] VPD-1787497123361827 Reject empty tokens in validate_token and cover empty stdin and token-file inputs in tests #bug !high @item:VPD-1787497073989478
- [x] VPD-1787497123379234 Replace the (unset) host fallback with a hard error naming the missing secrets key; add the no-server_name regression test #bug !high @item:VPD-1787497073989478
- [x] VPD-1787497123396516 Route qr::write_svg and write_private through a create-with-mode(0600)+replace-stale-temp+rename helper; assert modes and crash recovery in tests #bug !high @item:VPD-1787497073989478

## Verification

Use the exact gates and evidence categories in verification.md.
