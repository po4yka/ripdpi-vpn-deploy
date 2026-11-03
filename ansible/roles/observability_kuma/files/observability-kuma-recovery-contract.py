"""Shared offline admission for scheduled observer recovery."""
import re


def validate(config):
    if (set(config) != {'directory', 'bucket_id', 'bucket_name', 'max_backup_age_seconds', 'restore_images',
                       'recipient', 'operator_recipients'}
            or not isinstance(config['directory'], str) or not re.fullmatch('/[A-Za-z0-9_/-]+', config['directory'])
            or not isinstance(config['bucket_id'], str) or not re.fullmatch('[a-f0-9]{24}', config['bucket_id'])
            or not isinstance(config['bucket_name'], str) or not re.fullmatch('[A-Za-z0-9-]{6,63}', config['bucket_name'])
            or type(config['max_backup_age_seconds']) is not int
            or not 3600 <= config['max_backup_age_seconds'] <= 93600
            or not isinstance(config['restore_images'], list) or len(config['restore_images']) != 2
            or any(not isinstance(ref, str) or not re.fullmatch(r'[a-z0-9][a-z0-9._/-]*@sha256:[a-f0-9]{64}', ref)
                   for ref in config['restore_images'])):
        raise ValueError('recovery-contract')
    recipients = config['operator_recipients']
    if (not isinstance(recipients, list) or not 1 <= len(recipients) <= 10
            or any(not isinstance(value, str) or not re.fullmatch('age1[0-9a-z]{58}', value)
                   for value in [config['recipient'], *recipients])
            or len(set(recipients)) != len(recipients) or config['recipient'] in recipients):
        raise ValueError('independent-kuma-recipient-required')
    return config
